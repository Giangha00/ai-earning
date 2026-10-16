# Module Summary: Web Dashboard (`web_app.py`)

## 1. Mục đích
Cung cấp giao diện Trading Terminal chuyên nghiệp dành cho bot giao dịch thuật toán:
- Biểu đồ nến TradingView tương tác ở trung tâm với **100% dữ liệu nến thật từ thị trường** (EURUSD M5 thực tế).
- Tỷ giá USD/VND trực tuyến thời gian thực (1 USD ≈ 25,872 ₫).
- Hiển thị trực tiếp tổng số dư ví được quy đổi ra **VNĐ** (theo tỷ giá thị trường thực tế).
- Form đặt lệnh trực quan hoàn toàn bằng **VNĐ**:
  - **Mức giá muốn đánh (VNĐ)**: Quy đổi tương ứng với giá EURUSD thị trường thực tế (e.g. `29,132 ₫`), kèm nút `⚡ Giá hiện tại` và tinh chỉnh `±10 pips`.
  - **Số lot**: Khối lượng vào lệnh (`0.01` đến `1.00`), hiển thị số tiền ký quỹ ước tính bằng VNĐ.
  - **Mức giá mong muốn kiếm được (VNĐ)**: Hỗ trợ cả nhập mức giá chốt lời (VNĐ/EUR) và chọn nhanh các mốc tiền lời mong muốn (`+200k ₫`, `+500k ₫`, `+1M ₫`, `+2M ₫`, `+5M ₫`).
  - Hộp tính toán lợi nhuận dự kiến tức thì: hiển thị rõ số tiền lời bằng **VNĐ** (e.g. `+500,000 ₫`), quy đổi USD và số pips mục tiêu.
- Cột bên cạnh biểu đồ hiển thị danh sách **lịch sử các lệnh AI thật đã đánh**:
  - **Tuyệt đối không có dữ liệu mẫu (seed data đã xóa 100%)**.
  - Toàn bộ cơ sở dữ liệu `orders`, `bot_signals`, `daily_equity`, `bot_logs` chỉ lưu trữ và hiển thị các lệnh thực tế.
  - Các chỉ báo kỹ thuật (RSI, ATR, ADX) và độ tin cậy AI khi vào lệnh được tính toán trực tiếp từ dữ liệu nến thật và mô hình Machine Learning LightGBM đã huấn luyện.

## 2. API Endpoints
- `GET /`: Giao diện Dashboard SPA hoàn chỉnh.
- `GET /api/account`: Thông tin tài khoản Exness, số dư USD, số dư quy đổi VNĐ (`balance_vnd`, `equity_vnd`, `floating_pnl_vnd`, `usd_vnd_rate`).
- `GET /api/candles`: Đọc nến thị trường thật từ Parquet trong `data/`, tính toán SMA20, SMA50, RSI14.
- `GET /api/orders`: Danh sách lệnh AI thực tế đã thực thi từ SQLite.
- `POST /api/orders/place`: Tiếp nhận lệnh đặt từ UI, tính toán chỉ báo và độ tin cậy AI thực tế, ghi nhận vào SQLite `orders`, `bot_signals` & `bot_logs`.
- `POST /api/orders/close/{ticket_id}`: Chốt lệnh thủ công và tính toán lợi nhuận thực tế.
- `GET /api/signals`: Danh sách tín hiệu AI (`bot_signals`).
- `GET /api/equity`: Dữ liệu tăng trưởng vốn (`daily_equity`).
- `GET /api/logs`: Nhật ký hoạt động (`bot_logs`).

