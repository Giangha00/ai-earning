# Out-Of-Sample (OOS) Event-Driven Backtest Report

## 1. Mục tiêu & Thiết kế thử nghiệm (Test Design)
- **Module**: [backtest.py](file:///Users/macbook/ai-earning/backtest.py)
- **Dữ liệu kiểm thử**: 15% nến cuối cùng của [processed_dataset.parquet](file:///Users/macbook/ai-earning/data/processed_dataset.parquet) (2,511 nến M5 EURUSD từ `2026-10-05 16:05:00` đến `2026-10-16 11:00:00`).
- **Mô hình**: LightGBM Classifier tại [lgbm_forex_model.pkl](file:///Users/macbook/ai-earning/models/lgbm_forex_model.pkl).
- **Cơ chế mô phỏng**:
  - Event-driven (bar-by-bar): Theo dõi giá High/Low nến tương lai trong tối đa 12 nến (horizon = 1h).
  - Khấu trừ Spread thực tế: Khớp Buy tại `Ask = Close + Spread`, đóng tại `Bid = Bid_Price`.
  - Quản trị vốn: Rủi ro 2% vốn / lệnh, vốn khởi điểm 100,000 VND.

## 2. Kết quả kiểm thử thực nghiệm

| Ngưỡng Threshold | Số lệnh kích hoạt | Win Rate | Profit Factor (PF) | Max Drawdown (MDD) | Net PnL (VND) | Ghi chú |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **0.55 (Mặc định)** | **0** | **N/A** | **N/A** | **0.00%** | **0.00** | Mô hình không kích hoạt lệnh nào |
| **0.415** | 74 | 20.27% | 0.36 | -53.57% | -52,696.11 | Top ~4% tín hiệu xác suất cao nhất |
| **0.410** | 134 | 22.39% | 0.39 | -70.13% | -70,131.65 | Top ~8% tín hiệu |
| **0.400** | 551 | 24.14% | 0.47 | -99.02% | -98,914.49 | Top ~45% tín hiệu |

## 3. Phân tích nguyên nhân định lượng (Quantitative Root Cause)

1. **Ngưỡng xác suất 0.55 không có lệnh**:
   - Mô hình LightGBM được huấn luyện với early stopping và dừng lại ở **iteration 4**.
   - Dải xác suất dự đoán `ai_prob` trên tập Test chỉ dao động hẹp từ `0.3620` đến `0.4214` (trung bình `0.3974`). Do đó, không có nến nào vượt qua ngưỡng `0.55`.

2. **Ảnh hưởng tiêu cực của Spread so với ATR trên nến M5**:
   - Trung bình `ATR(14)` trên EURUSD M5 là `0.000209` (~2.1 pips).
   - Phí Spread của broker là `12 points` = `1.2 pips` (`0.000120`).
   - Khoảng cách Stop Loss: `1.0 * ATR = 2.1 pips`. Nhưng do vào lệnh tại `Ask = Close + Spread`, khoảng đệm giá thực tế từ `Close` đến `SL` chỉ còn: `2.1 - 1.2 = 0.9 pips`!
   - Khoảng cách Take Profit: `Close + Spread + 1.5 * ATR = 1.2 + 3.15 = 4.35 pips`.
   - **Tỷ lệ Risk-Reward thực tế bị thị trường đòi hỏi**: `4.35 pips / 0.9 pips ≈ 4.83 : 1`.
   - Do nhiễu giá ngẫu nhiên (noise) của nến M5 vượt quá 0.9 pips, hầu hết các lệnh đều bị quét SL (`HIT_SL`) trước khi đạt được 4.35 pips.

## 4. Đề xuất cải thiện để đạt chuẩn bot "Ngon" (PF > 1.3, MDD < 15%)
1. **Nâng khung thời gian (Timeframe)**: Chuyển sang nến M15, H1 hoặc H4 để tăng biên độ sóng (ATR ~ 10-30 pips), giảm thiểu tỷ trọng ăn mòn của Spread (1.2 pips chiếm < 5% thay vì > 50% khoảng cách SL).
2. **Cải tiến huấn luyện LightGBM**:
   - Tinh chỉnh siêu tham số và feature selection nhằm tăng AUC từ `0.513` lên `>= 0.58`.
   - Chuẩn hóa xác suất (Probability Calibration qua Isotonic Regression hoặc Sigmoid) hoặc sử dụng ngưỡng động theo phân vị (quantile thresholding).
3. **Mở rộng SL Multiplier**: Tăng `sl_multiplier` lên 1.5 - 2.0 để tránh bị quét bởi nhiễu vi mô của spread.
