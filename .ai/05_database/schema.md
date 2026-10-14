# Database Schema Documentation

SQLite Database: `trading_bot.db`

### 1. `orders` Table
Stores all order executions and closed trades.
- `ticket_id` (INTEGER, PK): MT5 order ticket ID
- `symbol` (TEXT): Trading instrument (e.g. `EURUSD`, `XAUUSD`)
- `order_type` (TEXT): `BUY` or `SELL`
- `lot_size` (REAL): Volume traded
- `open_time` (TIMESTAMP): Time order opened
- `open_price` (REAL): Entry price
- `close_time` (TIMESTAMP): Time order closed
- `close_price` (REAL): Exit price
- `stop_loss` (REAL): Stop loss level
- `take_profit` (REAL): Take profit level
- `commission` (REAL): Broker commission fee
- `swap` (REAL): Rollover swap fee
- `profit` (REAL): Net profit / loss
- `close_reason` (TEXT): Reason (e.g., SL hit, TP hit, manual, signal reversal)
- `status` (TEXT): `OPEN` or `CLOSED`

### 2. `bot_signals` Table
Records generated AI/technical indicators and signals.
- `id` (INTEGER, PK AUTOINCREMENT)
- `timestamp` (TIMESTAMP): Time signal was calculated
- `symbol` (TEXT): Target pair
- `signal_type` (TEXT): `BUY`, `SELL`, or `HOLD`
- `confidence` (REAL): Model confidence score
- `rsi_value` (REAL): RSI indicator reading
- `atr_value` (REAL): ATR volatility reading
- `adx_value` (REAL): ADX trend strength reading
- `executed` (INTEGER): `0` (not executed) or `1` (executed)
- `order_ticket` (INTEGER, FK -> orders.ticket_id)

### 3. `daily_equity` Table
Snapshots daily equity and performance.
- `date` (DATE, PK): Snapshot date (YYYY-MM-DD)
- `balance` (REAL): Account balance
- `equity` (REAL): Account equity
- `floating_pnl` (REAL): Unrealized profit/loss
- `total_trades` (INTEGER): Daily trade count
- `win_trades` (INTEGER): Daily winning trades

### 4. `bot_logs` Table
System audit logs.
- `id` (INTEGER, PK AUTOINCREMENT)
- `timestamp` (TIMESTAMP): Log event time
- `log_level` (TEXT): `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- `module` (TEXT): Source module
- `message` (TEXT): Log content
