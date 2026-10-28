# 02 - Architecture Map

```mermaid
graph TD
    ENV[".env / config.py"] --> DB["db.py (SQLite)"]
    ENV --> MT5C["mt5_connector.py"]
    MT5C --> MT5_TERM["MetaTrader 5 Terminal / MockMT5"]
    
    subgraph Data Layer
        DB --> T1["orders"]
        DB --> T2["bot_signals"]
        DB --> T3["daily_equity"]
        DB --> T4["bot_logs"]
    end

    subgraph Quantitative AI Brain
        PA["ai_price_action.py (6 Market Cases A-F & Compression)"]
        MATH["ai_math_models.py (ML/DL, HMM, OOD, Monte Carlo VaR)"]
        MODEL["models/lgbm_forex_model.pkl"]
        MATH --> MODEL
    end

    subgraph Trading Execution & Risk Control
        RISK["risk_manager.py (1R Sizing, R:R >= 1.5, LOCK_BOT_24H)"]
        EXEC["executor.py (MT5Executor)"]
        ENGINE["ai_trading_engine.py (AITradingEngine Loop)"]
        
        PA --> ENGINE
        MATH --> ENGINE
        RISK --> ENGINE
        ENGINE --> EXEC
        EXEC --> MT5C
        EXEC --> DB
        ENGINE --> DB
    end

    subgraph Realtime Web Terminal
        WEB["web_app.py (FastAPI)"]
        WS["WebSocket (/ws/live)"]
        UI["templates/index.html & dashboard.js"]
        
        ENGINE --> WS
        WS --> UI
        WEB --> UI
        WEB --> DB
    end
```

## Layer Definitions
1. **Config Layer**: Single-point configuration loader (`config.py`).
2. **Storage Layer**: SQLite (`db.py`) handling trade journals, signals with Market Case/Regime tags, daily equity, and system logs.
3. **Broker Interface**: MT5 Python API bridge (`mt5_connector.py`) with cross-platform MockMT5 support.
4. **Quantitative AI Brain**: 6 Market Cases Price Action (`ai_price_action.py`), Vectorized ML/DL, Gaussian HMM Regimes, and Isolation Forest OOD filter (`ai_math_models.py`).
5. **Risk & Execution Layer**: 1R position sizing, $R:R \ge 1.5$ guard, 24h circuit breaker (`risk_manager.py`), MT5 order execution (`executor.py`), and master orchestrator (`ai_trading_engine.py`).
6. **Realtime Web Terminal**: FastAPI backend with WebSocket streaming `/ws/live` pushing live ticks, dynamic candle updates, AI HUD metrics, and live VNĐ wallet directly to the browser (`dashboard.js`, `lightweight-charts.js`).
