import logging
from pathlib import Path
import numpy as np
import pandas as pd

from config import BASE_DIR
from create_training_pool import compute_training_pool_features

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")


class FeatureEngineer:
    def __init__(self, data_path: Path):
        self.data_path = data_path

    def load_data(self) -> pd.DataFrame:
        """Đọc dữ liệu nến từ file Parquet."""
        logging.info(f"Đang đọc dữ liệu từ {self.data_path}...")
        df = pd.read_parquet(self.data_path)
        return df

    def build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Tính toán đầy đủ ma trận đặc trưng Training Pool (Chương 2 & Chương 4):
        - Đặc trưng Nến: body_size, body_ratio, upper_wick, lower_wick
        - Đặc trưng Biến động: tr, atr5, atr20, atr_ratio = ATR(5) / ATR(20)
        - Đặc trưng Cấu trúc: dist_to_support, dist_to_resistance
        - Đặc trưng Thời gian: session_code (0=Asia, 1=Europe, 2=US)
        - Các chỉ báo kỹ thuật kết hợp: RSI, EMA, MACD, Bollinger Bands, ATR14, Volume Ratio
        """
        logging.info("Đang tạo các features kỹ thuật chuẩn Training Pool...")
        pip = 0.0001 if "JPY" not in str(self.data_path) else 0.01
        return compute_training_pool_features(df, pip=pip)

    def apply_triple_barrier_labels(
        self,
        df: pd.DataFrame,
        horizon_bars: int = 100,      # Quét tối đa 100 nến tương lai theo chuẩn Chương 4
        tp_multiplier: float = 2.0,   # TP = 2R (Tỷ lệ Risk:Reward = 1:2)
        sl_multiplier: float = 1.0,   # SL = 1R
    ) -> pd.DataFrame:
        """
        Gán nhãn tự động dựa trên R:R = 1:2 (Chương 2 & Chương 3 Bước 2):
        - Nhãn y = 1 (Lệnh Thắng / Hợp Lệ): Giá chạm Take Profit (TP = 2R) trước khi chạm Stop Loss (SL = 1R).
        - Nhãn y = 0 (Lệnh Thua / Nhiễu): Giá bị dính Stop Loss trước hoặc giằng co không đạt mục tiêu 2R.
        """
        logging.info(
            f"Đang gán nhãn Training Pool R:R = 1:2 (Horizon={horizon_bars} bars, TP={tp_multiplier}R, SL={sl_multiplier}R)..."
        )
        df = df.copy()

        n = len(df)
        labels = np.zeros(n, dtype=int)

        close_prices = df["close"].values
        high_prices = df["high"].values
        low_prices = df["low"].values
        atr_values = df["atr_14"].values
        pip = 0.0001 if "JPY" not in str(self.data_path) else 0.01

        for i in range(n - horizon_bars):
            entry_price = close_prices[i]
            current_atr = atr_values[i]

            if np.isnan(current_atr) or current_atr <= 0:
                risk_dist = 15 * pip
            else:
                risk_dist = max(float(current_atr), 10 * pip)

            stop_loss = entry_price - (sl_multiplier * risk_dist)
            take_profit = entry_price + (tp_multiplier * risk_dist)

            for h in range(1, horizon_bars + 1):
                future_idx = i + h
                future_high = high_prices[future_idx]
                future_low = low_prices[future_idx]

                # Chạm SL trước -> y = 0
                if future_low <= stop_loss:
                    labels[i] = 0
                    break

                # Chạm TP trước -> y = 1
                if future_high >= take_profit:
                    labels[i] = 1
                    break

        df["target"] = labels
        df = df.head(n - horizon_bars).copy()
        df = df.dropna().reset_index(drop=True)

        win_rate = df["target"].mean() * 100
        logging.info(f"Gán nhãn hoàn tất! Số mẫu: {len(df):,} | Tỷ lệ nhãn y=1 (TP=2R): {win_rate:.2f}%")
        return df

    def run(self, output_filename: str = "processed_dataset.parquet") -> Path:
        df_raw = self.load_data()
        df_featured = self.build_features(df_raw)
        df_final = self.apply_triple_barrier_labels(df_featured)

        out_path = self.data_path.parent / output_filename
        csv_path = self.data_path.parent / "training_pool.csv"

        df_final.to_parquet(out_path, engine="pyarrow", compression="snappy", index=False)
        df_final.to_csv(csv_path, index=False)
        logging.info(f"Đã lưu tập Training Pool tại: {csv_path} và {out_path}")
        return out_path


if __name__ == "__main__":
    data_dir = BASE_DIR / "data"
    parquet_files = [f for f in data_dir.glob("*.parquet") if not f.name.startswith("processed_")]

    if not parquet_files:
        logging.error("Không tìm thấy file parquet nào trong thư mục data/. Hãy chạy create_training_pool.py trước.")
    else:
        input_file = parquet_files[0]
        engineer = FeatureEngineer(input_file)
        processed_file = engineer.run()
