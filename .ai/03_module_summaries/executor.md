# Module Summary: Execution & Order Management (`executor.py` - TASK-4.2)

## 1. Mục đích
Cung cấp lớp trừu tượng (Wrapper) cho các API MetaTrader 5 để thực thi lệnh thị trường (Market Orders) kèm Stop-Loss/Take-Profit cứng, xử lý trượt giá, đóng lệnh chủ động/khẩn cấp, và giải mã các mã lỗi (retcode) từ broker.

## 2. Thiết kế cốt lõi
- **Chuẩn hóa Mức giá (`_normalize_price`):**
  - Làm tròn giá thị trường, giá SL và giá TP theo đúng số lượng chữ số thập phân (`digits`) của từng cặp tiền/hàng hóa.
- **Thực thi Lệnh Thị trường (`open_position`):**
  - Hỗ trợ cả hai chiều `BUY` (khớp Ask) và `SELL` (khớp Bid).
  - Tích hợp sẵn Stop-Loss và Take-Profit ngay trong payload yêu cầu (`TRADE_ACTION_DEAL`) nhằm đảm bảo vị thế luôn được bảo vệ ngay khi khớp trên server broker.
  - Sử dụng tham số `deviation` để kiểm soát trượt giá và gán `magic_number` nhận diện bot.
  - Bảng tra cứu mã lỗi `RETCODE_MESSAGES` hỗ trợ ghi log chi tiết khi lệnh bị sàn từ chối (Requote, Price Off, Invalid Stops, No Money, v.v.).
- **Đóng Vị thế Khẩn cấp/Chủ động (`close_position_by_ticket`):**
  - Kiểm tra trạng thái vị thế còn tồn tại hay không.
  - Tự động đảo chiều lệnh (`BUY` đóng bằng `SELL` tại Bid, `SELL` đóng bằng `BUY` tại Ask) và gửi yêu cầu đóng trực tiếp bằng ticket ID.
- **Truy vấn Lệnh Mở (`get_open_positions`):**
  - Lấy danh sách các lệnh đang hoạt động trên tài khoản, hỗ trợ lọc theo `magic_number`.
