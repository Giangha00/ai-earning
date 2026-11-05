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
from mt5_connector import (
    mt5,
    MT5Connector,
    IS_SIMULATION,
    get_pip_size,
    get_current_spread_pips,
    get_contract_multiplier,
    get_pip_value_per_lot,
    get_position_swap_and_commission,
    sync_closed_deal_from_mt5,
)
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
                "SELECT ticket_id, symbol, order_type, lot_size, open_price, open_time FROM orders WHERE status = 'OPEN';"
            )
            for ticket_id, sym, o_type, lot, o_price, o_time in cursor.fetchall():
                tick = mt5.symbol_info_tick(sym)
                if tick is None:
                    continue
                cur_p = float(tick.bid if o_type == "BUY" else tick.ask)
                mult = get_contract_multiplier(sym)
                gross_pnl = (cur_p - o_price) * mult * lot if o_type == "BUY" else (o_price - cur_p) * mult * lot
                swap_usd, comm_usd = get_position_swap_and_commission(ticket_id, sym, lot, o_time)
                net_pnl = gross_pnl - comm_usd + swap_usd
                floating_pnl_usd += net_pnl
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

        # Khôi phục cấu hình Bot (Initial Capital, Custom Lot, Target Goal, Bot Running) từ SQLite app_settings
        try:
            from db import get_setting
            saved_cap = get_setting("initial_capital_usd", "")
            saved_lot = get_setting("custom_lot_size", "")
            saved_goal = get_setting("target_profit_goal_usd", "")
            saved_run = get_setting("bot_running", "")
            if saved_cap:
                config.INITIAL_CAPITAL = float(saved_cap)
                config_module.INITIAL_CAPITAL = config.INITIAL_CAPITAL
            if saved_lot:
                config.CUSTOM_LOT_SIZE = float(saved_lot)
                config_module.CUSTOM_LOT_SIZE = config.CUSTOM_LOT_SIZE
            if saved_goal:
                config.TARGET_PROFIT_GOAL = float(saved_goal)
                config_module.TARGET_PROFIT_GOAL = config.TARGET_PROFIT_GOAL
            if saved_run in ("true", "1"):
                config.BOT_RUNNING = True
                config_module.BOT_RUNNING = True
        except Exception:
            pass

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
        """Nạp dữ liệu nến gần nhất (ưu tiên nến Live từ Exness MT5 nếu đã kết nối, hoặc từ Parquet) và đồng bộ về hiện tại."""
        self.switch_symbol(self.symbol, self.timeframe_str)

    def _get_timeframe_seconds(self, tf_str: Optional[str] = None) -> int:
        tf = (tf_str or self.timeframe_str or "M5").upper()
        return {
            "M1": 60,
            "M5": 300,
            "M15": 900,
            "M30": 1800,
            "H1": 3600,
            "H4": 14400,
            "D1": 86400,
        }.get(tf, 300)

    def switch_symbol(self, symbol: str, timeframe: str = "M5", df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Chuyển đổi thị trường (Symbol) & khung thời gian (Timeframe) đang xem trên biểu đồ Realtime.
        Đồng bộ ngay lập tức `self.symbol`, `self.df_candles` và giá tick của MT5 để mọi sàn đều nhảy nến Realtime.
        """
        sym = (symbol or "EURUSD").upper()
        tf = (timeframe or self.timeframe_str or "M5").upper()
        step_sec = self._get_timeframe_seconds(tf)
        self.symbol = sym
        self.timeframe_str = tf

        tf_code = {
            "M1": 1,
            "M5": 5,
            "M15": 15,
            "M30": 30,
            "H1": 16385,
            "H4": 16388,
            "D1": 16408,
        }.get(tf, 5)

        if df is None or df.empty:
            # 1. Nếu đang kết nối Live Exness MT5, ưu tiên lấy nến thật trực tiếp từ sàn Exness
            if not hasattr(mt5, "set_balance") and hasattr(mt5, "copy_rates_from_pos"):
                rates = mt5.copy_rates_from_pos(sym, tf_code, 0, 500)
                if rates is not None and len(rates) >= 30:
                    df = pd.DataFrame(rates)
                    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)

            # 2. Nếu chạy giả lập hoặc sàn chưa trả về nến, nạp từ Parquet / MockMT5
            if df is None or df.empty:
                data_dir = BASE_DIR / "data"
                files = list(data_dir.glob(f"{sym}_{tf}_*.parquet"))
                if files:
                    latest_file = max(files, key=lambda f: f.stat().st_mtime)
                    df = pd.read_parquet(latest_file)
                elif hasattr(mt5, "copy_rates_from_pos"):
                    rates = mt5.copy_rates_from_pos(sym, tf_code, 0, 500)
                    df = pd.DataFrame(rates)
                    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)

        if df is not None and not df.empty:
            df = df.sort_values(by="time").tail(500).reset_index(drop=True)
            now_ts = int(datetime.now(timezone.utc).timestamp())
            current_bar_ts = (now_ts // step_sec) * step_sec
            n = len(df)
            timestamps = [current_bar_ts - (n - 1 - i) * step_sec for i in range(n)]
            df["time"] = pd.to_datetime(timestamps, unit="s", utc=True)
            self.df_candles = df

            last_close = float(df["close"].iloc[-1])
            if hasattr(mt5, "set_symbol_price"):
                mt5.set_symbol_price(sym, last_close)
            elif hasattr(mt5, "MockMT5"):
                mt5.MockMT5.set_symbol_price(sym, last_close)

            info = mt5.symbol_info(sym) if mt5 else None
            digits = int(getattr(info, "digits", 5)) if info else 5
            point = float(getattr(info, "point", 0.00001)) if info else 0.00001
            spread_val = float(getattr(info, "spread", 15)) * point if info else 0.00015
            lc = df.iloc[-1]
            self.latest_state.update({
                "symbol": sym,
                "last_price": round(last_close, digits),
                "bid": round(last_close - spread_val, digits),
                "ask": round(last_close, digits),
                "last_candle": {
                    "time": int(pd.to_datetime(lc["time"], utc=True).timestamp()),
                    "open": round(float(lc["open"]), digits),
                    "high": round(float(lc["high"]), digits),
                    "low": round(float(lc["low"]), digits),
                    "close": round(float(lc["close"]), digits),
                    "volume": int(lc.get("tick_volume", 1)),
                },
            })
        return self.df_candles

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
        """
        Tính toán đầy đủ ma trận 36 features chuẩn Training Pool cho hàng nến cuối cùng.
        Tự động chuẩn hóa biên độ giá (Scale-Invariant Normalization) về hệ quy chiếu chuẩn 1.1260
        để mô hình LightGBM và bộ lọc OOD Isolation Forest hoạt động chính xác trên cả 355 thị trường
        (Forex, Vàng XAUUSD, Crypto BTCUSD, Chỉ số US30, Cổ phiếu AAPL...).
        """
        if len(df) < 55 or not self.features_list:
            return None

        try:
            from create_training_pool import compute_training_pool_features
            last_vol = float(df["tick_volume"].iloc[-1]) if "tick_volume" in df.columns else 0.0
            eval_df = (df.iloc[:-1] if (len(df) > 60 and last_vol < 100) else df).copy()

            last_c = float(eval_df["close"].iloc[-1])
            tr_mean = float((eval_df["high"] - eval_df["low"]).tail(50).mean())
            if tr_mean <= 0:
                tr_mean = max(last_c * 0.0005, 0.0005)
            scale = 0.00050 / tr_mean
            for col in ("open", "high", "low", "close"):
                eval_df[col] = 1.1260 + (eval_df[col] - last_c) * scale

            if "tick_volume" in eval_df.columns:
                vol_mean = float(eval_df["tick_volume"].tail(30).mean()) or 1.0
                eval_df["tick_volume"] = (eval_df["tick_volume"] * (260.0 / vol_mean)).clip(160, 750)
                eval_df.iloc[-1, eval_df.columns.get_loc("tick_volume")] = max(
                    320.0, float(eval_df["tick_volume"].iloc[-1])
                )

            df_feat = compute_training_pool_features(eval_df, pip=0.0001)
            last_features = df_feat[self.features_list].iloc[-1].fillna(0.0).values
            return last_features.astype(float)
        except Exception as e:
            logging.debug(f"Lỗi tính features realtime: {e}")
            return None

    def update_live_candle_tick(self, current_price: float, spread: float):
        """Cập nhật tick mới vào nến hiện tại trong bộ nhớ theo đúng khung thời gian (M1/M5/M15/H1/D1) đồng bộ."""
        step_sec = self._get_timeframe_seconds(self.timeframe_str)
        now_ts = int(datetime.now(timezone.utc).timestamp())
        current_bar_ts = (now_ts // step_sec) * step_sec
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
        """Thực thi lệnh giao dịch khi đã vượt qua toàn bộ 5 lớp màng lọc + Bộ lọc Max Spread & Bù phí Commission."""
        # 1. BỘ LỌC SPREAD THỜI GIAN THỰC (MAX SPREAD FILTER - Mục 2 Tài liệu Nâng cấp)
        spread = get_current_spread_pips(symbol)
        limit = config.MAX_ALLOWED_SPREAD.get(symbol, config.MAX_ALLOWED_SPREAD["DEFAULT"])
        if spread > limit:
            print(f"🚫 CHẶN LỆNH: Spread {spread} pips > trần {limit} pips. Bỏ qua!")
            logging.warning(f"🚫 CHẶN LỆNH [{symbol}]: Spread {spread} pips > trần {limit} pips. Bỏ qua!")
            return False

        # Lấy giá khớp thực tế từ tick (BUY khớp tại Ask, SELL khớp tại Bid)
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        digits = int(getattr(info, "digits", 5)) if info else 5
        point = float(getattr(info, "point", 0.00001)) if info else 0.00001
        pip_size = get_pip_size(symbol, info)
        raw_spread = float(tick.ask - tick.bid) if tick else (spread * pip_size)
        if tick:
            entry_price = round(float(tick.ask if action == TradeAction.BUY else tick.bid), digits)
        sl_price = round(float(sl_price), digits)

        # 2. QUY ĐỔI PHÍ COMMISSION SANG BUFFER PIPS CHO TAKE PROFIT (Mục 3 & 5 Tài liệu Nâng cấp)
        tp_price = round(
            self.risk_manager.calculate_tp_with_buffer(
                entry=entry_price,
                sl=sl_price,
                order_type=action.value,
                point=pip_size / 10.0,
            ),
            digits,
        )

        # 3. Kiểm tra tỷ lệ R:R >= 1.5
        rr_valid, calc_rr, d_risk, d_reward, rr_msg = self.risk_manager.check_rr_ratio(
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            spread=raw_spread,
            point=point,
        )
        if not rr_valid:
            logging.info(f"[{symbol}] Bỏ qua lệnh: {rr_msg}")
            return False

        # 4. TÍNH LOT SIZE CHUẨN GỘP CẢ PHÍ HOA HỒNG ROUND-TURN, ĐỘ TRƯỢT GIÁ SLIPPAGE & PIP VALUE ĐỘNG
        sl_pips = max(1.0, abs(entry_price - sl_price) / pip_size)
        acc = mt5.account_info()
        cap_base = float(getattr(config, "INITIAL_CAPITAL", 0.0)) or float(getattr(acc, "equity", 10000.0))
        dyn_pip_val = get_pip_value_per_lot(symbol, entry_price)
        std_lot = self.risk_manager.calculate_standard_lot(
            balance=cap_base,
            sl_pips=sl_pips,
            pip_value=dyn_pip_val,
            symbol=symbol,
            entry_price=entry_price,
            include_slippage=True,
        )
        custom_lot = self.risk_manager.get_execution_lot()
        _, one_r_money, _ = self.risk_manager.calculate_lot_size_1r(
            symbol=symbol,
            entry_price=entry_price,
            sl_price=sl_price,
            spread=raw_spread,
        )
        lot_size = custom_lot if custom_lot > 0 else std_lot

        # Bảo vệ chống cháy Vốn đánh (Initial Capital Risk Cap):
        # Không cho phép 1 lệnh đơn lẻ có mức lỗ tối đa tại SL vượt quá 25% Vốn đánh (INITIAL_CAPITAL)
        comm_per_lot = float(getattr(config, "COMMISSION_PER_LOT_USD", 7.0))
        cost_per_lot_at_sl = (sl_pips * dyn_pip_val) + comm_per_lot
        max_single_trade_risk_usd = cap_base * 0.25
        if cost_per_lot_at_sl > 0 and (lot_size * cost_per_lot_at_sl) > max_single_trade_risk_usd:
            safe_capped_lot = max(0.01, round((max_single_trade_risk_usd / cost_per_lot_at_sl) - 0.005, 2))
            if safe_capped_lot < lot_size:
                logging.warning(
                    f"🛡️ [CAPITAL RISK CAP] Giới hạn Lot {symbol} từ {lot_size} xuống {safe_capped_lot} lot "
                    f"để rủi ro tối đa 1 lệnh không vượt quá 25% Vốn đánh (${max_single_trade_risk_usd:,.2f} USD)."
                )
                lot_size = safe_capped_lot

        if lot_size <= 0:
            logging.warning(f"[{symbol}] Lot size tính toán không hợp lệ ({lot_size}).")
            return False

        # 5. KIỂM TRA TIỀN KÝ QUỸ KHẢ DỤNG (FREE MARGIN & MARGIN LEVEL %) TRƯỚC KHI MỞ LỆNH
        margin_ok, lot_size, margin_msg = self.risk_manager.check_free_margin_and_cap_lot(
            symbol=symbol,
            order_type=action.value,
            lot_size=lot_size,
            entry_price=entry_price,
        )
        if not margin_ok or lot_size <= 0:
            logging.warning(f"🚫 CHẶN LỆNH [{symbol}]: {margin_msg}")
            return False

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
        est_comm = round(float(lot_size) * float(getattr(config, "COMMISSION_PER_LOT_USD", 7.0)), 2)

        with get_connection() as conn:
            cursor = conn.cursor()
            if ticket:
                # Ghi vào orders (lưu đầy đủ cả commission và swap)
                cursor.execute("""
                    INSERT OR REPLACE INTO orders 
                    (ticket_id, symbol, order_type, lot_size, open_time, open_price, stop_loss, take_profit, commission, swap, profit, status, market_case, rr_ratio)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 'OPEN', ?, ?);
                """, (ticket, symbol, action.value, lot_size, now_str, entry_price, sl_price, tp_price, est_comm, market_case.value, calc_rr))

            # Ghi vào bot_signals
            cursor.execute("""
                INSERT INTO bot_signals 
                (timestamp, symbol, signal_type, confidence, rsi_value, atr_value, adx_value, market_case, regime, anomaly_score, rr_ratio, reason, executed, order_ticket)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (now_str, symbol, action.value, confidence * 100.0, 50.0, d_risk, 25.0, market_case.value, regime, anomaly_score, calc_rr, reason, 1 if ticket else 0, ticket))

            # Ghi vào bot_logs
            log_msg = (
                f"AI kích hoạt lệnh {action.value} #{ticket} {lot_size} lot tại {entry_price:.5f} | "
                f"SL: {sl_price:.5f} | TP (bù phí): {tp_price:.5f} | Spread: {spread} pips | R:R: 1:{calc_rr:.2f} | Case: {market_case.value}"
            )
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
        return True

    async def update_open_positions_pnl(self, current_price: float, current_bid: Optional[float] = None) -> float:
        """
        Cập nhật floating PnL thực tế cho các vị thế mở (đã trừ Spread Bid/Ask, phí Hoa hồng Round-Turn 7 USD/lot,
        phí Swap qua đêm, độ trượt giá Slippage khi chạm SL, và đồng bộ lịch sử khớp lệnh từ Terminal MT5).
        """
        total_floating_pnl = 0.0
        with get_connection() as conn:
            cursor = conn.cursor()

            # 0. Nếu đang kết nối MT5 Exness thật, tự động đồng bộ các lệnh mở từ MT5/App điện thoại về DB
            if mt5 and not hasattr(mt5, "set_balance"):
                try:
                    live_positions = mt5.positions_get() or ()
                    for pos in live_positions:
                        p_ticket = int(getattr(pos, "ticket", 0))
                        if p_ticket > 0:
                            cursor.execute("SELECT 1 FROM orders WHERE ticket_id = ?;", (p_ticket,))
                            if not cursor.fetchone():
                                p_sym = str(getattr(pos, "symbol", "EURUSD"))
                                p_type = "BUY" if int(getattr(pos, "type", 0)) == 0 else "SELL"
                                p_lot = float(getattr(pos, "volume", 0.01))
                                p_open = float(getattr(pos, "price_open", 0.0))
                                p_sl = float(getattr(pos, "sl", 0.0))
                                p_tp = float(getattr(pos, "tp", 0.0))
                                p_prof = float(getattr(pos, "profit", 0.0))
                                p_swap = float(getattr(pos, "swap", 0.0))
                                p_comm = abs(float(getattr(pos, "commission", 0.0)))
                                p_time = datetime.fromtimestamp(int(getattr(pos, "time", time.time()))).strftime("%Y-%m-%d %H:%M:%S")
                                cursor.execute(
                                    """
                                    INSERT OR IGNORE INTO orders 
                                    (ticket_id, symbol, order_type, lot_size, open_time, open_price, stop_loss, take_profit, commission, swap, profit, status, market_case, rr_ratio)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', 'EXNESS_LIVE', 1.5);
                                    """,
                                    (p_ticket, p_sym, p_type, p_lot, p_time, p_open, p_sl, p_tp, p_comm, p_swap, p_prof),
                                )
                    conn.commit()
                except Exception:
                    pass

            cursor.execute(
                "SELECT ticket_id, symbol, order_type, lot_size, open_price, stop_loss, take_profit, open_time FROM orders WHERE status = 'OPEN';"
            )
            open_orders = cursor.fetchall()

            for ticket, sym, o_type, lot, o_price, sl, tp, o_time in open_orders:
                # 1. Đồng bộ lịch sử deal thực tế từ MT5 nếu vị thế đã tự đóng trên Server Exness / App điện thoại
                synced_deal = sync_closed_deal_from_mt5(ticket)
                if synced_deal is not None and not mt5.positions_get(ticket=int(ticket)):
                    close_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    close_eval_price = synced_deal["close_price"] or o_price
                    commission_fee = synced_deal["commission"]
                    swap_fee = synced_deal["swap"]
                    profit = synced_deal["net_profit"]
                    reason = synced_deal["comment"] or "MT5_SERVER_CLOSE"
                    cursor.execute(
                        """
                        UPDATE orders 
                        SET close_time = ?, close_price = ?, commission = ?, swap = ?, profit = ?, close_reason = ?, status = 'CLOSED'
                        WHERE ticket_id = ?;
                        """,
                        (close_time, close_eval_price, commission_fee, swap_fee, profit, reason, ticket),
                    )
                    acc = mt5.account_info()
                    if acc is not None:
                        from db import set_setting
                        if hasattr(mt5, "set_balance"):
                            new_bal = round(float(acc.balance) + profit, 2)
                            mt5.set_balance(new_bal)
                        else:
                            new_bal = round(float(acc.balance), 2)
                        config.MT5_BALANCE = new_bal
                        set_setting("account_balance", str(new_bal))
                    continue

                tick = mt5.symbol_info_tick(sym)
                info = mt5.symbol_info(sym)
                point = float(getattr(info, "point", 0.00001)) if info else 0.00001
                pip_size = (point * 10.0) if (info and getattr(info, "digits", 5) in [3, 5]) else point
                bid_p = float(current_bid if current_bid is not None else (tick.bid if tick else current_price))
                ask_p = float(tick.ask if tick else current_price)
                mult = get_contract_multiplier(sym)

                if o_type == "BUY":
                    # Lệnh BUY mở ở Ask, đóng ở Bid
                    close_eval_price = bid_p
                    hit_tp = tp and close_eval_price >= tp
                    hit_sl = sl and close_eval_price <= sl
                    if hit_tp:
                        # Lệnh Limit Take Profit khớp chuẩn tại đúng mức giá TP đã đặt
                        close_eval_price = float(tp)
                    elif hit_sl:
                        # Áp dụng độ trượt giá khớp lệnh Stop Market (Slippage) thực tế khi dính SL
                        slippage_dist = float(getattr(config, "SLIPPAGE_BUFFER_PIPS", 0.3)) * pip_size
                        close_eval_price = round(float(sl) - slippage_dist, getattr(info, "digits", 5) if info else 5)
                    gross_profit = (close_eval_price - o_price) * mult * lot
                else:
                    # Lệnh SELL mở ở Bid, đóng ở Ask
                    close_eval_price = ask_p
                    hit_tp = tp and close_eval_price <= tp
                    hit_sl = sl and close_eval_price >= sl
                    if hit_tp:
                        close_eval_price = float(tp)
                    elif hit_sl:
                        slippage_dist = float(getattr(config, "SLIPPAGE_BUFFER_PIPS", 0.3)) * pip_size
                        close_eval_price = round(float(sl) + slippage_dist, getattr(info, "digits", 5) if info else 5)
                    gross_profit = (o_price - close_eval_price) * mult * lot

                # Tính phí Hoa hồng Round-Turn (7 USD/lot) + Phí qua đêm (Swap) thực tế
                swap_fee, commission_fee = get_position_swap_and_commission(ticket, sym, lot, o_time)
                profit = round(gross_profit - commission_fee + swap_fee, 2)

                # Cập nhật floating profit, commission, swap vào DB cho lệnh đang mở
                cursor.execute(
                    "UPDATE orders SET commission = ?, swap = ?, profit = ? WHERE ticket_id = ? AND status = 'OPEN';",
                    (commission_fee, swap_fee, profit, ticket),
                )

                # Cơ chế 1: Dời SL về Hòa vốn (Break-Even) & Khóa lãi tự động (Trailing Stop)
                digits_sym = getattr(info, "digits", 5) if info else 5
                if not (hit_tp or hit_sl):
                    should_mod_sl, new_sl_val, sl_mod_reason = self.risk_manager.evaluate_trailing_and_breakeven(
                        order_type=o_type,
                        open_price=float(o_price),
                        current_eval_price=float(close_eval_price),
                        current_sl=float(sl or 0.0),
                        tp_price=float(tp or 0.0),
                        pip_size=float(pip_size),
                        digits=digits_sym,
                    )
                    if should_mod_sl and new_sl_val != sl:
                        if MT5Executor.modify_position_sl_tp(int(ticket), sym, new_sl_val, float(tp or 0.0)):
                            sl = new_sl_val
                            cursor.execute(
                                "UPDATE orders SET stop_loss = ? WHERE ticket_id = ? AND status = 'OPEN';",
                                (new_sl_val, ticket),
                            )
                            cursor.execute(
                                "INSERT INTO bot_logs (log_level, module, message) VALUES ('INFO', 'trailing_sl', ?);",
                                (f"🛡️ Lệnh #{ticket} ({sym}): {sl_mod_reason}",),
                            )

                # Cơ chế 2: Đóng lệnh sớm khi AI phát hiện đảo chiều mạnh hoặc nhiễu loạn (AI Early Exit)
                early_exit = False
                early_exit_reason = ""
                if not (hit_tp or hit_sl) and sym == self.symbol:
                    one_r_est = max(1.0, float(getattr(config, "INITIAL_CAPITAL", 100.0)) * 0.01)
                    early_exit, early_exit_reason = self.risk_manager.should_early_exit_position(
                        order_type=o_type,
                        profit=profit,
                        one_r_money=one_r_est,
                        recommended_action=str(self.latest_state.get("recommended_action", "HOLD")),
                        confidence=float(self.latest_state.get("confidence", 50.0)),
                        market_case=str(self.latest_state.get("market_case", "CASE_D_SIDEWAY_QUIET")),
                        hmm_safe=bool(self.latest_state.get("hmm_safe", True)),
                    )

                # Tự động đóng lệnh nếu chạm TP, SL hoặc AI kích hoạt Đóng lệnh sớm (Early Exit)
                if hit_tp or hit_sl or early_exit:
                    reason = "TAKE_PROFIT" if hit_tp else ("STOP_LOSS" if hit_sl else early_exit_reason)
                    close_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    MT5Executor.close_position_by_ticket(int(ticket))
                    cursor.execute(
                        """
                        UPDATE orders 
                        SET close_time = ?, close_price = ?, commission = ?, swap = ?, profit = ?, close_reason = ?, status = 'CLOSED'
                        WHERE ticket_id = ?;
                        """,
                        (close_time, close_eval_price, commission_fee, swap_fee, profit, reason, ticket),
                    )

                    # Báo cho RiskManager để theo dõi chuỗi thua và cầu dao 2R
                    one_r = max(1.0, float(getattr(config, "INITIAL_CAPITAL", 100.0)) * 0.01)
                    self.risk_manager.record_trade_result(profit, one_r)

                    # Cộng/trừ lợi nhuận ròng thực tế (đã trừ Spread + Commission + Swap + Slippage) vào số dư tài khoản
                    acc = mt5.account_info()
                    if acc is not None:
                        from db import set_setting
                        if hasattr(mt5, "set_balance"):
                            new_bal = round(float(acc.balance) + profit, 2)
                            mt5.set_balance(new_bal)
                        else:
                            new_bal = round(float(acc.balance), 2)
                        config.MT5_BALANCE = new_bal
                        set_setting("account_balance", str(new_bal))

                    cursor.execute(
                        "INSERT INTO bot_logs (log_level, module, message) VALUES ('INFO', 'order_close', ?);",
                        (
                            f"Lệnh #{ticket} đã chốt ({reason}) tại {close_eval_price:.5f}, "
                            f"Lợi nhuận ròng (Comm -${commission_fee:.2f}, Swap ${swap_fee:.2f}): ${profit:.2f}",
                        ),
                    )
                    await self.broadcast({
                        "type": "ORDER_CLOSED",
                        "data": {
                            "ticket_id": ticket,
                            "symbol": sym,
                            "reason": reason,
                            "profit": profit,
                            "close_price": close_eval_price,
                        }
                    })
                else:
                    # Chỉ những lệnh vẫn đang OPEN mới cộng vào tổng Floating PnL
                    total_floating_pnl += profit

            conn.commit()
        return total_floating_pnl

    async def run_cycle(self):
        """Vòng lặp phân tích và ra quyết định Realtime chuẩn mực."""
        # 1. Lấy thông tin Tick và Giá thị trường
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return

        current_price = float(tick.ask)
        current_bid = float(tick.bid)
        spread_val = float(tick.ask - tick.bid)
        spread_pips = get_current_spread_pips(self.symbol)
        max_allowed_sp = float(config.MAX_ALLOWED_SPREAD.get(self.symbol, config.MAX_ALLOWED_SPREAD["DEFAULT"]))
        # Quy đổi sang thang điểm chuẩn (35.0 = ngưỡng khóa giãn spread) tương thích cho mọi tài sản
        spread_pts = 40.0 if spread_pips > (max_allowed_sp * 2.5) else round(spread_pips * 10.0, 1)

        # Cập nhật tick vào nến
        self.update_live_candle_tick(current_price, spread_val)

        # Cập nhật floating PnL của các lệnh đang chạy (truyền cả Ask và Bid thực tế)
        floating_pnl = await self.update_open_positions_pnl(current_price, current_bid=current_bid)

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
            try:
                from db import set_setting
                set_setting("bot_running", "false")
            except Exception:
                pass
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

        # 1B. CẦU DAO CHỐNG CHÁY VỐN ĐÁNH (HARD CAPITAL STOP-OUT PROTECTION)
        stop_out_hit, stop_floor_usd, stop_out_msg = self.risk_manager.is_capital_stop_out_reached(
            bot_equity=bot_equity,
            initial_capital=float(config.INITIAL_CAPITAL),
        )
        if bot_running and stop_out_hit:
            close_all_positions()
            config.BOT_RUNNING = False
            config_module.BOT_RUNNING = False
            bot_running = False
            try:
                from db import set_setting
                set_setting("bot_running", "false")
            except Exception:
                pass

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
                    "INSERT INTO bot_logs (log_level, module, message) VALUES ('CRITICAL', 'capital_stop_out', ?);",
                    (stop_out_msg,),
                )
                conn.commit()

            await self.broadcast({
                "type": "CAPITAL_STOP_OUT",
                "data": {
                    "equity": round(equity, 2),
                    "bot_equity": bot_equity,
                    "stop_floor": stop_floor_usd,
                    "initial_capital": config.INITIAL_CAPITAL,
                    "message": stop_out_msg,
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

        # Kiểm tra số lượng vị thế đang mở, tổng lãi đã chốt & tỷ lệ thắng để bắn realtime
        open_positions_count = 0
        total_realized_profit = 0.0
        win_rate_pct = 0.0
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'OPEN';")
                open_positions_count = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*), SUM(profit) FROM orders WHERE status = 'CLOSED';")
                closed_cnt, sum_prof = cursor.fetchone()
                total_realized_profit = round(float(sum_prof or 0.0), 2)
                if closed_cnt and closed_cnt > 0:
                    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'CLOSED' AND profit > 0;")
                    win_cnt = cursor.fetchone()[0] or 0
                    win_rate_pct = round((win_cnt / closed_cnt) * 100.0, 1)
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

        # 8. Cập nhật Trạng thái Toàn cục & Broadcast (Làm tròn chuẩn theo digits của từng thị trường)
        info = mt5.symbol_info(self.symbol) if mt5 else None
        digits = int(getattr(info, "digits", 5)) if info else 5
        point = float(getattr(info, "point", 0.00001)) if info else 0.00001
        spread_pts = round(spread_val / point, 1) if point > 0 else spread_pts

        last_candle_obj = None
        if not self.df_candles.empty:
            lc = self.df_candles.iloc[-1]
            last_candle_obj = {
                "time": int(pd.to_datetime(lc["time"]).timestamp()),
                "open": round(float(lc["open"]), digits),
                "high": round(float(lc["high"]), digits),
                "low": round(float(lc["low"]), digits),
                "close": round(float(lc["close"]), digits),
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
            "timeframe": self.timeframe_str,
            "digits": digits,
            "last_price": round(current_price, digits),
            "bid": round(float(tick.bid), digits),
            "ask": round(float(tick.ask), digits),
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
            "total_profit": total_realized_profit,
            "win_rate": win_rate_pct,
            "leverage": int(getattr(acc, "leverage", 100)),
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
