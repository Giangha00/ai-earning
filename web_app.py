import os
import glob
import random
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Query, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd
import numpy as np

import threading
import config as config_module
from config import BASE_DIR, config
from db import get_connection, init_database, set_setting
from mt5_connector import mt5, MT5Connector, IS_SIMULATION
from ai_trading_engine import AITradingEngine, start_trading_loop
from ai_price_action import MarketCase
from executor import close_all_positions

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

app = FastAPI(title="AI Earning - Trading Terminal", version="2.0.0")

# Mount thư mục static
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

USD_VND_RATE = 25870  # Tỷ giá thị trường thực tế USD sang VNĐ


def fetch_live_usd_vnd_rate() -> float:
    """Cập nhật tỷ giá trực tuyến thực tế từ Yahoo Finance nếu có mạng."""
    global USD_VND_RATE
    try:
        import urllib.request
        import json
        url = "https://query1.finance.yahoo.com/v8/finance/chart/USDVND=X?interval=1d&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())["chart"]["result"][0]["meta"]
            rate = data.get("regularMarketPrice")
            if rate and rate > 20000:
                USD_VND_RATE = round(float(rate))
                return USD_VND_RATE
    except Exception as e:
        logging.debug(f"Dùng tỷ giá thị trường chuẩn: {e}")
    return USD_VND_RATE


