# Module Summary: Web Dashboard (`web_app.py`)

## 1. Mục đích
Cung cấp giao diện Trading Terminal chuyên nghiệp dành cho bot giao dịch thuật toán:
- Biểu đồ nến TradingView tương tác ở trung tâm.
- Hiển thị trực tiếp tổng số dư ví được quy đổi ra **VNĐ** (theo tỷ giá USD/VND hiện hành).
- Form đặt lệnh trực quan cho phép nhập: **mức giá muốn đánh**, **số lot**, và **mức giá mong muốn kiếm được** kèm tính toán lợi nhuận dự kiến tức thời (cả USD và VNĐ).
- Cột bên cạnh biểu đồ hiển thị danh sách **lịch sử các lệnh AI đã đánh** (ticket, loại lệnh BUY/SELL, volume, điểm vào, điểm chốt lời, lãi lỗ USD và VNĐ).

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
