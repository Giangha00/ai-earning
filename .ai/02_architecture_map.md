# 02 - Architecture Map

```mermaid
graph TD
    ENV[".env / config.py"] --> DB["db.py (SQLite)"]
    ENV --> MT5C["mt5_connector.py"]
    MT5C --> MT5_TERM["MetaTrader 5 Terminal"]
    
    subgraph Data Layer
        DB --> T1["orders"]
        DB --> T2["bot_signals"]
        DB --> T3["daily_equity"]
        DB --> T4["bot_logs"]
    end

    subgraph Future Modules
        SIG["signals.py (RSI, ATR, ADX)"] --> EXEC["execution.py"]
        EXEC --> MT5C
        EXEC --> DB
    end
```

## Layer Definitions
1. **Config Layer**: Single-point configuration loader (`config.py`).
2. **Storage Layer**: SQLite (`db.py`) handling trade journals, signal history, equity logs, system diagnostics.
3. **Broker Interface**: MT5 Python API bridge (`mt5_connector.py`).
