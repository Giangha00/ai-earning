import os
from pathlib import Path
from typing import Dict
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# 1. Cài đặt ngưỡng Spread tối đa (Pips) - Mục 2 Tài liệu Nâng cấp Spread, Commission & Lot Size
MAX_ALLOWED_SPREAD: Dict[str, float] = {
    "EURUSD": 1.5,   # Trần 1.5 pips cho EURUSD
    "GBPUSD": 2.0,   # Trần 2.0 pips cho GBPUSD
    "USDJPY": 1.8,   # Trần 1.8 pips cho USDJPY
    "XAUUSD": 3.5,   # Trần 3.5 pips (0.35 giá) cho Vàng
    "DEFAULT": 2.0,
}

# 2. Cấu hình Rủi ro 1R & Phí Hoa Hồng Round-Turn (Mục 3, 4, 5 Tài liệu)
RISK_PER_TRADE: float = float(os.getenv("RISK_PER_TRADE") or 0.01)
COMMISSION_PER_LOT_USD: float = float(os.getenv("COMMISSION_PER_LOT_USD") or 7.0)
COMMISSION_BUFFER_PIPS: float = float(os.getenv("COMMISSION_BUFFER_PIPS") or 0.7)
USE_CUSTOM_LOT: bool = os.getenv("USE_CUSTOM_LOT", "false").lower() in ("true", "1", "yes")


class Config:
    MT5_LOGIN: int = int(os.getenv("MT5_LOGIN") or 0)
    MT5_PASSWORD: str = os.getenv("MT5_PASSWORD", "")
    MT5_SERVER: str = os.getenv("MT5_SERVER", "")
    MT5_PATH: str | None = os.getenv("MT5_PATH") or None
    MT5_BALANCE: float = float(os.getenv("MT5_BALANCE") or 10000.0)

    DB_PATH: Path = BASE_DIR / os.getenv("DB_NAME", "trading_bot.db")
    LOG_PATH: Path = BASE_DIR / "trading.log"

    # Bộ lọc Spread tối đa & Phí Hoa Hồng Round-Turn (Mục 2, 3, 4, 5)
    MAX_ALLOWED_SPREAD: Dict[str, float] = MAX_ALLOWED_SPREAD
    RISK_PER_TRADE: float = RISK_PER_TRADE
    COMMISSION_PER_LOT_USD: float = COMMISSION_PER_LOT_USD
    COMMISSION_BUFFER_PIPS: float = COMMISSION_BUFFER_PIPS
    USE_CUSTOM_LOT: bool = USE_CUSTOM_LOT

    # Các biến cấu hình động điều khiển Bot AI (v2 - Đơn vị chuẩn USD)
    INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL") or 100.0)
    CUSTOM_LOT_SIZE: float = float(os.getenv("CUSTOM_LOT_SIZE") or 0.01)
    TARGET_PROFIT_GOAL: float = float(os.getenv("TARGET_PROFIT_GOAL") or 200.0)
    BOT_RUNNING: bool = os.getenv("BOT_RUNNING", "false").lower() in ("true", "1", "yes")


config = Config()

# Đồng bộ biến cấp module để hỗ trợ cả `import config` và `from config import config`
INITIAL_CAPITAL = config.INITIAL_CAPITAL
CUSTOM_LOT_SIZE = config.CUSTOM_LOT_SIZE
TARGET_PROFIT_GOAL = config.TARGET_PROFIT_GOAL
BOT_RUNNING = config.BOT_RUNNING
