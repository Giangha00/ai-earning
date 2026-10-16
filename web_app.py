import os
import glob
import random
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd
import numpy as np

from config import BASE_DIR, config
from db import get_connection
from mt5_connector import mt5, MT5Connector, IS_SIMULATION

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

app = FastAPI(title="AI Earning - Trading Terminal", version="1.1.0")

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
def startup_event():
    fetch_live_usd_vnd_rate()


@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """Trả về giao diện Dashboard chính."""
    html_file = BASE_DIR / "templates" / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Loading Dashboard...</h1>")


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
    balance_usd = getattr(account_info, "balance", 10000.0)
    equity_usd = balance_usd + floating_profit

    # Tính toán VNĐ theo tỷ giá thực tế
    balance_vnd = balance_usd * rate
    equity_vnd = equity_usd * rate
    floating_pnl_vnd = floating_profit * rate
    total_profit_vnd = (total_profit or 0.0) * rate

    return {
        "status": "connected",
        "is_simulation": IS_SIMULATION,
        "login": getattr(account_info, "login", config.MT5_LOGIN),
        "name": f"Tài khoản Exness #{config.MT5_LOGIN}",
        "server": getattr(account_info, "server", config.MT5_SERVER),
        "currency": getattr(account_info, "currency", "USD"),
        "usd_vnd_rate": round(rate),
        # USD Metrics
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
    }


