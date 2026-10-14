import os
import glob
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
import numpy as np

from config import BASE_DIR, config
from db import get_connection
from mt5_connector import mt5, MT5Connector, IS_SIMULATION

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

app = FastAPI(title="AI Earning - Trading Terminal", version="1.0.0")

# Mount thư mục static
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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


def ensure_sample_data():
    """Tự động chèn dữ liệu mẫu vào SQLite nếu các bảng chưa có dữ liệu để hiển thị trực quan."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders;")
        order_count = cursor.fetchone()[0]

        if order_count == 0:
            now = datetime.now()
            # 1. Orders mẫu
            orders = [
                (10124891, "EURUSD", "BUY", 0.10, "2026-10-12 08:30:00", 1.0820, "2026-10-12 14:15:00", 1.0865, 1.0780, 1.0865, -0.70, 0.0, 45.00, "TAKE_PROFIT", "CLOSED"),
                (10124952, "EURUSD", "SELL", 0.15, "2026-10-13 09:00:00", 1.0870, "2026-10-13 16:45:00", 1.0850, 1.0910, 1.0850, -1.05, 0.15, 30.00, "TAKE_PROFIT", "CLOSED"),
                (10125010, "EURUSD", "BUY", 0.10, "2026-10-13 18:20:00", 1.0845, "2026-10-13 21:00:00", 1.0835, 1.0835, 1.0880, -0.70, 0.0, -10.00, "STOP_LOSS", "CLOSED"),
                (10125134, "EURUSD", "BUY", 0.20, "2026-10-14 06:10:00", 1.0852, None, None, 1.0810, 1.0920, -1.40, 0.0, 18.50, None, "OPEN")
            ]
            cursor.executemany("""
                INSERT OR IGNORE INTO orders 
                (ticket_id, symbol, order_type, lot_size, open_time, open_price, close_time, close_price, stop_loss, take_profit, commission, swap, profit, close_reason, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, orders)

            # 2. Bot Signals mẫu
            signals = [
                ("2026-10-12 08:25:00", "EURUSD", "BUY", 88.5, 28.4, 0.0018, 32.4, 1, 10124891),
                ("2026-10-13 08:55:00", "EURUSD", "SELL", 84.0, 72.8, 0.0020, 29.5, 1, 10124952),
                ("2026-10-13 18:15:00", "EURUSD", "BUY", 79.0, 31.2, 0.0016, 26.0, 1, 10125010),
                ("2026-10-14 06:05:00", "EURUSD", "BUY", 91.2, 26.5, 0.0022, 35.8, 1, 10125134),
                ("2026-10-14 07:30:00", "EURUSD", "HOLD", 54.0, 48.9, 0.0014, 18.2, 0, None)
            ]
            cursor.executemany("""
                INSERT INTO bot_signals (timestamp, symbol, signal_type, confidence, rsi_value, atr_value, adx_value, executed, order_ticket)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, signals)

            # 3. Daily Equity mẫu
            equity = [
                ("2026-10-08", 9800.0, 9800.0, 0.0, 0, 0),
                ("2026-10-09", 9850.0, 9850.0, 0.0, 2, 2),
                ("2026-10-10", 9920.0, 9920.0, 0.0, 3, 2),
                ("2026-10-11", 9935.0, 9935.0, 0.0, 1, 1),
                ("2026-10-12", 9980.0, 9980.0, 0.0, 2, 2),
                ("2026-10-13", 10000.0, 10000.0, 0.0, 2, 1),
                ("2026-10-14", 10000.0, 10018.5, 18.5, 1, 0),
            ]
            cursor.executemany("""
                INSERT OR IGNORE INTO daily_equity (date, balance, equity, floating_pnl, total_trades, win_trades)
                VALUES (?, ?, ?, ?, ?, ?);
            """, equity)

            # 4. Bot Logs mẫu
            logs = [
                ("INFO", "mt5_connector", f"Đã kết nối tài khoản demo {config.MT5_LOGIN} sàn {config.MT5_SERVER}"),
                ("INFO", "data_collector", "Đã đồng bộ 100,000 nến EURUSD M5 từ data storage"),
                ("INFO", "signal_engine", "Chỉ báo RSI chạm ngưỡng 26.5, hình thành tín hiệu BUY mạnh (Confidence: 91.2%)"),
                ("INFO", "risk_manager", "Khối lượng lệnh 0.20 lots thỏa mãn rủi ro tối đa 1.5% vốn"),
                ("INFO", "order_execution", "Khớp lệnh BUY ticket #10125134 tại 1.08520 thành công")
            ]
            cursor.executemany("""
                INSERT INTO bot_logs (log_level, module, message)
                VALUES (?, ?, ?);
            """, logs)
            conn.commit()


@app.on_event("startup")
def startup_event():
    ensure_sample_data()


@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """Trả về giao diện Dashboard chính."""
    html_file = BASE_DIR / "templates" / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Loading Dashboard...</h1>")


@app.get("/api/account")
def get_account_info():
    """Lấy thông tin tài khoản MT5 và trạng thái kết nối."""
    account_info = mt5.account_info() if mt5 else None
    
    # Tính toán tổng PnL và tỷ lệ thắng từ SQLite
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(profit) FROM orders WHERE status = 'CLOSED';")
        closed_trades, total_profit = cursor.fetchone()
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'CLOSED' AND profit > 0;")
        win_trades = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(profit) FROM orders WHERE status = 'OPEN';")
        floating_profit = cursor.fetchone()[0] or 0.0

    win_rate = (win_trades / closed_trades * 100) if closed_trades and closed_trades > 0 else 0.0

    return {
        "status": "connected",
        "is_simulation": IS_SIMULATION,
        "login": getattr(account_info, "login", config.MT5_LOGIN),
        "name": getattr(account_info, "name", "Trader Demo"),
        "server": getattr(account_info, "server", config.MT5_SERVER),
        "currency": getattr(account_info, "currency", "USD"),
        "balance": getattr(account_info, "balance", 10000.0),
        "equity": getattr(account_info, "equity", 10000.0) + floating_profit,
        "floating_pnl": floating_profit,
        "leverage": getattr(account_info, "leverage", 100),
        "closed_trades": closed_trades or 0,
        "win_rate": round(win_rate, 1),
        "total_profit": round(total_profit or 0.0, 2),
    }


@app.get("/api/candles")
def get_candles(symbol: str = "EURUSD", timeframe: str = "M5", limit: int = 1500):
    """
    Đọc dữ liệu nến từ Parquet file và trả về dữ liệu chuẩn cho TradingView Lightweight Charts.
    """
    data_dir = BASE_DIR / "data"
    # Tìm file parquet tương ứng
    pattern = str(data_dir / f"{symbol}_{timeframe}_*.parquet")
    files = glob.glob(pattern)

    if not files:
        # Thử tìm file bất kỳ trong data
        all_files = glob.glob(str(data_dir / "*.parquet"))
        if not all_files:
            return JSONResponse({"candles": [], "volume": [], "sma20": [], "sma50": [], "rsi": []})
        files = all_files

    # Chọn file mới nhất
    latest_file = max(files, key=os.path.getmtime)
    df = pd.read_parquet(latest_file)

    # Đảm bảo sắp xếp tăng dần theo thời gian
    df = df.sort_values(by="time").reset_index(drop=True)

    # Tính toán các chỉ báo
    df = calculate_indicators(df)

    # Cắt lấy số lượng nến gần nhất theo limit
    if limit > 0 and len(df) > limit:
        df = df.tail(limit).reset_index(drop=True)

    candles = []
    volumes = []
    sma20 = []
    sma50 = []
    rsi = []

    for _, row in df.iterrows():
        # Lightweight charts yêu cầu timestamp dạng Unix seconds (integer UTC)
        ts = int(row["time"].timestamp())
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

        if not pd.isna(row.get("sma20")):
            sma20.append({"time": ts, "value": round(float(row["sma20"]), 5)})

        if not pd.isna(row.get("sma50")):
            sma50.append({"time": ts, "value": round(float(row["sma50"]), 5)})

        if not pd.isna(row.get("rsi14")):
            rsi.append({"time": ts, "value": round(float(row["rsi14"]), 2)})

    return {
        "file_name": os.path.basename(latest_file),
        "total_candles": len(df),
        "candles": candles,
        "volume": volumes,
        "sma20": sma20,
        "sma50": sma50,
        "rsi": rsi
    }


@app.get("/api/orders")
def get_orders():
    """Lấy danh sách lệnh giao dịch từ SQLite."""
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
        orders = [dict(zip(columns, row)) for row in rows]
    return orders


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
