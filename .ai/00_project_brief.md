# 00 - Project Brief: AI Trading Bot (MetaTrader 5 & Quantitative Engine)

## 1. Project Goal
Build an automated, production-ready AI quantitative trading bot integrating with MetaTrader 5 (MT5), utilizing SQLite for operational trade logging, signal tracking, risk management, and equity history, augmented with:
- **Price Action Law of Bulls and Bears (6 Market Cases A - F)**
- **Mathematical ML & Deep Learning Pipeline** (Logistic Regression, Sigmoid, Binary Cross-Entropy, Multi-Layer Perceptron with L2 Regularization & Inverted Dropout, Gaussian HMM for 3 Market Regimes, Monte Carlo VaR)
- **Anti-Noise & Out-of-Distribution (OOD) Filter** (Isolation Forest with Anomaly Scoring)
- **Dynamic 1R Lot Sizing & Custom Fixed Lot (v2) + 24h Circuit Breaker (`LOCK_BOT_24H()`) & Target Profit Circuit Breaker (`close_all_positions()`)**
- **Real-Time Bidirectional WebSocket Streaming** from backend engine to frontend dashboard.

## 2. Key Modules
- **Configuration (`config.py`)**: Environment-based credentials, path configuration, and dynamic v2 runtime parameters (`INITIAL_CAPITAL`, `CUSTOM_LOT_SIZE`, `TARGET_PROFIT_GOAL`, `BOT_RUNNING`).
- **Database (`db.py`)**: SQLite schema initialization and migration (tables: `orders`, `bot_signals`, `daily_equity`, `bot_logs`, `app_settings`).
- **MT5 Connector (`mt5_connector.py`)**: Terminal initialization, broker authentication, connection lifecycle management, with seamless Mock simulation on macOS/Linux.
- **Price Action Engine (`ai_price_action.py`)**: 6 Market Cases (Case A Trend, Case B Compression, Case C Broadening Chaos, Case D Liquidity Sweep, Case E Leading Wave, Case F Rollover News) and 3-condition Compression Detection.
- **Multi-Dataset Training Pool (`create_training_pool.py`, `data/hf_datasets/`)**: Combines `arvind7754/btc-candlestick-dataset` (13,081 BTCUSDT candlestick records), `tripolskypetr/tradingview-ideas-signals` (51,963 TradingView LONG/SHORT/NEUTRAL signals + 111,918 1m Binance OHLCV bars resampled to 22,385 M5 bars), and 20,000 MT5 Exness historical bars into a unified 55,167-row Training Pool (`data/training_pool.csv`, `data/processed_dataset.parquet`, 34 features including `candle_bullish_score` and `tv_signal_confluence`).
- **Mathematical AI Models (`ai_math_models.py`, `train_model.py`)**: LightGBM Gradient Boosting Classifier, Sigmoid activation, Vectorized Logistic Regression, Deep MLP with L2/Dropout, Gaussian HMM Regimes, Isolation Forest OOD filter, and Monte Carlo VaR.
- **Risk Manager (`risk_manager.py`)**: R:R ratio check (min 1:1.5, default 1:2.0), Custom Lot priority (`get_execution_lot()`), Target Profit Circuit Breaker (`is_target_goal_reached()`), 1R lot calculation, and 24h lockout circuit breaker on 2 consecutive losses.
- **Executor (`executor.py`)**: Order execution and `close_all_positions()` with `deviation = 20` to immediately close all open MT5 positions when the target profit goal is reached.
- **Autonomous Live Engine (`ai_trading_engine.py`)**: Background loop continuously evaluating ticks, checking the Target Profit Circuit Breaker at the start of each cycle, classifying cases, filtering noise, executing trades with Custom Lot, logging to `trading.log`, and broadcasting via WebSockets.
- **Web Terminal (`web_app.py`, `dashboard.js`, `index.html`)**: Real-time trading dashboard with Lightweight Charts, AI HUD, dynamic Bot v2 configuration form (`/api/start_bot`, `/api/stop_bot`), and live VNĐ/USD wallet.

## 3. Supported Environments
- **Primary Runtime for MT5 Execution**: Windows (Windows 10/11 or Windows Server VPS) where MetaTrader 5 Terminal 64-bit is installed.
- **Development & Analysis**: Cross-platform (macOS / Linux / Windows) with SQLite, Pandas, NumPy, scikit-learn, LightGBM, and hmmlearn.