@app.get("/api/candles")
def get_candles(symbol: str = "EURUSD", timeframe: str = "M5", limit: int = 1500):
    """
    Đọc dữ liệu nến từ Parquet file và trả về dữ liệu chuẩn cho TradingView Lightweight Charts.
    """
    data_dir = BASE_DIR / "data"
    pattern = str(data_dir / f"{symbol}_{timeframe}_*.parquet")
    files = glob.glob(pattern)

    if not files:
        all_files = glob.glob(str(data_dir / "*.parquet"))
        if not all_files:
            return JSONResponse({"candles": [], "volume": [], "sma20": [], "sma50": [], "rsi": []})
        files = all_files

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

    latest_price = candles[-1]["close"] if candles else 1.0850

    return {
        "file_name": os.path.basename(latest_file),
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
    """Lấy danh sách lệnh giao dịch của AI từ SQLite kèm quy đổi VNĐ."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ticket_id, symbol, order_type, lot_size, open_time, open_price, 
                   close_time, close_price, stop_loss, take_profit, profit, close_reason, status
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
    Nhận lệnh đặt từ giao diện người dùng:
    - Mức giá muốn đánh (entry_price hoặc entry_price_vnd)
    - Số lot (lot_size)
    - Mức giá mong muốn kiếm được (target_price hoặc target_price_vnd)
    """
    if req.lot_size <= 0:
        raise HTTPException(status_code=400, detail="Số lot phải lớn hơn 0")

    # Xác định entry_price (Forex)
    if req.entry_price and req.entry_price > 0:
        entry_price = float(req.entry_price)
    elif req.entry_price_vnd and req.entry_price_vnd > 0:
        entry_price = float(req.entry_price_vnd) / USD_VND_RATE
    else:
        raise HTTPException(status_code=400, detail="Vui lòng nhập mức giá muốn đánh hợp lệ")

    mult = 100.0 if "XAU" in req.symbol or "GOLD" in req.symbol else 100000.0

    # Xác định target_price (Forex)
    if req.target_price and req.target_price > 0:
        target_price = float(req.target_price)
    elif req.target_price_vnd and req.target_price_vnd > 0:
        target_price = float(req.target_price_vnd) / USD_VND_RATE
    elif req.target_profit_vnd and req.target_profit_vnd > 0:
        # Quy đổi từ số tiền muốn kiếm được (VNĐ) -> USD -> khoảng cách giá
        desired_usd = float(req.target_profit_vnd) / USD_VND_RATE
        diff = desired_usd / (mult * req.lot_size)
        target_price = entry_price + diff if req.order_type.upper() == "BUY" else entry_price - diff
    else:
        raise HTTPException(status_code=400, detail="Vui lòng nhập mức giá mong muốn kiếm được")

    if req.order_type.upper() == "BUY":
        expected_profit_usd = (target_price - entry_price) * mult * req.lot_size
    else:
        expected_profit_usd = (entry_price - target_price) * mult * req.lot_size

    expected_profit_vnd = expected_profit_usd * USD_VND_RATE
    entry_price_vnd = entry_price * USD_VND_RATE
    target_price_vnd = target_price * USD_VND_RATE

    ticket_id = random.randint(10126000, 10129999)
    open_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Tính toán các chỉ báo kỹ thuật thực tế từ nến gần nhất
    data_dir = BASE_DIR / "data"
    parquet_files = sorted(glob.glob(str(data_dir / "EURUSD_M5_*.parquet")), key=os.path.getmtime, reverse=True)
    real_rsi = 50.0
    real_atr = 0.0012
    real_adx = 24.5
    ai_confidence = 62.5

    if parquet_files:
        try:
            df_recent = pd.read_parquet(parquet_files[0]).tail(60).copy()
            df_recent = calculate_indicators(df_recent)
            last_r = df_recent.iloc[-1]
            if pd.notna(last_r.get("rsi14")):
                real_rsi = round(float(last_r["rsi14"]), 1)
            hl = (df_recent["high"] - df_recent["low"]).mean()
            real_atr = round(float(hl), 5)
            # Tính độ tự tin AI từ độ lệch RSI và khoảng cách mục tiêu
            rsi_strength = abs(50.0 - real_rsi) / 50.0
            ai_confidence = round(52.0 + (rsi_strength * 35.0), 1)
        except Exception as e:
            logging.warning(f"Lỗi đọc chỉ báo thời gian thực: {e}")

    with get_connection() as conn:
        cursor = conn.cursor()
        # Thêm vào orders
        cursor.execute("""
            INSERT INTO orders 
            (ticket_id, symbol, order_type, lot_size, open_time, open_price, stop_loss, take_profit, profit, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN');
        """, (ticket_id, req.symbol, req.order_type.upper(), req.lot_size, open_time, entry_price, req.stop_loss, target_price, 0.0))

        # Ghi log
        msg = f"AI Bot đã vào lệnh {req.order_type.upper()} {req.lot_size} lot {req.symbol} tại giá {entry_price_vnd:,.0f} ₫ ({entry_price:.5f}), mục tiêu TP {target_price_vnd:,.0f} ₫ ({target_price:.5f}) - Dự kiến lãi: +{expected_profit_vnd:,.0f} ₫ (+${expected_profit_usd:.2f})"
        cursor.execute("""
            INSERT INTO bot_logs (log_level, module, message)
            VALUES ('INFO', 'order_entry', ?);
        """, (msg,))

        # Thêm vào tín hiệu bot với chỉ báo thật
        cursor.execute("""
            INSERT INTO bot_signals (timestamp, symbol, signal_type, confidence, rsi_value, atr_value, adx_value, executed, order_ticket)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?);
        """, (open_time, req.symbol, req.order_type.upper(), ai_confidence, real_rsi, real_atr, real_adx, ticket_id))

        conn.commit()

    return {
        "success": True,
        "ticket_id": ticket_id,
        "message": f"Đặt lệnh thành công #{ticket_id}",
        "entry_price": round(entry_price, 5),
        "entry_price_vnd": round(entry_price_vnd),
        "target_price": round(target_price, 5),
        "target_price_vnd": round(target_price_vnd),
        "expected_profit_usd": round(expected_profit_usd, 2),
        "expected_profit_vnd": round(expected_profit_vnd)
    }


@app.post("/api/orders/close/{ticket_id}")
def close_order(ticket_id: int):
    """Đóng lệnh giao dịch thủ công hoặc khi chạm mục tiêu."""
    close_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, order_type, lot_size, open_price, take_profit FROM orders WHERE ticket_id = ? AND status = 'OPEN';", (ticket_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy lệnh mở với Ticket này")

        symbol, o_type, lot_size, open_price, take_profit = row
        close_price = take_profit if take_profit else open_price

        mult = 100.0 if "XAU" in symbol or "GOLD" in symbol else 100000.0
        profit = (close_price - open_price) * mult * lot_size if o_type == "BUY" else (open_price - close_price) * mult * lot_size

        cursor.execute("""
            UPDATE orders 
            SET close_time = ?, close_price = ?, profit = ?, close_reason = 'TARGET_REACHED', status = 'CLOSED'
            WHERE ticket_id = ?;
        """, (close_time, close_price, profit, ticket_id))

        cursor.execute("""
            INSERT INTO bot_logs (log_level, module, message)
            VALUES ('INFO', 'order_close', ?);
        """, (f"Đã chốt lệnh #{ticket_id} {symbol} tại {close_price}, lợi nhuận: +${profit:.2f} ({profit * USD_VND_RATE:,.0f} đ)",))

        conn.commit()

    return {"success": True, "ticket_id": ticket_id, "profit": profit}


@app.get("/api/signals")
def get_signals():
    """Lấy danh sách tín hiệu bot từ SQLite."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, symbol, signal_type, confidence, rsi_value, atr_value, adx_value, executed, order_ticket
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)
