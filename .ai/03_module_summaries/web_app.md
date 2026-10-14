# Module Summary: Web Dashboard (`web_app.py`)

## 1. Mục đích
Cung cấp giao diện Trading Terminal chuyên nghiệp dành cho bot giao dịch thuật toán:
- Biểu đồ nến TradingView tương tác ở trung tâm.
- Hiển thị trực tiếp tổng số dư ví được quy đổi ra **VNĐ** (theo tỷ giá USD/VND hiện hành).
- Form đặt lệnh trực tiếp bằng **VNĐ**:
  - **Mức giá muốn đánh (VNĐ)**: e.g. `27,613 ₫` (tự động đồng bộ với tỷ giá Forex `1.08500`).
  - **Số lot**: Khối lượng vào lệnh.
  - **Mức giá mong muốn kiếm được (VNĐ)**: e.g. `27,715 ₫` (chốt lời mục tiêu `1.08900`).
  - Hộp tính toán lợi nhuận dự kiến tức thì bằng cả **VNĐ** và **USD**.
- Cột bên cạnh biểu đồ hiển thị danh sách **lịch sử các lệnh AI thật đã đánh**:
  - Không sử dụng dữ liệu mẫu (seed data đã được gỡ bỏ hoàn toàn).
  - Chỉ ghi nhận và hiển thị các lệnh thực tế do người dùng hoặc bot đặt.

## 2. API Endpoints
- `GET /`: Giao diện Dashboard SPA hoàn chỉnh.
- `GET /api/account`: Thông tin tài khoản MT5, số dư USD, số dư quy đổi VNĐ (`balance_vnd`, `equity_vnd`, `floating_pnl_vnd`).
- `GET /api/candles`: Đọc nến từ Parquet trong `data/`, tính toán SMA20, SMA50, RSI14.
- `GET /api/orders`: Danh sách lệnh AI đã thực thi từ SQLite.
- `POST /api/orders/place`: Tiếp nhận lệnh đặt từ UI và ghi nhận vào SQLite `orders` & `bot_logs`.
- `POST /api/orders/close/{ticket_id}`: Chốt lệnh thủ công và tính toán lợi nhuận thực tế.
- `GET /api/signals`: Danh sách tín hiệu AI (`bot_signals`).
- `GET /api/equity`: Dữ liệu tăng trưởng vốn (`daily_equity`).
- `GET /api/logs`: Nhật ký hoạt động (`bot_logs`).
