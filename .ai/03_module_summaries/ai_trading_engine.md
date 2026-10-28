# Module Summary: AI Trading Engine & Orchestrator (`ai_trading_engine.py`)

## 1. Mục đích
Đóng vai trò là bộ não điều phối tự động toàn bộ chu trình giao dịch định lượng theo thời gian thực (Real-time Orchestrator), kết nối đa tầng giữa Price Action, Machine Learning, Quản trị rủi ro và WebSocket Streaming.

## 2. Quy trình xử lý theo từng nhịp (Tick Cycle)
1. **Lấy Tick & Cập nhật nến M5 Realtime**: Đọc giá Bid/Ask thực tế, cập nhật nến trong bộ nhớ (`update_live_candle_tick`), tính toán lại floating PnL.
2. **Kiểm tra 5 Màng lọc bảo vệ**:
   - Cầu dao 24H (`is_locked_24h`): Khóa 24h nếu dính 2 lệnh thua liên tiếp hoặc lỗ 2R.
   - Case F Rollover / News: Khóa trong khung giờ 4h-5h sáng VN hoặc khi spread giãn $\ge 25$ points.
   - Case C Broadening Chaos: Nhận diện loa kèn mở rộng -> Strict No Trade.
   - HMM Regime: Bỏ qua lệnh nếu trạng thái ẩn là `HIGH_VOLATILITY_CHAOS`.
   - OOD Anomaly Check: Bỏ qua lệnh nếu Isolation Forest phát hiện dữ liệu lạ chưa từng có trong tập huấn luyện.
3. **Thẩm định R:R & Lot Sizing 1R**:
   - $D_{\text{risk}} = |\text{Entry} - \text{SL}| + \text{Spread} + \text{Buffer}$.
   - $D_{\text{reward}} = |\text{TP} - \text{Entry}|$.
   - Bắt buộc $R:R \ge 1.5$ (chuẩn 1:2.0). Khối lượng Lot chuẩn xác theo 1R ($1.0\%$ vốn).
4. **Thực thi lệnh & Lưu trữ SQLite**: Gửi lệnh qua MT5 Executor, ghi nhận vào `orders`, `bot_signals`, `bot_logs`.
5. **Real-time Broadcast**: Truyền phát trạng thái toàn cục `REALTIME_TICK` qua WebSocket `/ws/live` tới mọi client đang mở dashboard.