class OrderPlaceRequest(BaseModel):
    symbol: str = "EURUSD"
    order_type: str = "BUY"  # BUY hoặc SELL
    lot_size: float = 0.1
    entry_price: Optional[float] = None
    entry_price_vnd: Optional[float] = None
    target_price: Optional[float] = None
    target_price_vnd: Optional[float] = None
    target_profit_vnd: Optional[float] = None
    target_profit_usd: Optional[float] = None
    stop_loss: Optional[float] = None


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Tính toán các chỉ báo kỹ thuật cơ bản (SMA20, SMA50, RSI14)."""
    if len(df) == 0:
        return df

    # SMA 20 & SMA 50
    df["sma20"] = df["close"].rolling(window=20).mean()
    df["sma50"] = df["close"].rolling(window=50).mean()

    # RSI 14
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df["rsi14"] = 100 - (100 / (1 + rs))

    return df


@app.on_event("startup")
async def startup_event():
    fetch_live_usd_vnd_rate()
    init_database()
    MT5Connector.connect()
    # Khởi động luồng quét dữ liệu & biểu đồ thời gian thực (chờ lệnh kích hoạt Auto-Trade từ Web UI)
    engine = AITradingEngine()
    if engine._task is None or engine._task.done():
        import asyncio
        engine._task = asyncio.create_task(engine._run_loop())
    logging.info("Hệ thống Web App và AI Trading Engine Realtime đã sẵn sàng.")


@app.on_event("shutdown")
async def shutdown_event():
    engine = AITradingEngine()
    engine.stop()
    MT5Connector.disconnect()
    logging.info("Hệ thống Web App đã tắt an toàn.")


@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    """
    WebSocket thời gian thực kết nối 2 chiều giữa Frontend & Backend.
    Truyền dữ liệu: Live tick, Real-time Candle, Market Cases A-F,
    HMM Regimes, OOD Anomaly, Circuit Breaker, và VNĐ Balance/PnL.
    """
    engine = AITradingEngine()
    await engine.register_websocket(websocket)
    try:
        while True:
            # Lắng nghe tin nhắn từ client (ping/pong)
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        engine.unregister_websocket(websocket)
    except Exception:
        engine.unregister_websocket(websocket)


@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """Trả về giao diện Dashboard chính."""
    html_file = BASE_DIR / "templates" / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Loading Dashboard...</h1>")


@app.get("/api/ai_status")
def get_ai_status():
    """Lấy trạng thái AI Engine, 6 kịch bản thị trường, HMM, OOD và Cầu dao 24H."""
    engine = AITradingEngine()
    return engine.latest_state


@app.get("/api/training_pool")
def get_training_pool_info():
    """Trả về thông tin chi tiết của Multi-Dataset Training Pool (2 bộ HuggingFace + MT5 Exness) & kết quả huấn luyện AI."""
    import json
    meta_path = BASE_DIR / "data" / "hf_datasets" / "pool_metadata.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            logging.warning(f"Lỗi đọc pool_metadata.json: {e}")
    return {"status": "empty"}


@app.get("/api/account")
def get_account_info():
    """Lấy thông tin tài khoản MT5 và quy đổi VNĐ với dữ liệu thật."""
    rate = USD_VND_RATE
    account_info = mt5.account_info() if mt5 else None
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(profit) FROM orders WHERE status = 'CLOSED';")
        closed_trades, total_profit = cursor.fetchone()
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'CLOSED' AND profit > 0;")
        win_trades = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(profit) FROM orders WHERE status = 'OPEN';")
        floating_profit = cursor.fetchone()[0] or 0.0

    win_rate = (win_trades / closed_trades * 100) if closed_trades and closed_trades > 0 else 0.0
    balance_usd = float(getattr(account_info, "balance", config.MT5_BALANCE))
    equity_usd = balance_usd + floating_profit

    # Tính toán VNĐ theo tỷ giá thực tế
    balance_vnd = balance_usd * rate
    equity_vnd = equity_usd * rate
    floating_pnl_vnd = floating_profit * rate
    total_profit_vnd = (total_profit or 0.0) * rate

    engine = AITradingEngine()
    if engine.session_start_wallet_equity is None:
        engine.session_start_wallet_equity = equity_usd
    bot_equity_usd = round(float(config.INITIAL_CAPITAL) + (equity_usd - engine.session_start_wallet_equity), 2)

    return {
        "status": "connected",
        "is_simulation": IS_SIMULATION,
        "login": getattr(account_info, "login", config.MT5_LOGIN),
        "name": f"Tài khoản Exness #{config.MT5_LOGIN}",
        "server": getattr(account_info, "server", config.MT5_SERVER),
        "currency": getattr(account_info, "currency", "USD"),
        "usd_vnd_rate": round(rate),
        # USD Metrics (Ví Exness tự động đồng bộ)
        "balance": balance_usd,
        "equity": equity_usd,
        "floating_pnl": floating_profit,
        "total_profit": round(total_profit or 0.0, 2),
        # VNĐ Metrics
        "balance_vnd": round(balance_vnd),
        "equity_vnd": round(equity_vnd),
        "floating_pnl_vnd": round(floating_pnl_vnd),
        "total_profit_vnd": round(total_profit_vnd),
        # Trading stats
        "leverage": getattr(account_info, "leverage", 100),
        "closed_trades": closed_trades or 0,
        "win_rate": round(win_rate, 1),
        # Realtime AI Metrics
        "market_case": engine.latest_state.get("market_case", "CASE_A_TREND"),
        "regime": engine.latest_state.get("regime", "BULLISH"),
        "circuit_breaker": engine.latest_state.get("circuit_breaker", "NORMAL"),
        "var_95": engine.latest_state.get("var_95", 0.0),
        # Dynamic Bot Configuration (v2 - Vốn trích ra đánh do người dùng nhập)
        "initial_capital": config.INITIAL_CAPITAL,
        "bot_equity": bot_equity_usd,
        "custom_lot": config.CUSTOM_LOT_SIZE,
        "target_goal": config.TARGET_PROFIT_GOAL,
        "bot_running": config.BOT_RUNNING,
    }


class StartBotRequest(BaseModel):
    initial_capital: float = 100.0
    custom_lot: float = 0.01
    target_goal: float = 200.0


@app.post("/api/start_bot")
def start_bot_api(req: StartBotRequest):
    """
    API Tiếp Nhận Tham Số từ Web UI (Chương 2 & 3.1 - v2 - Đơn vị chuẩn USD):
    1. Số tiền vốn đánh (USD) trích từ ví Exness - initial_capital (do người dùng nhập)
    2. Số Lot vào lệnh cố định - custom_lot
    3. Mức tiền mục tiêu muốn đạt để dừng (USD) - target_goal
    """
    if req.initial_capital is None or req.initial_capital <= 0:
        raise HTTPException(status_code=400, detail="Số tiền vốn đánh (USD) phải lớn hơn 0")
    if req.custom_lot <= 0:
        raise HTTPException(status_code=400, detail="Số Lot cố định phải lớn hơn 0")
    if req.target_goal <= 0:
        raise HTTPException(status_code=400, detail="Mức lợi nhuận mục tiêu (USD) phải lớn hơn 0")

    account_info = mt5.account_info() if mt5 else None
    wallet_balance_usd = round(float(getattr(account_info, "balance", config.MT5_BALANCE)), 2)

    if req.initial_capital > wallet_balance_usd:
        raise HTTPException(
            status_code=400,
            detail=f"Số tiền vốn đánh (${req.initial_capital:,.2f}) không được vượt quá số dư ví Exness hiện tại (${wallet_balance_usd:,.2f})",
        )

    config.INITIAL_CAPITAL = round(float(req.initial_capital), 2)
    config.CUSTOM_LOT_SIZE = round(float(req.custom_lot), 2)
    config.TARGET_PROFIT_GOAL = round(float(req.target_goal), 2)
    config.BOT_RUNNING = True

    config_module.INITIAL_CAPITAL = config.INITIAL_CAPITAL
    config_module.CUSTOM_LOT_SIZE = config.CUSTOM_LOT_SIZE
    config_module.TARGET_PROFIT_GOAL = config.TARGET_PROFIT_GOAL
    config_module.BOT_RUNNING = True

    set_setting("initial_capital_usd", str(config.INITIAL_CAPITAL))
    set_setting("custom_lot_size", str(config.CUSTOM_LOT_SIZE))
    set_setting("target_profit_goal_usd", str(config.TARGET_PROFIT_GOAL))

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(profit) FROM orders WHERE status = 'OPEN';")
        floating_profit = cursor.fetchone()[0] or 0.0
    wallet_equity_usd = wallet_balance_usd + float(floating_profit)

    engine = AITradingEngine()
    engine.load_models()
    engine.load_initial_candles()
    engine.target_reached_triggered = False
    engine.session_start_wallet_equity = wallet_equity_usd
    engine.risk_manager.circuit_breaker_locked_until = None
    engine.risk_manager.lock_reason = ""
    engine.risk_manager.consecutive_losses = 0
    engine.risk_manager.reset_daily_state(wallet_balance_usd)
    engine.latest_state["initial_capital"] = config.INITIAL_CAPITAL
    engine.latest_state["bot_equity"] = config.INITIAL_CAPITAL
    engine.latest_state["custom_lot"] = config.CUSTOM_LOT_SIZE
    engine.latest_state["target_goal"] = config.TARGET_PROFIT_GOAL
    engine.latest_state["bot_running"] = True
    engine.latest_state["status"] = "RUNNING"
    engine.latest_state["circuit_breaker"] = "NORMAL"

    # Ghi nhật ký hệ thống vào trading.log và SQLite bot_logs
    log_msg = (
        f"🚀 Khởi chạy AI Auto-Trade (v2) | Vốn trích đánh: ${config.INITIAL_CAPITAL:,.2f} USD (Ví Exness: ${wallet_balance_usd:,.2f} USD) | "
        f"Lot cố định: {config.CUSTOM_LOT_SIZE} | Mục tiêu chốt lời tổng: ${config.TARGET_PROFIT_GOAL:,.2f} USD"
    )
    logging.info(log_msg)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO bot_logs (log_level, module, message) VALUES ('INFO', 'start_bot', ?);",
            (log_msg,),
        )
        conn.commit()

    # Phát luồng chạy ngầm theo hướng dẫn Chương 3.1
    threading.Thread(target=start_trading_loop, daemon=True).start()
    engine.start()

    return {
        "status": "success",
        "message": f"Đã khởi chạy Bot với Vốn đánh ${config.INITIAL_CAPITAL:,.2f} USD & Lot: {config.CUSTOM_LOT_SIZE}",
        "initial_capital": config.INITIAL_CAPITAL,
        "bot_equity": config.INITIAL_CAPITAL,
        "custom_lot": config.CUSTOM_LOT_SIZE,
        "target_goal": config.TARGET_PROFIT_GOAL,
        "balance_usd": wallet_balance_usd,
        "bot_running": True,
    }


@app.post("/api/stop_bot")
def stop_bot_api():
    """Tạm dừng Bot AI & đóng toàn bộ vị thế đang mở theo yêu cầu người dùng."""
    closed_cnt = close_all_positions()
    config.BOT_RUNNING = False
    config_module.BOT_RUNNING = False
    engine = AITradingEngine()
    engine.stop()
    engine.latest_state["bot_running"] = False
    engine.latest_state["status"] = "STOPPED"
    engine.latest_state["circuit_breaker"] = "STOPPED"

    msg = f"🛑 Đã dừng Bot AI và đóng {closed_cnt} vị thế mở."
    logging.info(msg)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO bot_logs (log_level, module, message) VALUES ('WARNING', 'stop_bot', ?);", (msg,))
        conn.commit()

    return {"status": "success", "message": msg, "bot_running": False, "closed_positions": closed_cnt}


class BalanceUpdateRequest(BaseModel):
    balance: float


@app.post("/api/account/balance")
def update_account_balance(req: BalanceUpdateRequest):
    """
    Đồng bộ số dư thực tế từ tài khoản Exness của người dùng.
    Lưu vào Database app_settings, file .env, và cập nhật toàn bộ Engine & MockMT5.
    """
    if req.balance < 0:
        raise HTTPException(status_code=400, detail="Số dư không thể âm")

    from db import set_setting
    set_setting("account_balance", str(req.balance))
    config.MT5_BALANCE = req.balance

    if hasattr(mt5, "set_balance"):
        mt5.set_balance(req.balance)

    # Đồng bộ vào Engine & Reset mốc số dư đầu ngày trong RiskManager
    engine = AITradingEngine()
    engine.load_models()
    engine.load_initial_candles()
    engine.target_reached_triggered = False
    engine.risk_manager.circuit_breaker_locked_until = None
    engine.risk_manager.lock_reason = ""
    engine.risk_manager.consecutive_losses = 0
    engine.risk_manager.reset_daily_state(req.balance)
    engine.latest_state["balance"] = req.balance
    engine.latest_state["equity"] = req.balance

    # Cập nhật cả file .env để lưu vĩnh viễn
    try:
        env_path = BASE_DIR / ".env"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            if "MT5_BALANCE=" in content:
                import re
                content = re.sub(r"MT5_BALANCE=.*", f"MT5_BALANCE={req.balance}", content)
            else:
                content += f"\nMT5_BALANCE={req.balance}\n"
            env_path.write_text(content, encoding="utf-8")
    except Exception as e:
        logging.warning(f"Không thể ghi .env: {e}")

    return {
        "status": "success",
        "balance": req.balance,
        "message": f"Đã đồng bộ số dư Exness: ${req.balance:,.2f} USD"
    }


@app.get("/api/markets")
@app.get("/api/symbols")
def get_all_markets_api(category: Optional[str] = None, search: Optional[str] = None):
    """
    Xem toàn bộ 355 thị trường trên MT5 / Exness.
    Hỗ trợ lọc theo danh mục: 'all', 'forex', 'metals_energy', 'crypto', 'indices', 'stocks'
    hoặc tìm kiếm theo tên/mã symbol.
    """
    import exness_markets
    all_markets = exness_markets.ALL_EXNESS_MARKETS
    filtered = all_markets

    if category and category.lower() != "all":
        cat_map = {
            "forex": "Forex",
            "metals": "Kim loại & Dầu",
            "metals_energy": "Kim loại & Dầu",
            "crypto": "Crypto",
            "indices": "Chỉ số",
            "stocks": "Cổ phiếu"
        }
        target_cat = cat_map.get(category.lower(), category)
        filtered = [m for m in filtered if m.get("category", "") == target_cat]

    if search:
        q = search.lower().strip()
        filtered = [m for m in filtered if q in m.get("symbol", "").lower() or q in m.get("name", "").lower()]

    return {
        "total": len(all_markets),
        "count": len(filtered),
        "broker": "Exness (Exness-MT5Trial7)",
        "categories": {
            "all": len(all_markets),
            "forex": len(exness_markets.FOREX_MARKETS),
            "metals_energy": len(exness_markets.METALS_ENERGY_MARKETS),
            "crypto": len(exness_markets.CRYPTO_MARKETS),
            "indices": len(exness_markets.INDICES_MARKETS),
            "stocks": len(exness_markets.STOCKS_MARKETS),
        },
        "markets": filtered
    }


@app.get("/api/candles")
def get_candles(symbol: str = "EURUSD", timeframe: str = "M5", limit: int = 1500):
    """
    Đọc dữ liệu nến từ Parquet file / Engine và trả về dữ liệu chuẩn cho TradingView Lightweight Charts.
    """
    engine = AITradingEngine()
    if not engine.df_candles.empty and symbol == engine.symbol:
        df = engine.df_candles.copy()
    else:
        data_dir = BASE_DIR / "data"
        pattern = str(data_dir / f"{symbol}_{timeframe}_*.parquet")
        files = glob.glob(pattern)

        if not files:
            # Nếu là symbol khác chưa có parquet (XAUUSD, BTCUSD, US30...), sinh nến chuẩn từ MT5
            if hasattr(mt5, "copy_rates_from_pos"):
                tf_val = 5 if timeframe == "M5" else (1 if timeframe == "M1" else 15)
                rates = mt5.copy_rates_from_pos(symbol, tf_val, 0, min(limit, 500))
                df = pd.DataFrame(rates)
                df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            else:
                all_files = glob.glob(str(data_dir / "*.parquet"))
                if not all_files:
                    return JSONResponse({"candles": [], "volume": [], "sma20": [], "sma50": [], "rsi": []})
                latest_file = max(all_files, key=os.path.getmtime)
                df = pd.read_parquet(latest_file)
        else:
            latest_file = max(files, key=os.path.getmtime)
            df = pd.read_parquet(latest_file)

    df = df.sort_values(by="time").reset_index(drop=True)
    df = calculate_indicators(df)

    if limit > 0 and len(df) > limit:
        df = df.tail(limit).reset_index(drop=True)

    candles = []
    volumes = []
    sma20 = []
    sma50 = []
    rsi = []

    for _, row in df.iterrows():
        ts = int(pd.to_datetime(row["time"]).timestamp())
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        vol = float(row.get("tick_volume", 0))

        candles.append({
            "time": ts,
            "open": round(o, 5),
            "high": round(h, 5),
            "low": round(l, 5),
            "close": round(c, 5)
        })

        is_bullish = c >= o
        volumes.append({
            "time": ts,
            "value": vol,
            "color": "rgba(34, 197, 94, 0.45)" if is_bullish else "rgba(239, 68, 68, 0.45)"
        })

        sma20_val = row.get("sma20")
        if pd.notna(sma20_val):
            sma20.append({"time": ts, "value": round(float(sma20_val), 5)})

        sma50_val = row.get("sma50")
        if pd.notna(sma50_val):
            sma50.append({"time": ts, "value": round(float(sma50_val), 5)})

        rsi_val = row.get("rsi14")
        if pd.notna(rsi_val):
            rsi.append({"time": ts, "value": round(float(rsi_val), 2)})

    latest_price = candles[-1]["close"] if candles else 1.1260

    return {
        "symbol": symbol,
        "total_candles": len(df),
        "latest_price": latest_price,
        "candles": candles,
        "volume": volumes,
        "sma20": sma20,
        "sma50": sma50,
        "rsi": rsi
    }


@app.get("/api/orders")
def get_orders():
    """Lấy danh sách lệnh giao dịch của AI từ SQLite kèm quy đổi VNĐ & Kịch bản Price Action."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ticket_id, symbol, order_type, lot_size, open_time, open_price, 
                   close_time, close_price, stop_loss, take_profit, profit, close_reason, status,
                   market_case, rr_ratio
            FROM orders 
            ORDER BY open_time DESC;
        """)
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        orders = []
        for row in rows:
            order_dict = dict(zip(columns, row))
            pnl_usd = float(order_dict.get("profit") or 0.0)
            order_dict["profit_usd"] = round(pnl_usd, 2)
            order_dict["profit_vnd"] = round(pnl_usd * USD_VND_RATE)

            open_p = float(order_dict.get("open_price") or 0.0)
            order_dict["open_price_vnd"] = round(open_p * USD_VND_RATE, 2)

            tp_p = float(order_dict.get("take_profit") or 0.0) if order_dict.get("take_profit") else None
            order_dict["take_profit_vnd"] = round(tp_p * USD_VND_RATE, 2) if tp_p else None

            close_p = float(order_dict.get("close_price") or 0.0) if order_dict.get("close_price") else None
            order_dict["close_price_vnd"] = round(close_p * USD_VND_RATE, 2) if close_p else None

            orders.append(order_dict)
    return orders


@app.post("/api/orders/place")
def place_order(req: OrderPlaceRequest):
    """
    Nhận lệnh đặt từ giao diện người dùng kèm thẩm định R:R & Quản lý rủi ro.
    """
    if req.lot_size <= 0:
        raise HTTPException(status_code=400, detail="Số lot phải lớn hơn 0")

    # Kiểm tra Cầu dao ngắt mạch 24h
    engine = AITradingEngine()
    locked_24h, lock_reason = engine.risk_manager.is_locked_24h()
    if locked_24h:
        raise HTTPException(status_code=403, detail=f"Cầu dao ngắt mạch 24H đang kích hoạt: {lock_reason}. Không thể đặt lệnh mới!")

    # Xác định entry_price (Forex)
    if req.entry_price and req.entry_price > 0:
        entry_price = float(req.entry_price)
    elif req.entry_price_vnd and req.entry_price_vnd > 0:
        entry_price = float(req.entry_price_vnd) / USD_VND_RATE
    else:
        raise HTTPException(status_code=400, detail="Vui lòng nhập mức giá muốn đánh hợp lệ")

    mult = 100.0 if "XAU" in req.symbol or "GOLD" in req.symbol else 100000.0

    # Xác định target_price
    if req.target_price and req.target_price > 0:
        target_price = float(req.target_price)
    elif req.target_profit_usd and req.target_profit_usd > 0:
        diff = float(req.target_profit_usd) / (mult * req.lot_size)
        target_price = entry_price + diff if req.order_type.upper() == "BUY" else entry_price - diff
    elif req.target_price_vnd and req.target_price_vnd > 0:
        target_price = float(req.target_price_vnd) / USD_VND_RATE
    elif req.target_profit_vnd and req.target_profit_vnd > 0:
        desired_usd = float(req.target_profit_vnd) / USD_VND_RATE
        diff = desired_usd / (mult * req.lot_size)
        target_price = entry_price + diff if req.order_type.upper() == "BUY" else entry_price - diff
    else:
        raise HTTPException(status_code=400, detail="Vui lòng nhập mức giá mong muốn kiếm được")

    # Stop Loss mặc định nếu người dùng chưa nhập
    sl_price = req.stop_loss
    if sl_price is None or sl_price <= 0:
        diff_sl = abs(target_price - entry_price) / 2.0  # R:R chuẩn 1:2
        sl_price = entry_price - diff_sl if req.order_type.upper() == "BUY" else entry_price + diff_sl

    # Thẩm định tỷ lệ R:R theo CHƯƠNG 3.1 (Tối thiểu 1:1.5)
    rr_valid, calc_rr, _, _, rr_msg = engine.risk_manager.check_rr_ratio(
        entry_price=entry_price,
        sl_price=sl_price,
        tp_price=target_price,
    )
    if not rr_valid:
        raise HTTPException(status_code=400, detail=f"{rr_msg} Vui lòng điều chỉnh TP hoặc SL hợp lý.")

    if req.order_type.upper() == "BUY":
        expected_profit_usd = (target_price - entry_price) * mult * req.lot_size
    else:
        expected_profit_usd = (entry_price - target_price) * mult * req.lot_size

    expected_profit_vnd = expected_profit_usd * USD_VND_RATE
    entry_price_vnd = entry_price * USD_VND_RATE
    target_price_vnd = target_price * USD_VND_RATE

    ticket_id = random.randint(10126000, 10129999)
    open_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    current_case = engine.latest_state.get("market_case", "CASE_A_TREND")
    regime = engine.latest_state.get("regime", "BULLISH")
    confidence = engine.latest_state.get("confidence", 75.0)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO orders 
            (ticket_id, symbol, order_type, lot_size, open_time, open_price, stop_loss, take_profit, profit, status, market_case, rr_ratio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.0, 'OPEN', ?, ?);
        """, (ticket_id, req.symbol, req.order_type.upper(), req.lot_size, open_time, entry_price, sl_price, target_price, current_case, calc_rr))

        msg = f"Đã vào lệnh {req.order_type.upper()} #{ticket_id} {req.lot_size} lot {req.symbol} tại giá {entry_price:.5f}, TP {target_price:.5f} - Dự kiến lãi: +${expected_profit_usd:.2f} USD (R:R 1:{calc_rr:.2f})"
        cursor.execute("INSERT INTO bot_logs (log_level, module, message) VALUES ('INFO', 'order_entry', ?);", (msg,))

        cursor.execute("""
            INSERT INTO bot_signals (timestamp, symbol, signal_type, confidence, rsi_value, atr_value, adx_value, market_case, regime, anomaly_score, rr_ratio, reason, executed, order_ticket)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?);
        """, (open_time, req.symbol, req.order_type.upper(), confidence, 50.0, 0.0012, 25.0, current_case, regime, 0.0, calc_rr, f"Lệnh thủ công R:R 1:{calc_rr:.2f}", ticket_id))

        conn.commit()

    return {
        "success": True,
        "ticket_id": ticket_id,
        "message": f"Đặt lệnh thành công #{ticket_id}",
        "entry_price": round(entry_price, 5),
        "entry_price_vnd": round(entry_price_vnd),
        "target_price": round(target_price, 5),
        "target_price_vnd": round(target_price_vnd),
        "rr_ratio": round(calc_rr, 2),
        "expected_profit_usd": round(expected_profit_usd, 2),
        "expected_profit_vnd": round(expected_profit_vnd)
    }


