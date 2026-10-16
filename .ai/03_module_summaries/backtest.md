# Module Summary: Event-Driven Backtester (`backtest.py`)

## 1. Mục đích
Mô phỏng khớp lệnh thực tế từng bước (Event-driven / Bar-by-bar) trên tập dữ liệu kiểm thử độc lập Out-Of-Sample (15% cuối dữ liệu) để đo lường hiệu quả định lượng của chiến lược giao dịch trước khi kết nối trực tiếp với MetaTrader 5.

## 2. Thiết kế cốt lõi
- **Mô phỏng Bar-by-Bar (Tránh Look-ahead Bias):**
  - Theo dõi giá `high` và `low` của từng cây nến tiếp theo trong khung thời gian `horizon_bars` (mặc định 12 nến M5 = 1 giờ).
  - Kiểm tra điều kiện chạm Stop-Loss hoặc Take-Profit theo thứ tự xuất hiện nến; đóng lệnh theo giá `close` khi hết thời gian giữ lệnh (`TIME_OUT`).
- **Khấu trừ Chi phí Giao dịch (Spread & Slippage):**
  - Khớp lệnh MUA tại giá Ask = `close + spread`.
  - Đóng lệnh BÁN tại giá Bid tương ứng, phản ánh chính xác chi phí ăn mòn của sàn môi giới.
- **Quản trị Rủi ro Động (Fixed % Risk per Trade):**
  - Số tiền chấp nhận rủi ro trên mỗi lệnh = `balance * risk_per_trade` (mặc định 2% vốn).
  - Tự động tái đầu tư lợi nhuận kép (Compounding) khi tài khoản tăng trưởng.
- **Đo lường Định lượng & Trực quan hóa:**
  - Thống kê: Tỷ lệ thắng (Win Rate), Hệ số lợi nhuận (Profit Factor), Tỷ lệ sụt giảm tối đa (Max Drawdown - MDD), Lợi nhuận ròng (Net PnL / ROI).
  - Xuất báo cáo lịch sử lệnh: Lưu từng giao dịch chi tiết ra `backtest_trades.csv`.
  - Biểu đồ tăng trưởng: Tạo biểu đồ `equity_curve.png` gồm đường cong vốn (Equity Curve) và biểu đồ diện tích vùng sụt giảm (Drawdown Area Chart).
