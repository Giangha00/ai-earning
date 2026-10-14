# Module Summary: Feature Engineering (`feature_engineering.py`)

## 1. Mục đích
Tính toán các chỉ báo kỹ thuật tài chính nâng cao (sử dụng `pandas-ta`) và gán nhãn dữ liệu theo phương pháp **Triple Barrier Method** phục vụ huấn luyện mô hình Machine Learning / AI Trading.

## 2. Các nhóm Features kỹ thuật
1. **Động lượng (Momentum)**: RSI(14), RSI(7).
2. **Xu hướng (Trend)**: EMA(20), EMA(50), EMA(200), khoảng cách tương đối giá tới EMA (%), MACD (12, 26, 9) gồm macd, macd_signal, macd_hist.
3. **Biến động (Volatility)**: ATR(14), ATR % giá, Bollinger Bands (20, 2) gồm bb_width và vị trí giá %B.
4. **Đặc trưng nến (Geometry)**: Tỷ lệ thân nến `body_ratio`, tỷ lệ thay đổi giá `return_1`, `return_3`, `return_5`.
5. **Khối lượng (Volume)**: SMA khối lượng tick 20 nến, tỷ lệ khối lượng so với trung bình `vol_ratio`.
6. **Thời gian (Cyclical/Temporal)**: `hour` (giờ trong ngày), `dayofweek` (ngày trong tuần).

## 3. Cơ chế Gán nhãn Triple Barrier Method
- **Horizon**: 12 bars (tương đương 1 giờ trên nến M5).
- **Take Profit (TP)**: `1.5 * ATR(14)`
- **Stop Loss (SL)**: `1.0 * ATR(14)` (Tỷ lệ Risk:Reward = 1:1.5)
- **Nhãn mục tiêu (`target`)**:
  - `1` (Thắng / Win): Giá chạm TP trước SL trong vòng 12 nến.
  - `0` (Thua / Quá hạn): Giá chạm SL trước hoặc hết 12 nến chưa chạm TP.
- **Đầu ra**: Lưu trữ tập dữ liệu huấn luyện tại `data/processed_dataset.parquet`.
