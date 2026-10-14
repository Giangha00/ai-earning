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
| `data/` | Thư mục lưu trữ nến dạng `.parquet` | Active (git-ignored) |
| `.ai/` | Agent memory bank and system documentation | Active |
| `docs/` | Human-readable system specifications | Active |
