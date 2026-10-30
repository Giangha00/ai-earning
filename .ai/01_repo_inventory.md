# 01 - Repository Inventory

| File / Folder | Purpose | Status |
| :--- | :--- | :--- |
| `.env` | Stores sensitive secrets, credentials, DB paths | Active (git-ignored) |
| `.env.example` | Template for environment variables | Active |
| `requirements.txt` | Python dependency declarations | Active |
| `config.py` | Environment loading and strongly-typed config object | Active |
| `db.py` | SQLite connection pooling & schema initialization | Active |
| `mt5_connector.py` | MetaTrader 5 terminal connector and session manager | Active |
| `data_collector.py` | Tải dữ liệu nến từ MT5 và lưu Parquet nén Snappy | Active |
| `create_training_pool.py` | Cào 20,000+ nến, trích xuất đặc trưng Price Action (Chương 2 & 4) và gán nhãn R:R = 1:2 xuất `data/training_pool.csv` | Active |
| `feature_engineering.py` | Tính toán chỉ báo kỹ thuật & đặc trưng Training Pool, gán nhãn R:R = 1:2 | Active |
| `train_model.py` | Huấn luyện mô hình AI trên `data/training_pool.csv` (70/15/15) xuất `models/model.pkl` & `models/lgbm_forex_model.pkl` | Active |
| `backtest.py` | Kiểm thử Out-of-Sample trên tập Test 15% với ngưỡng Confidence >= 0.75 và R:R = 1:2 | Active |
| `data/` | Thư mục lưu trữ nến dạng `.parquet` | Active (git-ignored) |
| `web_app.py` | FastAPI backend cung cấp REST API và giao diện Dashboard nến | Active |
| `templates/` & `static/` | Giao diện TradingView Lightweight Charts & Dark Cyber Fintech UI | Active |
| `.ai/` | Agent memory bank and system documentation | Active |
| `docs/` | Human-readable system specifications | Active |
