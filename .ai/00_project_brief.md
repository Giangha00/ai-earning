# 00 - Project Brief: AI Trading Bot (MetaTrader 5)

## 1. Project Goal
Build an automated AI-assisted trading bot integrating with MetaTrader 5 (MT5), utilizing SQLite for operational trade logging, signal tracking, risk management, and equity history.

## 2. Key Modules
- **Configuration (`config.py`)**: Environment-based credentials and path configuration.
- **Database (`db.py`)**: SQLite schema initialization and connection management (tables: `orders`, `bot_signals`, `daily_equity`, `bot_logs`).
- **MT5 Connector (`mt5_connector.py`)**: Terminal initialization, broker authentication, connection lifecycle management.
- **Signal Engine & Strategy**: Generating buy/sell/hold signals with indicators (RSI, ATR, ADX).
- **Execution & Risk Management**: Automated lot sizing, stop loss / take profit, drawdown protection.

## 3. Supported Environments
- **Primary Runtime for MT5 Execution**: Windows (Windows 10/11 or Windows Server VPS) where MetaTrader 5 Terminal 64-bit is installed.
- **Development & Analysis**: Cross-platform (macOS / Linux / Windows) with SQLite, Pandas, NumPy.
