import sqlite3
import logging
from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

def get_connection():
    """Tạo kết nối đến SQLite Database."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_database():
    """Khởi tạo toàn bộ các bảng trong hệ thống."""
    commands = [
        # Bảng 1: orders (Lưu lệnh giao dịch)
        """
        CREATE TABLE IF NOT EXISTS orders (
            ticket_id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            order_type TEXT NOT NULL CHECK(order_type IN ('BUY', 'SELL')),
            lot_size REAL NOT NULL,
            open_time TIMESTAMP NOT NULL,
            open_price REAL NOT NULL,
            close_time TIMESTAMP,
            close_price REAL,
            stop_loss REAL,
            take_profit REAL,
            commission REAL DEFAULT 0.0,
            swap REAL DEFAULT 0.0,
            profit REAL DEFAULT 0.0,
            close_reason TEXT,
            status TEXT NOT NULL CHECK(status IN ('OPEN', 'CLOSED'))
        );
        """,
        # Bảng 2: bot_signals (Lưu tín hiệu và lý do AI ra lệnh)
        """
        CREATE TABLE IF NOT EXISTS bot_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            symbol TEXT NOT NULL,
            signal_type TEXT NOT NULL CHECK(signal_type IN ('BUY', 'SELL', 'HOLD')),
            confidence REAL,
            rsi_value REAL,
            atr_value REAL,
            adx_value REAL,
            executed INTEGER DEFAULT 0 CHECK(executed IN (0, 1)),
            order_ticket INTEGER,
            FOREIGN KEY(order_ticket) REFERENCES orders(ticket_id) ON DELETE SET NULL
        );
        """,
        # Bảng 3: daily_equity (Theo dõi biến động vốn)
        """
        CREATE TABLE IF NOT EXISTS daily_equity (
            date DATE PRIMARY KEY,
            balance REAL NOT NULL,
            equity REAL NOT NULL,
            floating_pnl REAL NOT NULL,
            total_trades INTEGER DEFAULT 0,
            win_trades INTEGER DEFAULT 0
        );
        """,
        # Bảng 4: bot_logs (Nhật ký lỗi và trạng thái hệ thống)
        """
        CREATE TABLE IF NOT EXISTS bot_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            log_level TEXT NOT NULL,
            module TEXT,
            message TEXT NOT NULL
        );
        """,
        # Tạo Index để tăng tốc độ truy vấn
        "CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);",
        "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);",
        "CREATE INDEX IF NOT EXISTS idx_signals_time ON bot_signals(timestamp);"
    ]

    with get_connection() as conn:
        cursor = conn.cursor()
        for cmd in commands:
            cursor.execute(cmd)
        conn.commit()
    
    logging.info(f"Khởi tạo Database thành công tại: {config.DB_PATH}")

if __name__ == "__main__":
    init_database()
