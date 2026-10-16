import logging
from pathlib import Path
import numpy as np
import pandas as pd
import pandas_ta as ta

from config import BASE_DIR

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
        Tính toán các chỉ báo kỹ thuật cốt lõi (Features).
        """
        logging.info("Đang tạo các features kỹ thuật...")
        df = df.copy()

        # 1. Động lượng (Momentum)
        df["rsi_14"] = ta.rsi(df["close"], length=14)
        df["rsi_7"] = ta.rsi(df["close"], length=7)

        # 2. Xu hướng (Trend)
        df["ema_20"] = ta.ema(df["close"], length=20)
        df["ema_50"] = ta.ema(df["close"], length=50)
        df["ema_200"] = ta.ema(df["close"], length=200)
        
        # Khoảng cách tương đối giữa giá và EMA (%)
        df["dist_ema_20"] = (df["close"] - df["ema_20"]) / df["ema_20"] * 100
        df["dist_ema_50"] = (df["close"] - df["ema_50"]) / df["ema_50"] * 100

        # MACD
        macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            macd_col = next((c for c in macd.columns if c.startswith("MACD_")), None)
            macds_col = next((c for c in macd.columns if c.startswith("MACDs_")), None)
            macdh_col = next((c for c in macd.columns if c.startswith("MACDh_")), None)
            if macd_col and macds_col and macdh_col:
                df["macd"] = macd[macd_col]
                df["macd_signal"] = macd[macds_col]
                df["macd_hist"] = macd[macdh_col]

        # 3. Biến động (Volatility)
        df["atr_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)
        df["atr_pct"] = df["atr_14"] / df["close"] * 100  # ATR theo tỷ lệ % giá

        bb = ta.bbands(df["close"], length=20, std=2)
        if bb is not None and not bb.empty:
            bbu_col = next((c for c in bb.columns if c.startswith("BBU")), None)
            bbl_col = next((c for c in bb.columns if c.startswith("BBL")), None)
            if bbu_col and bbl_col:
                df["bb_width"] = (bb[bbu_col] - bb[bbl_col]) / df["close"] * 100
                # Vị trí giá trong dải Bollinger (%B: 0 = chạm đáy, 1 = chạm đỉnh)
                df["bb_pct"] = (df["close"] - bb[bbl_col]) / (bb[bbu_col] - bb[bbl_col] + 1e-9)

        # 4. Đặc trưng nến (Candlestick Geometry)
        body = (df["close"] - df["open"]).abs()
        candle_range = df["high"] - df["low"] + 1e-9
        df["body_ratio"] = body / candle_range
        df["return_1"] = df["close"].pct_change(1) * 100
        df["return_3"] = df["close"].pct_change(3) * 100
        df["return_5"] = df["close"].pct_change(5) * 100

        # 5. Khối lượng Tick
        df["vol_sma_20"] = ta.sma(df["tick_volume"], length=20)
        df["vol_ratio"] = df["tick_volume"] / (df["vol_sma_20"] + 1e-9)

        # 6. Yếu tố thời gian (Time Features - Forex có tính chu kỳ phiên London/New York)
        time_series = pd.to_datetime(df["time"], utc=True)
        df["hour"] = time_series.dt.hour
        df["dayofweek"] = time_series.dt.dayofweek

        return df

    def apply_triple_barrier_labels(
        self,
        df: pd.DataFrame,
        horizon_bars: int = 12,       # Số nến tối đa giữ lệnh (M5 x 12 = 1 giờ)
        tp_multiplier: float = 1.5,   # TP = 1.5 x ATR
        sl_multiplier: float = 1.0    # SL = 1.0 x ATR (Tỷ lệ Risk:Reward = 1:1.5)
    ) -> pd.DataFrame:
        """
        Gán nhãn BUY cho bài toán Classification:
        - Nhãn 1: Giá chạm Take-Profit trước khi chạm Stop-Loss trong vòng horizon_bars.
        - Nhãn 0: Chạm Stop-Loss trước hoặc hết horizon_bars mà không chạm TP.
        """
        logging.info(f"Đang gán nhãn Triple Barrier (Horizon={horizon_bars} bars, TP={tp_multiplier}xATR, SL={sl_multiplier}xATR)...")
        df = df.copy()

        n = len(df)
        labels = np.zeros(n, dtype=int)
        
        close_prices = df["close"].values
        high_prices = df["high"].values
        low_prices = df["low"].values
        atr_values = df["atr_14"].values

        for i in range(n - horizon_bars):
            entry_price = close_prices[i]
            current_atr = atr_values[i]

            if np.isnan(current_atr) or current_atr <= 0:
                continue

            take_profit = entry_price + (tp_multiplier * current_atr)
            stop_loss = entry_price - (sl_multiplier * current_atr)

            # Quét nến tương lai trong horizon_bars
            for h in range(1, horizon_bars + 1):
                future_idx = i + h
                future_high = high_prices[future_idx]
                future_low = low_prices[future_idx]

                # Nếu nến tương lai quét SL trước -> Thua (0)
                if future_low <= stop_loss:
                    labels[i] = 0
                    break

                # Nếu nến tương lai chạm TP trước -> Thắng (1)
                if future_high >= take_profit:
                    labels[i] = 1
                    break

        df["target"] = labels
        # Loại bỏ horizon_bars cây nến cuối cùng vì chưa rõ kết quả tương lai
        df = df.head(n - horizon_bars).copy()
        
        # Xóa các dòng có NaN do tính chỉ báo ở đầu chu kỳ
        df = df.dropna().reset_index(drop=True)

        win_rate = df["target"].mean() * 100
        logging.info(f"Gán nhãn hoàn tất! Số mẫu: {len(df):,} | Tỷ lệ nhãn 1 (Win): {win_rate:.2f}%")
        return df

    def run(self, output_filename: str = "processed_dataset.parquet") -> Path:
        df_raw = self.load_data()
        df_featured = self.build_features(df_raw)
        df_final = self.apply_triple_barrier_labels(df_featured)

        out_path = self.data_path.parent / output_filename
        df_final.to_parquet(out_path, engine="pyarrow", compression="snappy", index=False)
        logging.info(f"Đã lưu tập dataset đã xử lý tại: {out_path}")
        return out_path


if __name__ == "__main__":
    # Tìm file nến Parquet vừa tải ở TASK-2.1
    data_dir = BASE_DIR / "data"
    parquet_files = [f for f in data_dir.glob("*.parquet") if not f.name.startswith("processed_")]

    if not parquet_files:
        logging.error("Không tìm thấy file parquet nào trong thư mục data/. Hãy chạy data_collector.py trước.")
    else:
        # Lấy file nến thô đầu tiên tìm được
        input_file = parquet_files[0]
        engineer = FeatureEngineer(input_file)
        processed_file = engineer.run()