@app.post("/api/orders/close/{ticket_id}")
def close_order(ticket_id: int):
    """Đóng lệnh giao dịch thủ công."""
    close_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, order_type, lot_size, open_price, take_profit FROM orders WHERE ticket_id = ? AND status = 'OPEN';", (ticket_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy lệnh mở với Ticket này")

        symbol, o_type, lot_size, open_price, take_profit = row
        tick = mt5.symbol_info_tick(symbol) if mt5 else None
        if tick is not None:
            close_price = float(tick.bid if o_type == "BUY" else tick.ask)
        else:
            close_price = take_profit if take_profit else open_price

        mult = 100.0 if "XAU" in symbol or "GOLD" in symbol else 100000.0
        gross_profit = (close_price - open_price) * mult * lot_size if o_type == "BUY" else (open_price - close_price) * mult * lot_size
        comm_per_lot = float(getattr(config, "COMMISSION_PER_LOT_USD", 7.0))
        profit = round(gross_profit - (float(lot_size) * comm_per_lot), 2)

        cursor.execute("""
            UPDATE orders 
            SET close_time = ?, close_price = ?, profit = ?, close_reason = 'MANUAL_CLOSE', status = 'CLOSED'
            WHERE ticket_id = ?;
        """, (close_time, close_price, profit, ticket_id))

        cursor.execute("""
            INSERT INTO bot_logs (log_level, module, message)
            VALUES ('INFO', 'order_close', ?);
        """, (f"Đã đóng lệnh #{ticket_id} {symbol} tại {close_price}, lợi nhuận: +${profit:.2f} ({profit * USD_VND_RATE:,.0f} đ)",))

        conn.commit()

    # Cộng lợi nhuận thực tế vào số dư tài khoản
    acc = mt5.account_info() if mt5 else None
    if acc is not None:
        new_bal = round(float(acc.balance) + profit, 2)
        config.MT5_BALANCE = new_bal
        set_setting("account_balance", str(new_bal))
        if hasattr(mt5, "set_balance"):
            mt5.set_balance(new_bal)

    return {"success": True, "ticket_id": ticket_id, "profit": profit}


