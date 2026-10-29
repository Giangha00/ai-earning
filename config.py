import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

class Config:
    MT5_LOGIN: int = int(os.getenv("MT5_LOGIN") or 0)
    MT5_PASSWORD: str = os.getenv("MT5_PASSWORD", "")
    MT5_SERVER: str = os.getenv("MT5_SERVER", "")
    MT5_PATH: str | None = os.getenv("MT5_PATH") or None
    MT5_BALANCE: float = float(os.getenv("MT5_BALANCE") or 10000.0)

    DB_PATH: Path = BASE_DIR / os.getenv("DB_NAME", "trading_bot.db")
    LOG_PATH: Path = BASE_DIR / "trading.log"

    # Các biến cấu hình động điều khiển Bot AI (v2 - Tự động đồng bộ theo số dư ví Exness MT5)
    INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL") or MT5_BALANCE)
    CUSTOM_LOT_SIZE: float = float(os.getenv("CUSTOM_LOT_SIZE") or 0.01)
    TARGET_PROFIT_GOAL: float = float(os.getenv("TARGET_PROFIT_GOAL") or (INITIAL_CAPITAL + 500.0))
    BOT_RUNNING: bool = os.getenv("BOT_RUNNING", "false").lower() in ("true", "1", "yes")


config = Config()

# Đồng bộ biến cấp module để hỗ trợ cả `import config` và `from config import config`
INITIAL_CAPITAL = config.INITIAL_CAPITAL
CUSTOM_LOT_SIZE = config.CUSTOM_LOT_SIZE
TARGET_PROFIT_GOAL = config.TARGET_PROFIT_GOAL
BOT_RUNNING = config.BOT_RUNNING
