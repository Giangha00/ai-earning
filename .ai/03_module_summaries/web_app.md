# Module Summary: Web Dashboard (`web_app.py`)

## 1. Mục đích
Cung cấp giao diện trực quan hóa chuyên nghiệp cho bot giao dịch, hiển thị biểu đồ nến tương tác (TradingView Lightweight Charts), các chỉ báo kỹ thuật, thông tin tài khoản MT5, và nhật ký các bảng dữ liệu trong SQLite.

## 2. Các thành phần chính
- **Backend FastAPI (`web_app.py`)**:
  - `GET /`: Giao diện Dashboard SPA.
  - `GET /api/account`: Thông tin tài khoản MT5, số dư, vốn, tỷ lệ thắng.
  - `GET /api/candles`: Đọc dữ liệu nến từ các file `.parquet` trong `data/`, tính SMA 20, SMA 50, RSI 14, Volume và định dạng chuẩn cho Lightweight Charts.
  - `GET /api/orders`: Quản lý danh sách lệnh giao dịch (`orders`).
  - `GET /api/signals`: Quản lý tín hiệu AI (`bot_signals`).
  - `GET /api/equity`: Lịch sử tăng trưởng vốn (`daily_equity`).
  - `GET /api/logs`: Nhật ký kiểm toán hệ thống (`bot_logs`).
  - `GET /api/files`: Danh mục file parquet đã thu thập.
- **Frontend (`templates/index.html`, `static/css/dashboard.css`, `static/js/dashboard.js`)**:
  - Giao diện Dark Cyber Fintech cao cấp.
  - Biểu đồ nến TradingView thời gian thực, đồng bộ trục thời gian với biểu đồ phụ RSI 14.
  - Bảng điều khiển phân loại tab đa nhiệm.