@app.get("/api/signals")
def get_signals():
    """Lấy danh sách tín hiệu bot từ SQLite kèm Market Case và HMM Regime."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, symbol, signal_type, confidence, rsi_value, atr_value, adx_value,
                   market_case, regime, anomaly_score, rr_ratio, reason, executed, order_ticket
            FROM bot_signals 
            ORDER BY timestamp DESC
            LIMIT 50;
        """)
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        signals = [dict(zip(columns, row)) for row in rows]
    return signals


@app.get("/api/equity")
def get_equity():
    """Lấy lịch sử biến động vốn daily_equity."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, balance, equity, floating_pnl, total_trades, win_trades
            FROM daily_equity
            ORDER BY date ASC;
        """)
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        data = [dict(zip(columns, row)) for row in rows]
    return data


@app.get("/api/logs")
def get_logs():
    """Lấy lịch sử nhật ký hệ thống bot_logs."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, log_level, module, message
            FROM bot_logs
            ORDER BY timestamp DESC
            LIMIT 50;
        """)
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        logs = [dict(zip(columns, row)) for row in rows]
    return logs


@app.get("/api/files")
def list_parquet_files():
    """Liệt kê các tệp dữ liệu trong thư mục data/."""
    data_dir = BASE_DIR / "data"
    files = glob.glob(str(data_dir / "*.parquet"))
    results = []
    for f in sorted(files, key=os.path.getmtime, reverse=True):
        size_mb = os.path.getsize(f) / (1024 * 1024)
        mtime = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M:%S")
        results.append({
            "name": os.path.basename(f),
            "size_mb": round(size_mb, 2),
            "modified": mtime
        })
    return results


@app.post("/api/data/clean")
def clean_sample_data():
    """Xóa sạch toàn bộ dữ liệu mẫu trong orders, bot_signals, bot_logs, daily_equity."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orders;")
        cursor.execute("DELETE FROM bot_signals;")
        cursor.execute("DELETE FROM bot_logs;")
        cursor.execute("DELETE FROM daily_equity;")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('orders', 'bot_signals', 'bot_logs');")
        conn.commit()
    return {"status": "success", "message": "Đã làm sạch toàn bộ dữ liệu mẫu"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)
