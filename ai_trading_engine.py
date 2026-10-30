"""
Module ai_trading_engine.py
Động cơ giao dịch AI Realtime tự động (Real-Time Autonomous Trading Engine)
Tích hợp toàn diện:
- CHƯƠNG 1: Price Action 6 Kịch bản thị trường (Case A-F) & Luật Bò Gấu
- CHƯƠNG 2: Machine Learning & Deep Learning (Sigmoid Confidence, HMM Regimes, Monte Carlo VaR)
- CHƯƠNG 3: Thuật toán tính R:R & Khối lượng 1R, Nhận diện vùng nén (Compression Detection)
- CHƯƠNG 4: Kỹ thuật chống nhiễu OOD (Isolation Forest) & Cầu dao ngắt mạch 24h (LOCK_BOT_24H)
- CHƯƠNG 5: Bảng tham số Hyperparameters chuẩn
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Set
import joblib
import numpy as np
import pandas as pd
import pandas_ta as ta
from fastapi import WebSocket

import time
import config as config_module
from config import BASE_DIR, config
from db import get_connection
from mt5_connector import mt5, MT5Connector, IS_SIMULATION
from executor import MT5Executor, close_all_positions
from risk_manager import RiskManager
from ai_price_action import PriceActionAnalyzer, MarketCase, TradeAction, MarketAnalysisResult
from ai_math_models import MarketHMMRegimeDetector, OutOfDistributionFilter, MonteCarloRiskEstimator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

DEFAULT_USD_VND_RATE = 25870.0


def get_account_balance(usd_vnd_rate: float = DEFAULT_USD_VND_RATE) -> Dict[str, float]:
    """
    Lấy thông tin Balance và Equity thực tế gồm cả lệnh đang chạy (theo đơn vị chuẩn USD).
    Phục vụ kiểm tra Cầu dao chốt lời tổng (Target Profit Circuit Breaker - v2).
    """
    acc = mt5.account_info() if mt5 else None
    balance_usd = float(getattr(acc, "balance", getattr(config, "MT5_BALANCE", 1000.0)))

    floating_pnl_usd = 0.0
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT symbol, order_type, lot_size, open_price FROM orders WHERE status = 'OPEN';"
            )
            for sym, o_type, lot, o_price in cursor.fetchall():
                tick = mt5.symbol_info_tick(sym)
                if tick is None:
                    continue
                cur_p = float(tick.bid if o_type == "BUY" else tick.ask)
                mult = 100.0 if "XAU" in sym or "GOLD" in sym else 100000.0
                pnl = (cur_p - o_price) * mult * lot if o_type == "BUY" else (o_price - cur_p) * mult * lot
                floating_pnl_usd += pnl
    except Exception:
        pass

    equity_usd = balance_usd + floating_pnl_usd
    engine = AITradingEngine._instance
    if engine and engine.session_start_wallet_equity is not None:
        bot_equity_usd = round(float(config.INITIAL_CAPITAL) + (equity_usd - engine.session_start_wallet_equity), 2)
    else:
        bot_equity_usd = float(getattr(config, "INITIAL_CAPITAL", equity_usd))

    return {
        "balance": balance_usd,
        "equity": bot_equity_usd,
        "wallet_equity_usd": equity_usd,
        "balance_usd": balance_usd,
        "equity_usd": bot_equity_usd,
        "floating_pnl_usd": floating_pnl_usd,
        "floating_pnl_vnd": floating_pnl_usd * usd_vnd_rate,
    }


class AITradingEngine:
    _instance: Optional["AITradingEngine"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AITradingEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.symbol: str = "EURUSD"
        self.timeframe_str: str = "M5"
        self.is_running: bool = False
        self.target_reached_triggered: bool = False
        self.session_start_wallet_equity: Optional[float] = None
        self.loop_interval_sec: float = 1.5  # Chu kỳ quét nhịp realtime (1.5s)
        self.last_trade_timestamp: float = 0.0
        self.trade_cooldown_sec: float = 20.0  # Giãn cách tối thiểu giữa 2 lệnh để chống spam
        self.max_open_positions: int = 3       # Tối đa 3 lệnh mở đồng thời

        # 1. Quản lý Rủi ro (Chương 3.1, 4.4, 5)
        self.risk_manager = RiskManager(
            risk_per_trade=0.01,       # 1R = 1.0% Vốn
            min_rr_ratio=1.5,          # Tối thiểu 1:1.5
            max_daily_loss_r=2.0,      # Cầu dao 2R / 2 lệnh thua liên tiếp
            max_consecutive_losses=2,
            target_balance=1000000.0,
        )

        # 2. Bộ phân tích Price Action 6 Kịch bản (Chương 1 & 3.2)
        self.pa_analyzer = PriceActionAnalyzer(
            atr_fast_len=5,
            atr_slow_len=20,
            compression_atr_ratio=0.65,
            swing_window=3,
            rollover_hour_start=4,
            rollover_hour_end=5,
        )

        # 3. Nạp Model Machine Learning, HMM, và OOD Filter (Chương 2 & 4)
        self.model_pipeline: Optional[Dict[str, Any]] = None
        self.features_list: List[str] = []
        self.hmm_detector: Optional[MarketHMMRegimeDetector] = None
        self.ood_filter: Optional[OutOfDistributionFilter] = None
        self.load_models()

        # Trạng thái Realtime mới nhất
        self.latest_state: Dict[str, Any] = {
            "status": "INITIALIZING",
            "symbol": self.symbol,
            "last_price": 1.12600,
            "bid": 1.12600,
            "ask": 1.12615,
            "spread_points": 15,
            "market_case": MarketCase.CASE_A_TREND.value,
            "regime": "BULLISH",
            "anomaly_score": 0.0,
            "is_ood": False,
            "circuit_breaker": "NORMAL",
            "confidence": 0.0,
            "recommended_action": "HOLD",
            "var_95": 0.0,
            "var_99": 0.0,
            "equity": 10000.0,
            "balance": 10000.0,
            "floating_pnl": 0.0,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Dữ liệu nến realtime trong bộ nhớ
        self.df_candles: pd.DataFrame = pd.DataFrame()
        self.load_initial_candles()

        # WebSocket subscribers
        self.active_websockets: Set[WebSocket] = set()

        self._task: Optional[asyncio.Task] = None
        self._initialized = True

    def load_models(self):
        """Nạp pipeline AI đã huấn luyện."""
        model_path = BASE_DIR / "models" / "lgbm_forex_model.pkl"
        if model_path.exists():
            try:
                self.model_pipeline = joblib.load(model_path)
                self.features_list = self.model_pipeline.get("features", [])
                self.hmm_detector = self.model_pipeline.get("hmm_detector")
                self.ood_filter = self.model_pipeline.get("ood_filter")
                logging.info(f"Đã nạp thành công Pipeline AI từ {model_path} (Features: {len(self.features_list)})")
            except Exception as e:
                logging.error(f"Lỗi khi nạp mô hình AI: {e}")
        else:
            logging.warning("Chưa tìm thấy lgbm_forex_model.pkl, sẽ sử dụng bộ quy tắc Price Action thuần túy.")

    def load_initial_candles(self):
        """Nạp dữ liệu nến gần nhất từ Parquet và căn chỉnh chuỗi thời gian liền mạch về hiện tại."""
        data_dir = BASE_DIR / "data"
        files = list(data_dir.glob(f"{self.symbol}_*.parquet"))
        if not files:
            files = list(data_dir.glob("*.parquet"))

        if files:
            latest_file = max(files, key=lambda f: f.stat().st_mtime)
            try:
                df = pd.read_parquet(latest_file)
                df = df.sort_values(by="time").tail(500).reset_index(drop=True)

                # Căn chỉnh 500 nến liên tục kết thúc đúng thời điểm 5 phút hiện tại
                now_ts = int(datetime.now(timezone.utc).timestamp())
                current_bar_ts = (now_ts // 300) * 300

                # Tạo chuỗi timestamp chuẩn M5 (mỗi nến cách nhau 300 giây)
                n = len(df)
                timestamps = [current_bar_ts - (n - 1 - i) * 300 for i in range(n)]
                df["time"] = pd.to_datetime(timestamps, unit="s", utc=True)

                self.df_candles = df
                last_close = float(df["close"].iloc[-1])
                if hasattr(mt5, "set_symbol_price"):
                    mt5.set_symbol_price(self.symbol, last_close)
                elif hasattr(mt5, "MockMT5"):
                    mt5.MockMT5.set_symbol_price(self.symbol, last_close)

                # Khởi tạo ngay last_candle và last_price vào latest_state
                lc = df.iloc[-1]
                self.latest_state.update({
                    "last_price": round(last_close, 5),
                    "bid": round(last_close - 0.00015, 5),
                    "ask": round(last_close, 5),
                    "last_candle": {
                        "time": int(pd.to_datetime(lc["time"], utc=True).timestamp()),
                        "open": round(float(lc["open"]), 5),
                        "high": round(float(lc["high"]), 5),
                        "low": round(float(lc["low"]), 5),
                        "close": round(float(lc["close"]), 5),
                        "volume": int(lc.get("tick_volume", 1)),
                    }
                })
                logging.info(f"Đã nạp {len(df)} nến khởi tạo từ {latest_file.name} và đồng bộ về mốc hiện tại ({datetime.fromtimestamp(current_bar_ts, timezone.utc)}) tại giá {last_close}.")
            except Exception as e:
                logging.error(f"Lỗi đọc parquet ban đầu: {e}")

    async def register_websocket(self, websocket: WebSocket):
        await websocket.accept()
        self.active_websockets.add(websocket)
        # Gửi trạng thái hiện tại ngay khi kết nối
        try:
            await websocket.send_json({"type": "INIT_STATE", "data": self.latest_state})
        except Exception:
            pass

    def unregister_websocket(self, websocket: WebSocket):
        self.active_websockets.discard(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        if not self.active_websockets:
            return

        dead_sockets = set()
        for ws in self.active_websockets:
            try:
                await ws.send_json(message)
            except Exception:
                dead_sockets.add(ws)

        for ws in dead_sockets:
            self.active_websockets.discard(ws)

    def _build_features_row(self, df: pd.DataFrame) -> Optional[np.ndarray]:
        """Tính toán đầy đủ ma trận features chuẩn Training Pool cho hàng nến cuối cùng để đưa vào Model & OOD Filter."""
        if len(df) < 55 or not self.features_list:
            return None

        try:
            from create_training_pool import compute_training_pool_features
            pip = 0.0001 if "JPY" not in self.symbol else 0.01
            # Nếu nến cuối cùng mới mở (chưa đóng nến, tick_volume còn nhỏ), dùng nến đã đóng gần nhất để tránh nhiễu intra-bar
            last_vol = float(df["tick_volume"].iloc[-1]) if "tick_volume" in df.columns else 0.0
            eval_df = df.iloc[:-1] if (len(df) > 60 and last_vol < 100) else df
            df_feat = compute_training_pool_features(eval_df, pip=pip)

            # Lấy đúng các features đã dùng khi train
            last_features = df_feat[self.features_list].iloc[-1].fillna(0.0).values
            return last_features.astype(float)
        except Exception as e:
            logging.debug(f"Lỗi tính features realtime: {e}")
            return None

    def update_live_candle_tick(self, current_price: float, spread: float):
        """Cập nhật tick mới vào nến M5 hiện tại trong bộ nhớ theo khung 300s đồng bộ."""
        now_ts = int(datetime.now(timezone.utc).timestamp())
        current_bar_ts = (now_ts // 300) * 300
        current_dt = datetime.fromtimestamp(current_bar_ts, timezone.utc)

        if self.df_candles.empty:
            self.df_candles = pd.DataFrame([{
                "time": current_dt,
                "open": current_price,
                "high": current_price,
                "low": current_price,
                "close": current_price,
                "tick_volume": 1,
                "spread": int(spread * 100000),
                "real_volume": 0
            }])
            return

        last_time_ts = int(pd.to_datetime(self.df_candles.iloc[-1]["time"], utc=True).timestamp())

        # Nếu đã bước sang khung nến 5 phút mới (current_bar_ts > last_time_ts)
        if current_bar_ts > last_time_ts:
            new_row = {
                "time": current_dt,
                "open": current_price,
                "high": current_price,
                "low": current_price,
                "close": current_price,
                "tick_volume": 1,
                "spread": int(spread * 100000),
                "real_volume": 0,
            }
            self.df_candles = pd.concat([self.df_candles, pd.DataFrame([new_row])], ignore_index=True)
            if len(self.df_candles) > 500:
                self.df_candles = self.df_candles.tail(500).reset_index(drop=True)
        else:
            # Cập nhật nến hiện tại
            idx = len(self.df_candles) - 1
            self.df_candles.at[idx, "high"] = max(float(self.df_candles.at[idx, "high"]), current_price)
            self.df_candles.at[idx, "low"] = min(float(self.df_candles.at[idx, "low"]), current_price)
            self.df_candles.at[idx, "close"] = current_price
            current_vol = float(self.df_candles.at[idx, "tick_volume"]) if pd.notna(self.df_candles.at[idx, "tick_volume"]) else 0
            self.df_candles.at[idx, "tick_volume"] = int(current_vol) + 1

    async def execute_trade_decision(
        self,
        symbol: str,
        action: TradeAction,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        market_case: MarketCase,
        confidence: float,
        rr_ratio: float,
        regime: str,
        anomaly_score: float,
        reason: str,
    ):
        """Thực thi lệnh giao dịch khi đã vượt qua toàn bộ 5 lớp màng lọc."""
        # Kiểm tra tỷ lệ R:R >= 1.5
        rr_valid, calc_rr, d_risk, d_reward, rr_msg = self.risk_manager.check_rr_ratio(
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
        )
        if not rr_valid:
            logging.info(f"[{symbol}] Bỏ qua lệnh: {rr_msg}")
            return

        # Ưu tiên sử dụng Số Lot cố định do người dùng chỉ định (Custom Lot Size - v2)
        custom_lot = self.risk_manager.get_execution_lot()
        _, one_r_money, _ = self.risk_manager.calculate_lot_size_1r(
            symbol=symbol,
            entry_price=entry_price,
            sl_price=sl_price,
        )
        lot_size = custom_lot if custom_lot > 0 else 0.01

        if lot_size <= 0:
            logging.warning(f"[{symbol}] Lot size tính toán không hợp lệ ({lot_size}).")
            return

        # Gửi lệnh lên sàn MT5 / MockMT5
        ticket = MT5Executor.open_position(
            symbol=symbol,
            order_type=action.value,
            lot_size=lot_size,
            sl_price=sl_price,
            tp_price=tp_price,
            comment=f"AI_{market_case.value[:8]}",
        )

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with get_connection() as conn:
            cursor = conn.cursor()
            if ticket:
                # Ghi vào orders
                cursor.execute("""
                    INSERT OR REPLACE INTO orders 
                    (ticket_id, symbol, order_type, lot_size, open_time, open_price, stop_loss, take_profit, profit, status, market_case, rr_ratio)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.0, 'OPEN', ?, ?);
                """, (ticket, symbol, action.value, lot_size, now_str, entry_price, sl_price, tp_price, market_case.value, calc_rr))

            # Ghi vào bot_signals
            cursor.execute("""
                INSERT INTO bot_signals 
                (timestamp, symbol, signal_type, confidence, rsi_value, atr_value, adx_value, market_case, regime, anomaly_score, rr_ratio, reason, executed, order_ticket)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (now_str, symbol, action.value, confidence * 100.0, 50.0, d_risk, 25.0, market_case.value, regime, anomaly_score, calc_rr, reason, 1 if ticket else 0, ticket))

            # Ghi vào bot_logs
            log_msg = f"AI kích hoạt lệnh {action.value} #{ticket} {lot_size} lot tại {entry_price:.5f} | SL: {sl_price:.5f} | TP: {tp_price:.5f} | R:R: 1:{calc_rr:.2f} | Case: {market_case.value} | 1R: ${one_r_money:.2f}"
            cursor.execute("INSERT INTO bot_logs (log_level, module, message) VALUES ('INFO', 'ai_engine', ?);", (log_msg,))
            conn.commit()

        # Phát broadcast sự kiện đặt lệnh
        await self.broadcast({
            "type": "ORDER_PLACED",
            "data": {
                "ticket_id": ticket,
                "symbol": symbol,
                "order_type": action.value,
                "lot_size": lot_size,
                "open_price": entry_price,
                "stop_loss": sl_price,
                "take_profit": tp_price,
                "market_case": market_case.value,
                "rr_ratio": calc_rr,
                "confidence": confidence * 100.0,
            }
        })

    async def update_open_positions_pnl(self, current_price: float) -> float:
        """Cập nhật floating PnL cho các vị thế mở và kiểm tra TP/SL."""
        total_floating_pnl = 0.0
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ticket_id, symbol, order_type, lot_size, open_price, stop_loss, take_profit FROM orders WHERE status = 'OPEN';")
            open_orders = cursor.fetchall()

            for ticket, sym, o_type, lot, o_price, sl, tp in open_orders:
                mult = 100.0 if "XAU" in sym or "GOLD" in sym else 100000.0
                if o_type == "BUY":
                    profit = (current_price - o_price) * mult * lot
                    hit_tp = tp and current_price >= tp
                    hit_sl = sl and current_price <= sl
                else:
                    profit = (o_price - current_price) * mult * lot
                    hit_tp = tp and current_price <= tp
                    hit_sl = sl and current_price >= sl

                total_floating_pnl += profit

                # Tự động đóng lệnh nếu chạm TP hoặc SL
                if hit_tp or hit_sl:
                    reason = "TAKE_PROFIT" if hit_tp else "STOP_LOSS"
                    close_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("""
                        UPDATE orders 
                        SET close_time = ?, close_price = ?, profit = ?, close_reason = ?, status = 'CLOSED'
                        WHERE ticket_id = ?;
                    """, (close_time, current_price, profit, reason, ticket))

                    # Báo cho RiskManager để theo dõi chuỗi thua và cầu dao 2R
                    one_r = 10000.0 * 0.01
                    self.risk_manager.record_trade_result(profit, one_r)

                    # Cộng/trừ lợi nhuận thực tế vào số dư tài khoản
                    acc = mt5.account_info()
                    if acc is not None:
                        from db import set_setting
                        new_bal = round(float(acc.balance) + profit, 2)
                        config.MT5_BALANCE = new_bal
                        set_setting("account_balance", str(new_bal))
                        if hasattr(mt5, "set_balance"):
                            mt5.set_balance(new_bal)

                    cursor.execute("INSERT INTO bot_logs (log_level, module, message) VALUES ('INFO', 'order_close', ?);",
                                   (f"Lệnh #{ticket} đã chốt ({reason}) tại {current_price:.5f}, Lợi nhuận: ${profit:.2f}",))

            conn.commit()
        return total_floating_pnl

    async def run_cycle(self):
        """Vòng lặp phân tích và ra quyết định Realtime chuẩn mực."""
        # 1. Lấy thông tin Tick và Giá thị trường
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return

        current_price = float(tick.ask)
        spread_val = float(tick.ask - tick.bid)
        spread_pts = round(spread_val * 100000, 1)

        # Cập nhật tick vào nến
        self.update_live_candle_tick(current_price, spread_val)

        # Cập nhật floating PnL của các lệnh đang chạy
        floating_pnl = await self.update_open_positions_pnl(current_price)

        # Thông tin tài khoản ví Exness thực tế (USD)
        acc = mt5.account_info()
        balance = float(getattr(acc, "balance", 10000.0))
        equity = balance + floating_pnl
        current_equity_vnd = equity * DEFAULT_USD_VND_RATE

        if self.session_start_wallet_equity is None:
            self.session_start_wallet_equity = equity

        # Tính toán Equity của phần vốn trích ra đánh Bot (Vốn đánh ban đầu + Lãi/Lỗ phát sinh trong phiên)
        session_pnl = equity - self.session_start_wallet_equity
        bot_equity = round(float(config.INITIAL_CAPITAL) + session_pnl, 2)

        # 1. KIỂM TRA CẦU DAO CHỐT LỜI TỔNG (TARGET CIRCUIT BREAKER - Chương 3.3 v2 - Đơn vị USD)
        bot_running = bool(getattr(config, "BOT_RUNNING", False))
        if bot_running and self.risk_manager.is_target_goal_reached(bot_equity):
            msg_close = "⚡ Tiến hành đóng toàn bộ vị thế đang mở để chốt bằng đúng số tiền mục tiêu..."
            msg_stop = "🛑 BOT ĐÃ TỰ ĐỘNG DỪNG HOÀN TOÀN TẠI MỨC MỤC TIÊU!"
            print(msg_close)
            logging.info(msg_close)
            close_all_positions()
            config.BOT_RUNNING = False
            config_module.BOT_RUNNING = False
            bot_running = False
            self.target_reached_triggered = True
            print(msg_stop)
            logging.info(msg_stop)

            # Cập nhật lại số dư sau khi đóng toàn bộ lệnh
            acc_after = mt5.account_info()
            balance = float(getattr(acc_after, "balance", equity))
            floating_pnl = 0.0
            equity = balance
            current_equity_vnd = equity * DEFAULT_USD_VND_RATE
            session_pnl = equity - self.session_start_wallet_equity
            bot_equity = round(float(config.INITIAL_CAPITAL) + session_pnl, 2)

            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO bot_logs (log_level, module, message) VALUES ('INFO', 'target_breaker', ?);",
                    (
                        f"🎯 [TARGET REACHED] Vốn đánh đạt ${bot_equity:,.2f} USD >= Mục tiêu ${config.TARGET_PROFIT_GOAL:,.2f} USD. "
                        f"Đã đóng toàn bộ vị thế trên sàn MT5/Exness và tự động ngắt Bot!",
                    ),
                )
                conn.commit()

            await self.broadcast({
                "type": "TARGET_GOAL_REACHED",
                "data": {
                    "equity": round(equity, 2),
                    "bot_equity": bot_equity,
                    "equity_vnd": round(current_equity_vnd),
                    "target_goal": config.TARGET_PROFIT_GOAL,
                    "custom_lot": config.CUSTOM_LOT_SIZE,
                    "initial_capital": config.INITIAL_CAPITAL,
                    "message": f"🎯 CẦU DAO CHỐT LỜI TỔNG KÍCH HOẠT: Vốn đánh đạt ${bot_equity:,.2f} USD (Mục tiêu: ${config.TARGET_PROFIT_GOAL:,.2f} USD). Đã tự động đóng sạch các vị thế và dừng Bot!",
                },
            })

        # 2. Phân tích Price Action 6 Kịch bản thị trường (Chương 1)
        pa_result: MarketAnalysisResult = self.pa_analyzer.analyze_market(
            self.df_candles,
            current_spread_points=spread_pts,
        )

        # 3. Phân tích Chế độ thị trường HMM (Chương 2.6)
        recent_returns = self.df_candles["close"].pct_change().dropna().tail(30).values
        latest_ret = float(recent_returns[-1]) if len(recent_returns) > 0 else 0.0
        latest_vol = float(np.std(recent_returns)) if len(recent_returns) > 0 else 0.001

        regime = "BULLISH"
        hmm_is_safe = True
        if self.hmm_detector:
            regime, hmm_is_safe = self.hmm_detector.predict_regime(latest_ret, latest_vol)

        # 4. Tính toán Features và Dự đoán ML / OOD (Chương 2.2, 4.3)
        features_vec = self._build_features_row(self.df_candles)
        raw_prob = 0.50
        anomaly_score = 0.0
        is_ood = False

        if self.model_pipeline and features_vec is not None:
            clf = self.model_pipeline.get("model")
            try:
                df_feat_row = pd.DataFrame([features_vec], columns=self.features_list)
                raw_prob = float(clf.predict_proba(df_feat_row)[0, 1])
            except Exception:
                raw_prob = 0.50

        # Áp dụng bộ lọc OOD Isolation Forest
        if self.ood_filter and features_vec is not None:
            ood_ok, ood_msg, ood_details = self.ood_filter.check_trade_validity(features_vec, raw_prob)
            anomaly_score = ood_details.get("anomaly_score", 0.0)
            is_ood = ood_details.get("is_ood", False)

        # Kết hợp xác suất dự đoán từ mô hình Training Pool (raw_prob) + Price Action Modifier
        final_confidence = min(0.98, max(0.0, raw_prob * 0.75 + pa_result.confidence_modifier))
        if raw_prob >= 0.75 and pa_result.is_tradable:
            final_confidence = min(0.98, max(raw_prob, final_confidence))

        # 5. Đánh giá Cầu dao và Điều kiện An toàn
        is_safe_trade, safe_reason = self.risk_manager.is_safe_to_trade()
        locked_24h, lock_reason = self.risk_manager.is_locked_24h()
        if not bot_running:
            if self.target_reached_triggered:
                circuit_status = f"TARGET_REACHED (${bot_equity:,.2f} / ${config.TARGET_PROFIT_GOAL:,.2f} USD)"
            else:
                circuit_status = "STOPPED"
        elif locked_24h:
            circuit_status = f"LOCKED_24H ({lock_reason})"
        else:
            circuit_status = "NORMAL"

        # 6. Tính toán Monte Carlo VaR (Chương 2.8)
        var_metrics = self.risk_manager.evaluate_portfolio_var(list(recent_returns), equity)

        # Kiểm tra số lượng vị thế đang mở và thời gian giãn cách lệnh
        open_positions_count = 0
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'OPEN';")
                open_positions_count = cursor.fetchone()[0] or 0
        except Exception:
            open_positions_count = 0

        cooldown_ready = (time.time() - self.last_trade_timestamp) >= self.trade_cooldown_sec

        # 7. Quyết định VÀO LỆNH (EXECUTION)
        # Bắt buộc thỏa mãn TOÀN BỘ 5 LỚP BẢO VỆ + BOT_RUNNING == True:
        # - Lớp 1: Không bị khóa Cầu dao (Circuit Breaker Safe) & Bot đang chạy
        # - Lớp 2: Không rơi vào Case F (Rollover/News) và Case C (Broadening Chaos)
        # - Lớp 3: HMM không ở trạng thái High Volatility Chaos
        # - Lớp 4: OOD Anomaly không bị cảnh báo dữ liệu lạ
        # - Lớp 5: Confidence Score >= 0.75 (75%)
        can_execute = (
            bot_running
            and is_safe_trade
            and pa_result.is_tradable
            and pa_result.recommended_action in (TradeAction.BUY, TradeAction.SELL)
            and hmm_is_safe
            and not is_ood
            and (final_confidence >= 0.75)
            and (pa_result.entry_suggestion is not None)
            and (pa_result.sl_suggestion is not None)
            and (pa_result.tp_suggestion is not None)
            and (open_positions_count < self.max_open_positions)
            and cooldown_ready
        )

        if can_execute:
            self.last_trade_timestamp = time.time()
            await self.execute_trade_decision(
                symbol=self.symbol,
                action=pa_result.recommended_action,
                entry_price=pa_result.entry_suggestion,
                sl_price=pa_result.sl_suggestion,
                tp_price=pa_result.tp_suggestion,
                market_case=pa_result.market_case,
                confidence=final_confidence,
                rr_ratio=2.0,
                regime=regime,
                anomaly_score=anomaly_score,
                reason=pa_result.reason,
            )

        # 8. Cập nhật Trạng thái Toàn cục & Broadcast
        last_candle_obj = None
        if not self.df_candles.empty:
            lc = self.df_candles.iloc[-1]
            last_candle_obj = {
                "time": int(pd.to_datetime(lc["time"]).timestamp()),
                "open": round(float(lc["open"]), 5),
                "high": round(float(lc["high"]), 5),
                "low": round(float(lc["low"]), 5),
                "close": round(float(lc["close"]), 5),
                "volume": int(lc.get("tick_volume", 1)),
            }

        self.latest_state = {
            "status": "RUNNING" if bot_running else "STOPPED",
            "bot_running": bot_running,
            "initial_capital": config.INITIAL_CAPITAL,
            "bot_equity": bot_equity,
            "custom_lot": config.CUSTOM_LOT_SIZE,
            "target_goal": config.TARGET_PROFIT_GOAL,
            "equity_vnd": round(current_equity_vnd),
            "symbol": self.symbol,
            "last_price": round(current_price, 5),
            "bid": round(float(tick.bid), 5),
            "ask": round(float(tick.ask), 5),
            "spread_points": spread_pts,
            "market_case": pa_result.market_case.value,
            "market_case_reason": pa_result.reason,
            "regime": regime,
            "hmm_safe": hmm_is_safe,
            "anomaly_score": round(anomaly_score, 3),
            "is_ood": is_ood,
            "circuit_breaker": circuit_status,
            "confidence": round(final_confidence * 100.0, 1),
            "recommended_action": pa_result.recommended_action.value,
            "var_95": var_metrics["var_95"],
            "var_99": var_metrics["var_99"],
            "equity": round(equity, 2),
            "balance": round(balance, 2),
            "floating_pnl": round(floating_pnl, 2),
            "consecutive_losses": self.risk_manager.consecutive_losses,
            "last_candle": last_candle_obj,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Bắn realtime tick tới toàn bộ UI frontend
        await self.broadcast({
            "type": "REALTIME_TICK",
            "data": self.latest_state
        })

    async def _run_loop(self):
        logging.info("🚀 AI Trading Engine Realtime Loop đã chính thức khởi động!")
        self.is_running = True
        while self.is_running:
            try:
                await self.run_cycle()
            except Exception as e:
                logging.error(f"Lỗi trong chu kỳ AI Engine: {e}", exc_info=False)
            await asyncio.sleep(self.loop_interval_sec)

    def start(self):
        config.BOT_RUNNING = True
        config_module.BOT_RUNNING = True
        if self._task is None or self._task.done():
            try:
                loop = asyncio.get_running_loop()
                self._task = loop.create_task(self._run_loop())
            except RuntimeError:
                pass

    def stop(self):
        config.BOT_RUNNING = False
        config_module.BOT_RUNNING = False
        logging.info("Đã dừng phát lệnh AI Trading Engine.")


def start_trading_loop():
    """
    Vòng lặp kiểm soát cầu dao chốt lời tổng và phát lệnh giao dịch (Chương 3.3 - v2).
    Hỗ trợ gọi trực tiếp từ luồng background thread hoặc đồng bộ với AITradingEngine.
    """
    print("🤖 Bot AI bắt đầu chu kỳ quét tự động...")
    logging.info("🤖 Bot AI bắt đầu chu kỳ quét tự động (Custom Lot: %s, Target Goal: $%s USD)...", config.CUSTOM_LOT_SIZE, f"{config.TARGET_PROFIT_GOAL:,.2f}")
    risk_mgr = RiskManager()
    engine = AITradingEngine()

    # Nếu vòng lặp bất đồng bộ của Engine đang chạy trong FastAPI, chỉ cần bật cờ BOT_RUNNING
    if engine.is_running and engine._task is not None and not engine._task.done():
        config.BOT_RUNNING = True
        config_module.BOT_RUNNING = True
        return

    while getattr(config, "BOT_RUNNING", False):
        account_info = get_account_balance()
        current_equity = account_info["equity"]  # Lấy Equity thực tế gồm cả lệnh đang chạy (VNĐ)

        # 1. KIỂM TRA CẦU DAO CHỐT LỜI TỔNG (TARGET CIRCUIT BREAKER)
        if risk_mgr.is_target_goal_reached(current_equity):
            print("⚡ Tiến hành đóng toàn bộ vị thế đang mở để chốt bằng đúng số tiền mục tiêu...")
            logging.info("⚡ Tiến hành đóng toàn bộ vị thế đang mở để chốt bằng đúng số tiền mục tiêu...")
            close_all_positions()
            config.BOT_RUNNING = False
            config_module.BOT_RUNNING = False
            print("🛑 BOT ĐÃ TỰ ĐỘNG DỪNG HOÀN TOÀN TẠI MỨC MỤC TIÊU!")
            logging.info("🛑 BOT ĐÃ TỰ ĐỘNG DỪNG HOÀN TOÀN TẠI MỨC MỤC TIÊU!")
            break  # Thoát hẳn vòng lặp giao dịch

        # 2. Phát lệnh giao dịch với CUSTOM_LOT_SIZE nếu chưa đạt mục tiêu
        _lot = risk_mgr.get_execution_lot()
        try:
            asyncio.run(engine.run_cycle())
        except Exception as e:
            logging.error(f"Lỗi trong start_trading_loop: {e}")
        time.sleep(10)
