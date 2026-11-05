# AI Earning - Quantitative AI Trading Bot (MetaTrader 5 & Machine Learning)

Hệ thống Bot giao dịch định lượng thông minh tích hợp MetaTrader 5 (MT5), kết hợp trường phái **Price Action (6 Market Cases A - F)** và hệ thống mô hình toán học **Machine Learning / Deep Learning** (LightGBM, Vectorized Logistic Regression, Deep MLP, Gaussian HMM Regimes, Isolation Forest OOD Filter).

---

## 1. Cài đặt Môi trường (Setup)

### Yêu cầu tiên quyết:
- **Python**: 3.10 trở lên (khuyến nghị Python 3.11 hoặc 3.12).
- **Hệ điều hành**: macOS / Linux (hỗ trợ mô phỏng Mock MT5 hoàn chỉnh) hoặc Windows 10/11 / Windows Server VPS (hỗ trợ MT5 thật).

### Các bước cài đặt:

```bash
# 1. Tạo môi trường ảo (Virtual Environment)
python3 -m venv .venv

# 2. Kích hoạt môi trường ảo
# Trên macOS / Linux:
source .venv/bin/activate
# Trên Windows:
# .venv\Scripts\activate

# 3. Nâng cấp pip và cài đặt thư viện phụ thuộc
pip install --upgrade pip
pip install -r requirements.txt

# 4. Thiết lập file cấu hình môi trường
cp .env.example .env
# Chỉnh sửa thông tin tài khoản MT5 trong .env (MT5_LOGIN, MT5_PASSWORD, MT5_SERVER)
```

---

## 2. Lệnh Khởi động Dự án (Start Project)

### Cách 1: Khởi động Web Terminal & Realtime Dashboard (Khuyến nghị)
Khởi chạy giao diện điều khiển trực quan (FastAPI + WebSocket + Lightweight Charts + AI HUD):

```bash
# Chạy trực tiếp qua Python:
python web_app.py

# Hoặc chạy thông qua Uvicorn:
uvicorn web_app:app --host 127.0.0.1 --port 8000 --reload
```
👉 Mở trình duyệt và truy cập: **`http://127.0.0.1:8000`**

### Cách 2: Chạy Bot AI Trading Độc lập (Headless CLI Mode)
Chạy vòng lặp giao dịch tự động không cần mở trình duyệt web:

```bash
python ai_trading_engine.py
```

---

## 3. Lệnh Crawl Dữ liệu Dự án (Data Crawling)

Hệ thống cung cấp các công cụ thu thập dữ liệu chuyên sâu phục vụ huấn luyện AI:

### A. Crawl dữ liệu Tín hiệu MQL5 MT5 Signals (Mới)
Thu thập chỉ số định lượng (Sharpe, Profit Factor, Drawdown, Win Rate, Equity Curves) từ [MQL5 MT5 Signals](https://www.mql5.com/en/signals/mt5):

```bash
# Chế độ kiểm tra nhanh (Test 1 trang, 5 tín hiệu chi tiết):
python mql5_signal_crawler.py --test

# Crawl đầy đủ 3 trang (~140 tín hiệu thực tế) với 6 luồng tải song song:
python mql5_signal_crawler.py --pages 3 --workers 6

# Crawl 5 trang danh mục và lọc các tín hiệu có tối thiểu 20 lệnh giao dịch:
python mql5_signal_crawler.py --pages 5 --min-trades 20 --workers 8

# Chỉ lấy tổng quan các thẻ (không crawl trang chi tiết - tốc độ siêu nhanh):
python mql5_signal_crawler.py --pages 5 --no-details
```
📁 Dữ liệu sau khi crawl được lưu tại:
- `data/mql5_signals/mql5_signals_ai_features.parquet` (69 đặc trưng AI & nhãn phân loại)
- `data/mql5_signals/mql5_signals_ai_features.csv`
- `data/mql5_signals/mql5_signals_equity_curves.json` (Chuỗi thời gian đường cong vốn)

### B. Tải và Thiết lập Mega Training Pool (HuggingFace + MT5 Exness)
Tải và hợp nhất 5 bộ dữ liệu Hugging Face + 20,000 nến Exness:

```bash
python create_training_pool.py
```
📁 Kết quả lưu tại: `data/training_pool.csv` và `data/processed_dataset.parquet`.

### C. Thu thập nến lịch sử từ MT5
```bash
python data_collector.py
```

---

## 4. Lệnh Huấn luyện Mô hình AI (AI Training)

### A. Huấn luyện Mô hình Meta-AI Đánh giá Chiến lược (Từ dữ liệu MQL5 Signals)
Huấn luyện mô hình LightGBM Meta-Classifier và Random Forest Regressor để lọc các chiến lược chất lượng chuẩn Pro và loại bỏ bẫy rủi ro Martingale:

```bash
python train_signal_meta_model.py
```
📁 Mô hình được xuất vào: `models/mql5_signal_meta_model.pkl` (Accuracy ~94.8%, Precision 100%).

### B. Huấn luyện Bộ 5 Mô hình AI Trading (Từ Mega Training Pool)
Huấn luyện LightGBM Classifier, Vectorized Logistic Regression, Deep MLP, Gaussian HMM Regimes và Isolation Forest OOD Filter:

```bash
python train_model.py
```
📁 Mô hình được xuất vào: `models/lgbm_forex_model.pkl` và `models/model.pkl`.

---

## 5. Lệnh Kiểm thử & Backtest (Testing & Simulation)

```bash
# 1. Chạy Unit Test kiểm thử bộ Parser và Feature Engineering của MQL5 Crawler:
python test_mql5_signal_crawler.py

# 2. Chạy kiểm thử toàn diện luồng khớp lệnh, Mock MT5 & Quản lý rủi ro 1R:
python test_execution.py

# 3. Chạy Backtest chiến lược trên dữ liệu lịch sử:
python backtest.py
```

---

## 6. Cấu trúc Thư mục Chính

```text
├── web_app.py                 # FastAPI Web Server & Realtime WebSocket
├── ai_trading_engine.py       # Master Autonomous AI Engine Loop
├── ai_price_action.py         # 6 Market Cases Price Action Engine
├── ai_math_models.py          # Vectorized ML/DL, HMM Regimes, OOD Anomaly Filter
├── risk_manager.py            # Quản lý vốn 1R, R:R >= 1.5, 24h Circuit Breaker
├── executor.py                # Đặt lệnh, đóng lệnh MT5, tính phí Commission/Swap
├── mt5_connector.py           # Kết nối MT5 Terminal và giả lập MockMT5 cross-platform
├── mql5_signal_crawler.py     # Module Crawl Tín hiệu MT5 từ mql5.com
├── train_signal_meta_model.py # Huấn luyện Meta-Model AI từ dữ liệu MQL5
├── create_training_pool.py    # Xây dựng Mega Dataset (HuggingFace + Exness)
├── train_model.py             # Huấn luyện 5 mô hình toán học định lượng
├── data/                      # Lưu trữ Parquet, CSV dữ liệu huấn luyện
│   ├── mql5_signals/          # Dữ liệu crawl từ MQL5 Signals
│   └── hf_datasets/           # Dữ liệu nến từ Hugging Face
├── models/                    # Lưu trữ các file model AI (.pkl)
├── templates/ & static/       # Giao diện Web Dashboard & Lightweight Charts
└── docs/                      # Tài liệu kỹ thuật chi tiết (BA, SA, ADR)
```

