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
    """Khởi tạo và cập nhật schema toàn bộ các bảng trong hệ thống."""
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
            status TEXT NOT NULL CHECK(status IN ('OPEN', 'CLOSED')),
            market_case TEXT,
            rr_ratio REAL
        );
        """,
        # Bảng 2: bot_signals (Lưu tín hiệu và lý do AI ra lệnh)
        """
        CREATE TABLE IF NOT EXISTS bot_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            symbol TEXT NOT NULL,
            signal_type TEXT NOT NULL CHECK(signal_type IN ('BUY', 'SELL', 'HOLD', 'STRICT_NO_TRADE', 'WAIT_RETEST', 'CIRCUIT_BREAKER_LOCK')),
            confidence REAL,
            rsi_value REAL,
            atr_value REAL,
            adx_value REAL,
            market_case TEXT,
            regime TEXT,
            anomaly_score REAL,
            rr_ratio REAL,
            reason TEXT,
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
        # Bảng 4: app_settings (Cấu hình và đồng bộ số dư tài khoản)
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        # Migration an toàn nếu bảng cũ chưa có các cột mới
        cursor.execute("PRAGMA table_info(orders);")
        order_cols = [row[1] for row in cursor.fetchall()]
        if "market_case" not in order_cols:
            cursor.execute("ALTER TABLE orders ADD COLUMN market_case TEXT;")
        if "rr_ratio" not in order_cols:
            cursor.execute("ALTER TABLE orders ADD COLUMN rr_ratio REAL;")

        cursor.execute("PRAGMA table_info(bot_signals);")
        signal_cols = [row[1] for row in cursor.fetchall()]
        if "market_case" not in signal_cols:
            cursor.execute("ALTER TABLE bot_signals ADD COLUMN market_case TEXT;")
        if "regime" not in signal_cols:
            cursor.execute("ALTER TABLE bot_signals ADD COLUMN regime TEXT;")
        if "anomaly_score" not in signal_cols:
            cursor.execute("ALTER TABLE bot_signals ADD COLUMN anomaly_score REAL;")
        if "rr_ratio" not in signal_cols:
            cursor.execute("ALTER TABLE bot_signals ADD COLUMN rr_ratio REAL;")
        if "reason" not in signal_cols:
            cursor.execute("ALTER TABLE bot_signals ADD COLUMN reason TEXT;")

        conn.commit()
    
    logging.info(f"Khởi tạo và đồng bộ Database thành công tại: {config.DB_PATH}")


def get_setting(key: str, default: str = "") -> str:
    """Lấy giá trị cài đặt từ database."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_settings WHERE key = ?;", (key,))
            row = cursor.fetchone()
            return row[0] if row else default
    except Exception:
        return default


def set_setting(key: str, value: str) -> None:
    """Lưu giá trị cài đặt vào database."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP);", (key, value))
            conn.commit()
    except Exception as e:
        logging.error(f"Lỗi lưu setting {key}: {e}")


if __name__ == "__main__":
    init_database()
