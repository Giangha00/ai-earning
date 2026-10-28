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

config = Config()
