# 00 - Project Brief: AI Trading Bot (MetaTrader 5 & Quantitative Engine)

## 1. Project Goal
Build an automated, production-ready AI quantitative trading bot integrating with MetaTrader 5 (MT5), utilizing SQLite for operational trade logging, signal tracking, risk management, and equity history, augmented with:
- **Price Action Law of Bulls and Bears (6 Market Cases A - F)**
- **Mathematical ML & Deep Learning Pipeline** (Logistic Regression, Sigmoid, Binary Cross-Entropy, Multi-Layer Perceptron with L2 Regularization & Inverted Dropout, Gaussian HMM for 3 Market Regimes, Monte Carlo VaR)
- **Anti-Noise & Out-of-Distribution (OOD) Filter** (Isolation Forest with Anomaly Scoring)
- **Dynamic 1R Lot Sizing & 24h Circuit Breaker (`LOCK_BOT_24H()`)**
- **Real-Time Bidirectional WebSocket Streaming** from backend engine to frontend dashboard.

## 2. Key Modules
- **Configuration (`config.py`)**: Environment-based credentials and path configuration.
- **Database (`db.py`)**: SQLite schema initialization and migration (tables: `orders`, `bot_signals`, `daily_equity`, `bot_logs`).
- **MT5 Connector (`mt5_connector.py`)**: Terminal initialization, broker authentication, connection lifecycle management, with seamless Mock simulation on macOS/Linux.
- **Price Action Engine (`ai_price_action.py`)**: 6 Market Cases (Case A Trend, Case B Compression, Case C Broadening Chaos, Case D Liquidity Sweep, Case E Leading Wave, Case F Rollover News) and 3-condition Compression Detection.
- **Mathematical AI Models (`ai_math_models.py`)**: Sigmoid activation, Vectorized Logistic Regression, Deep MLP with L2/Dropout, Gaussian HMM Regimes, Isolation Forest OOD filter, and Monte Carlo VaR.
- **Risk Manager (`risk_manager.py`)**: R:R ratio check (min 1:1.5, default 1:2.0), 1R lot calculation (1.0% equity), and 24h lockout circuit breaker on 2 consecutive losses.
- **Autonomous Live Engine (`ai_trading_engine.py`)**: Background loop continuously evaluating ticks, classifying cases, filtering noise, executing trades, and broadcasting via WebSockets.
- **Web Terminal (`web_app.py`, `dashboard.js`, `index.html`)**: Real-time trading dashboard with Lightweight Charts, AI HUD, and live VNĐ wallet.

## 3. Supported Environments
- **Primary Runtime for MT5 Execution**: Windows (Windows 10/11 or Windows Server VPS) where MetaTrader 5 Terminal 64-bit is installed.
- **Development & Analysis**: Cross-platform (macOS / Linux / Windows) with SQLite, Pandas, NumPy, scikit-learn, LightGBM, and hmmlearn.
