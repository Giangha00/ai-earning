# Module Summary: Risk Manager (`risk_manager.py` - TASK-4.1)

## 1. Mục đích
Bảo vệ tài khoản giao dịch khỏi cháy vốn, kiểm soát sụt giảm tài sản (Drawdown) và tính toán kích thước vị thế (Lot Size) chuẩn xác dựa trên thông số đặc thù của từng mã sản phẩm từ sàn MetaTrader 5.

## 2. Thiết kế cốt lõi
- **Kiểm soát An toàn Tài khoản (`is_safe_to_trade`):**
  - **Mục tiêu lợi nhuận:** Tự động khóa giao dịch khi chạm hoặc vượt `target_balance` để bảo toàn thành quả.
  - **Daily Drawdown Protection:** Theo dõi số dư đầu ngày (`daily_start_balance`) và giới hạn lỗ tối đa trong ngày (`max_daily_drawdown`, mặc định 6%).
  - **Margin Level Protection:** Ngăn mở thêm vị thế khi tỷ lệ ký quỹ (`margin_level`) xuống dưới ngưỡng 200%, phòng tránh rủi ro Stop-Out từ sàn.
- **Tính toán Khối lượng Lệnh Động (`calculate_lot_size`):**
  - Quản trị rủi ro cố định (% Equity): `risk_capital = equity * risk_per_trade` (mặc định 2%).
  - Tính toán theo thông số kỹ thuật thực tế của broker: `tick_size`, `tick_value`, `volume_step`, `volume_min`, `volume_max`.
  - Làm tròn xuống theo bội số `volume_step` để đảm bảo không vượt quá mức rủi ro tối đa cho phép.
