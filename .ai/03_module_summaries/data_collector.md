# Module Summary: Data Collector (`data_collector.py`)

## 1. Mục đích
Thu thập dữ liệu nến lịch sử (OHLCV) từ MetaTrader 5 theo khung thời gian (Timeframe) và lưu trữ dưới dạng Parquet nén Snappy để phục vụ huấn luyện mô hình và tính toán chỉ báo kỹ thuật.

## 2. Tính năng chính
- Tự động bật hiển thị mã giao dịch trong Market Watch (`_ensure_symbol_visible`).
- Tải dữ liệu nến theo khoảng ngày (`fetch_by_range`) hoặc theo số lượng nến gần nhất (`fetch_by_count`).
- Chuẩn hóa timestamp sang UTC datetime và cấu trúc cột: `["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]`.
- Lưu trữ nén chuẩn Snappy trong thư mục `data/` với quy ước đặt tên: `{SYMBOL}_{TIMEFRAME}_{FROM}_{TO}.parquet`.
- Hỗ trợ cả hai môi trường: MT5 thật trên Windows và MockMT5 giả lập trên macOS/Linux.
