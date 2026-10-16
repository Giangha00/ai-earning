import logging
from pathlib import Path
import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import BASE_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")


class Backtester:
    def __init__(
        self,
        dataset_path: Path,
        model_path: Path,
        initial_balance: float = 100000.0,  # Vốn khởi điểm: 100,000 VNĐ (hoặc Cent/USD)
        risk_per_trade: float = 0.02,       # Rủi ro 2% vốn trên mỗi lệnh
        threshold: float = 0.55,            # Ngưỡng xác suất AI để kích hoạt vào lệnh
        tp_multiplier: float = 1.5,         # TP = 1.5 x ATR
        sl_multiplier: float = 1.0,         # SL = 1.0 x ATR
        horizon_bars: int = 12,             # Giữ tối đa 12 nến (1 giờ trên nến M5)
        default_spread_pips: float = 1.5,   # Spread ước lượng (1.5 pips nếu cột spread rỗng)
    ):
        self.dataset_path = dataset_path
        self.model_path = model_path
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.threshold = threshold
        self.tp_multiplier = tp_multiplier
        self.sl_multiplier = sl_multiplier
        self.horizon_bars = horizon_bars
        self.default_spread_pips = default_spread_pips

    def load_data_and_model(self):
        logging.info("Đang nạp mô hình AI...")
        payload = joblib.load(self.model_path)
        model = payload["model"]
        features = payload["features"]

        logging.info("Đang nạp dữ liệu kiểm thử...")
        df = pd.read_parquet(self.dataset_path).sort_values("time").reset_index(drop=True)

        # Lấy đúng 15% tập Test (Out-of-sample) ở cuối như TASK-3.1
        val_end = int(len(df) * 0.85)
        test_df = df.iloc[val_end:].copy().reset_index(drop=True)

        logging.info(f"Kích thước tập Test Backtest: {len(test_df):,} nến")
        logging.info(f"Thời gian test từ {test_df['time'].min()} đến {test_df['time'].max()}")

        # Dự đoán xác suất với Model
        X_test = test_df[features]
        test_df["ai_prob"] = model.predict_proba(X_test)[:, 1]

        return test_df

    def run(self) -> pd.DataFrame:
        df = self.load_data_and_model()
        logging.info("Bắt đầu mô phỏng giao dịch chi tiết từng nến...")

        balance = self.initial_balance
        equity_curve = [balance]
        timestamps = [df["time"].iloc[0]]
        trades = []

        n = len(df)
        i = 0

        while i < n - self.horizon_bars:
            prob = df["ai_prob"].iloc[i]

            # Kiểm tra điều kiện kích hoạt lệnh BUY
            if prob >= self.threshold:
                entry_time = df["time"].iloc[i]
                close_price = df["close"].iloc[i]
                atr = df["atr_14"].iloc[i]

                # Xử lý Spread (nếu có cột spread thì dùng, nếu không thì quy đổi pips sang giá)
                point = 0.00001 if "JPY" not in str(self.dataset_path) else 0.001
                spread = (
                    df["spread"].iloc[i] * point
                    if "spread" in df.columns and df["spread"].iloc[i] > 0
                    else self.default_spread_pips * 10 * point
                )

                # Giá vào lệnh BUY = Close + Spread
                entry_price = close_price + spread
                sl_price = entry_price - (self.sl_multiplier * atr)
                tp_price = entry_price + (self.tp_multiplier * atr)

                risk_distance = entry_price - sl_price
                if risk_distance <= 0:
                    i += 1
                    continue

                # Quản trị vốn: Số tiền chấp nhận rủi ro trên 1 lệnh
                risk_amount = balance * self.risk_per_trade

                # Quét các cây nến tiếp theo
                exit_price = None
                exit_time = None
                exit_reason = None
                bars_held = 0

                for h in range(1, self.horizon_bars + 1):
                    current_idx = i + h
                    future_high = df["high"].iloc[current_idx]
                    future_low = df["low"].iloc[current_idx]
                    future_time = df["time"].iloc[current_idx]
                    bars_held = h

                    # Kiểm tra dính SL trước
                    if future_low <= sl_price:
                        exit_price = sl_price
                        exit_time = future_time
                        exit_reason = "HIT_SL"
                        break

                    # Kiểm tra dính TP trước
                    if future_high >= tp_price:
                        exit_price = tp_price
                        exit_time = future_time
                        exit_reason = "HIT_TP"
                        break

                # Nếu hết horizon_bars mà chưa chạm SL/TP -> Đóng theo giá Close hiện tại
                if exit_price is None:
                    exit_idx = i + self.horizon_bars
                    exit_price = df["close"].iloc[exit_idx]
                    exit_time = df["time"].iloc[exit_idx]
                    exit_reason = "TIME_OUT"
                    bars_held = self.horizon_bars

                # Tính PnL
                pnl_ratio = (exit_price - entry_price) / risk_distance
                pnl_money = risk_amount * pnl_ratio
                balance += pnl_money

                # Ghi nhận trade
                trades.append({
                    "entry_time": entry_time,
                    "exit_time": exit_time,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "pnl_money": pnl_money,
                    "pnl_percent": (pnl_money / (balance - pnl_money)) * 100,
                    "balance_after": balance,
                    "exit_reason": exit_reason,
                    "bars_held": bars_held,
                    "ai_prob": prob,
                })

                equity_curve.append(balance)
                timestamps.append(exit_time)

                # Nhảy cóc qua số nến đã giữ lệnh (tránh mở chồng lấn lệnh)
                i += bars_held
            else:
                i += 1

        trades_df = pd.DataFrame(trades)
        equity_df = pd.DataFrame({"time": timestamps, "equity": equity_curve})

        self.print_report(trades_df, equity_df)
        self.plot_equity_curve(equity_df, trades_df)

        return trades_df

    def print_report(self, trades_df: pd.DataFrame, equity_df: pd.DataFrame):
        logging.info(f"\n{'='*25} BÁO CÁO KẾT QUẢ BACKTEST {'='*25}")
        if trades_df.empty:
            logging.warning("Không có lệnh nào được kích hoạt với ngưỡng xác suất này.")
            return

        total_trades = len(trades_df)
        win_trades = (trades_df["pnl_money"] > 0).sum()
        loss_trades = (trades_df["pnl_money"] < 0).sum()
        win_rate = (win_trades / total_trades) * 100

        total_profit = trades_df[trades_df["pnl_money"] > 0]["pnl_money"].sum()
        total_loss = abs(trades_df[trades_df["pnl_money"] < 0]["pnl_money"].sum())
        profit_factor = total_profit / total_loss if total_loss > 0 else np.nan

        net_profit = trades_df["pnl_money"].sum()
        final_balance = equity_df["equity"].iloc[-1]
        roi = ((final_balance - self.initial_balance) / self.initial_balance) * 100

        # Tính Maximum Drawdown (MDD)
        equity = equity_df["equity"]
        peak = equity.cummax()
        drawdown = (equity - peak) / peak
        max_drawdown = drawdown.min() * 100

        print(f"Vốn khởi điểm:           {self.initial_balance:,.2f}")
        print(f"Số dư cuối cùng:         {final_balance:,.2f}")
        print(f"Lợi nhuận ròng (Net PnL): {net_profit:,.2f} ({roi:+.2f}%)")
        print(f"Tổng số lệnh giao dịch:  {total_trades}")
        print(f"Số lệnh Thắng / Thua:    {win_trades} / {loss_trades}")
        print(f"Tỷ lệ Thắng (Win Rate):  {win_rate:.2f}%")
        print(f"Hệ số Lợi nhuận (PF):    {profit_factor:.2f}")
        print(f"Sụt giảm tối đa (MDD):   {max_drawdown:.2f}%")
        print(f"\nPhân bổ lý do đóng lệnh:")
        print(trades_df["exit_reason"].value_counts().to_string())

        # Xuất file CSV lịch sử lệnh
        report_file = BASE_DIR / "backtest_trades.csv"
        trades_df.to_csv(report_file, index=False)
        logging.info(f"Lịch sử lệnh chi tiết đã được lưu tại: {report_file}")

    def plot_equity_curve(self, equity_df: pd.DataFrame, trades_df: pd.DataFrame):
        """Vẽ biểu đồ tăng trưởng vốn và mức sụt giảm Drawdown."""
        equity = equity_df["equity"]
        peak = equity.cummax()
        drawdown = (equity - peak) / peak * 100

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})

        # Biểu đồ Equity Curve
        ax1.plot(equity_df["time"], equity_df["equity"], label="Equity Curve", color="#007acc", linewidth=1.8)
        ax1.axhline(self.initial_balance, color="gray", linestyle="--", alpha=0.7, label="Initial Capital")
        ax1.set_title("Biểu đồ tăng trưởng tài khoản (Equity Curve) - Out Of Sample", fontsize=14, fontweight="bold")
        ax1.set_ylabel("Số dư tài khoản")
        ax1.grid(True, linestyle=":", alpha=0.6)
        ax1.legend(loc="upper left")

        # Biểu đồ Drawdown (%)
        ax2.fill_between(equity_df["time"], drawdown, 0, color="#d9534f", alpha=0.4, label="Drawdown (%)")
        ax2.set_title("Mức sụt giảm vốn (Drawdown)", fontsize=11)
        ax2.set_xlabel("Thời gian")
        ax2.set_ylabel("Sụt giảm %")
        ax2.grid(True, linestyle=":", alpha=0.6)
        ax2.legend(loc="lower left")

        plt.tight_layout()
        chart_path = BASE_DIR / "equity_curve.png"
        plt.savefig(chart_path, dpi=300)
        logging.info(f"Đã lưu biểu đồ Equity Curve tại: {chart_path}")
        plt.show()


if __name__ == "__main__":
    dataset_file = BASE_DIR / "data" / "processed_dataset.parquet"
    model_file = BASE_DIR / "models" / "lgbm_forex_model.pkl"

    if not dataset_file.exists() or not model_file.exists():
        logging.error("Thiếu file dữ liệu processed_dataset.parquet hoặc file models/lgbm_forex_model.pkl!")
    else:
        tester = Backtester(
            dataset_path=dataset_file,
            model_path=model_file,
            initial_balance=100000.0,
            risk_per_trade=0.02,       # Rủi ro 2% mỗi lệnh
            threshold=0.55,            # Chỉ vào lệnh khi AI tự tin >= 55%
            tp_multiplier=1.5,
            sl_multiplier=1.0,
            horizon_bars=12,
            default_spread_pips=1.5
        )
        tester.run()
