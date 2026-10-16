import importlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

from config import BASE_DIR
from mt5_connector import MT5Connector

# Import MetaTrader5 an toàn (native trên Windows, hoặc fallback giả lập trên macOS/Linux)
try:
    mt5 = importlib.import_module("MetaTrader5")
except (ImportError, ModuleNotFoundError):
    from mt5_connector import mt5

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

# Mapping các khung thời gian thường dùng
TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


class DataCollector:
    def __init__(self, output_dir: str = "data"):
        self.output_dir = BASE_DIR / output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_symbol_visible(self, symbol: str) -> bool:
        """Đảm bảo symbol đã được kích hoạt trong Market Watch của MT5."""
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logging.error(f"Không tìm thấy mã {symbol} trên sàn.")
            return False

        if not symbol_info.visible:
            logging.info(f"Kích hoạt {symbol} vào Market Watch...")
            if not mt5.symbol_select(symbol, True):
                logging.error(f"Không thể kích hoạt {symbol} vào Market Watch.")
                return False
        return True

    def fetch_by_range(
        self,
        symbol: str,
        timeframe_str: str,
        start_date: datetime,
        end_date: datetime
    ) -> pd.DataFrame:
        """
        Kéo dữ liệu nến trong khoảng thời gian từ start_date đến end_date.
        """
        if timeframe_str not in TIMEFRAME_MAP:
            raise ValueError(f"Khung thời gian '{timeframe_str}' không hợp lệ. Chọn: {list(TIMEFRAME_MAP.keys())}")

        if not self._ensure_symbol_visible(symbol):
            return pd.DataFrame()

        tf = TIMEFRAME_MAP[timeframe_str]
        logging.info(f"Đang tải {symbol} [{timeframe_str}] từ {start_date} đến {end_date}...")

        # MT5 yêu cầu thời gian timezone UTC
        rates = mt5.copy_rates_range(symbol, tf, start_date, end_date)

        if rates is None or len(rates) == 0:
            logging.warning(f"Không nhận được dữ liệu nào cho {symbol} [{timeframe_str}]. Lỗi MT5: {mt5.last_error()}")
            return pd.DataFrame()

        df = self._process_rates(rates)
        logging.info(f"Đã tải thành công {len(df):,} cây nến cho {symbol}.")
        return df

    def fetch_by_count(
        self,
        symbol: str,
        timeframe_str: str,
        count: int = 50000,
        start_pos: int = 0
    ) -> pd.DataFrame:
        """
        Kéo `count` cây nến gần nhất tính từ vị trí `start_pos`.
        """
        if timeframe_str not in TIMEFRAME_MAP:
            raise ValueError(f"Khung thời gian '{timeframe_str}' không hợp lệ.")

        if not self._ensure_symbol_visible(symbol):
            return pd.DataFrame()

        tf = TIMEFRAME_MAP[timeframe_str]
        logging.info(f"Đang tải {count:,} nến gần nhất của {symbol} [{timeframe_str}]...")

        rates = mt5.copy_rates_from_pos(symbol, tf, start_pos, count)

        if rates is None or len(rates) == 0:
            logging.warning(f"Không tải được dữ liệu cho {symbol}. Lỗi MT5: {mt5.last_error()}")
            return pd.DataFrame()

        df = self._process_rates(rates)
        logging.info(f"Đã tải thành công {len(df):,} cây nến cho {symbol}.")
        return df

    def _process_rates(self, rates) -> pd.DataFrame:
        """Chuẩn hóa dữ liệu thô từ MT5 thành DataFrame sạch."""
        df = pd.DataFrame(rates)
        # Chuyển timestamp Unix (giây) sang datetime UTC
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)

        # Chọn và sắp xếp lại các cột cần thiết
        columns = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
        existing_cols = [c for c in columns if c in df.columns]
        df = df[existing_cols]

        # Sắp xếp thời gian tăng dần và loại bỏ trùng lặp nếu có
        df = df.sort_values(by=["time"]).drop_duplicates(subset=["time"]).reset_index(drop=True)
        return df

    def save_to_parquet(self, df: pd.DataFrame, symbol: str, timeframe_str: str) -> Path | None:
        """Lưu DataFrame ra file Parquet được nén chuẩn Snappy."""
        if df.empty:
            logging.warning("DataFrame rỗng, bỏ qua thao tác lưu file.")
            return None

        # Đặt tên file theo chuẩn: SYMBOL_TIMEFRAME_FROM_TO.parquet
        start_str = df["time"].iloc[0].strftime("%Y%m%d")
        end_str = df["time"].iloc[-1].strftime("%Y%m%d")
        file_name = f"{symbol}_{timeframe_str}_{start_str}_{end_str}.parquet"
        file_path = self.output_dir / file_name

        # Lưu bằng pyarrow với nén snappy
        df.to_parquet(file_path, engine="pyarrow", compression="snappy", index=False)
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

        logging.info(f"Đã lưu dữ liệu vào: {file_path} (Dung lượng: {file_size_mb:.2f} MB)")
        return file_path


def main():
    # 1. Kết nối MT5
    if not MT5Connector.connect():
        logging.error("Không thể kết nối MT5. Dừng chương trình.")
        return

    try:
        collector = DataCollector(output_dir="data")

        # Cấu hình tải dữ liệu
        symbol = "EURUSD"       # Cặp tiền bạn muốn đánh (hoặc 'XAUUSD', 'GBPUSD'...)
        timeframe = "M5"        # Khung nến: 'M5' hoặc 'M15'

        # Cách 1: Tải theo số nến gần nhất (ví dụ: 100,000 nến M5 tương đương ~1 năm giao dịch)
        df_count = collector.fetch_by_count(symbol=symbol, timeframe_str=timeframe, count=100000)

        # Cách 2: (Tuỳ chọn) Tải theo khoảng ngày cụ thể:
        # start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        # end = datetime(2026, 10, 1, tzinfo=timezone.utc)
        # df_range = collector.fetch_by_range(symbol=symbol, timeframe_str=timeframe, start_date=start, end_date=end)

        if not df_count.empty:
            saved_path = collector.save_to_parquet(df_count, symbol=symbol, timeframe_str=timeframe)
            if saved_path is not None:
                # Đọc kiểm tra lại file Parquet
                df_check = pd.read_parquet(saved_path)
                logging.info(f"Kiểm tra file vừa lưu: {len(df_check):,} dòng")
                logging.info(f"Khung thời gian từ {df_check['time'].min()} đến {df_check['time'].max()}")
                print("\n5 dòng dữ liệu đầu tiên:")
                print(df_check.head())

    finally:
        # Luôn đảm bảo đóng kết nối MT5 khi hoàn tất
        MT5Connector.disconnect()


if __name__ == "__main__":
    main()
