import importlib
import logging
import time
from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

# Kiểm tra thư viện MetaTrader5 chính thức (chỉ có trên Windows)
# Trên macOS / Linux: tự động kích hoạt MockMT5 để phát triển & test thử logic
try:
    mt5 = importlib.import_module("MetaTrader5")
    IS_SIMULATION = False
except (ImportError, ModuleNotFoundError):
    IS_SIMULATION = True
    import numpy as np
    import exness_markets
    from db import get_setting

    class MockAccountInfo:
        def __init__(self, login: int, server: str, balance: float = None):
            self.login = login
            self.name = f"Tài khoản Exness Trial #{login}"
            self.server = server
            if balance is not None:
                self.balance = float(balance)
            else:
                saved_bal = get_setting("account_balance", "")
                if saved_bal:
                    try:
                        self.balance = float(saved_bal)
                        config.MT5_BALANCE = self.balance
                    except ValueError:
                        self.balance = float(getattr(config, "MT5_BALANCE", 10000.0))
                else:
                    self.balance = float(getattr(config, "MT5_BALANCE", 10000.0))
            self.equity = self.balance
            self.currency = "USD"
            self.leverage = 100
            self.margin = 0.0
            self.margin_free = self.balance
            self.margin_level = 500.0

    class MockSymbolInfo:
        def __init__(self, symbol: str):
            info = exness_markets.get_market_by_symbol(symbol)
            self.name = symbol
            self.description = info.get("name", symbol)
            self.category = info.get("category", "Forex")
            self.visible = True
            self.digits = info.get("digits", 5)
            self.point = info.get("point", 0.00001)
            self.spread = info.get("spread", 15)
            self.trade_tick_size = self.point
            self.trade_tick_value = 1.0
            self.trade_contract_size = (
                1.0 if "BTC" in symbol or "ETH" in symbol or self.category in ("Crypto", "Chỉ số", "Cổ phiếu")
                else (100.0 if "XAU" in symbol or "GOLD" in symbol else 100000.0)
            )
            self.volume_min = 0.01
            self.volume_max = 100.0
            self.volume_step = 0.01
            self.bid = info.get("base", 1.1260)
            self.ask = round(self.bid + self.spread * self.point, self.digits)
            self.last = self.ask

    class MockTick:
        def __init__(self, symbol: str = "EURUSD"):
            info = exness_markets.get_market_by_symbol(symbol)
            digits = int(info.get("digits", 5))
            point = float(info.get("point", 0.00001))
            spread_pts = float(info.get("spread", 15))
            base = float(info.get("base", 1.1260))
            spread = spread_pts * point
            self.bid = base
            self.ask = round(base + spread, digits)
            self.last = self.ask
            self.volume = 100
            self.time = int(time.time())

    class MockPosition:
        def __init__(self, ticket: int, symbol: str, p_type: int, volume: float, price_open: float, sl: float, tp: float, magic: int = 888888, comment: str = ""):
            self.ticket = ticket
            self.symbol = symbol
            self.type = p_type
            self.volume = volume
            self.price_open = price_open
            self.price_current = price_open
            self.sl = sl
            self.tp = tp
            self.swap = 0.0
            self.commission = -round(float(volume) * float(getattr(config, "COMMISSION_PER_LOT_USD", 7.0)), 2)
            self.profit = 0.0
            self.time = int(time.time())
            self.magic = magic
            self.comment = comment

    class MockDeal:
        def __init__(self, ticket: int, position_id: int, symbol: str, entry: int, deal_type: int, volume: float, price: float, profit: float, commission: float, swap: float, fee: float = 0.0, comment: str = ""):
            self.ticket = ticket
            self.position_id = position_id
            self.symbol = symbol
            self.entry = entry  # 0: IN, 1: OUT
            self.type = deal_type
            self.volume = volume
            self.price = price
            self.profit = profit
            self.commission = commission
            self.swap = swap
            self.fee = fee
            self.time = int(time.time())
            self.comment = comment

    class MockOrderResult:
        def __init__(self, retcode: int, order: int, price: float, comment: str = "Request executed"):
            self.retcode = retcode
            self.order = order
            self.price = price
            self.comment = comment

    class MockMT5:
        """Bộ giả lập MT5 khi chạy trên macOS / Linux hoặc môi trường không cài MT5 Windows."""
        TIMEFRAME_M1 = 1
        TIMEFRAME_M5 = 5
        TIMEFRAME_M15 = 15
        TIMEFRAME_M30 = 30
        TIMEFRAME_H1 = 16385
        TIMEFRAME_H4 = 16388
        TIMEFRAME_D1 = 16408

        # Retcodes
        TRADE_RETCODE_DONE = 10009
        TRADE_RETCODE_REQUOTE = 10004
        TRADE_RETCODE_REJECT = 10006
        TRADE_RETCODE_PRICE_OFF = 10008
        TRADE_RETCODE_INVALID_PRICE = 10015
        TRADE_RETCODE_INVALID_STOPS = 10016
        TRADE_RETCODE_INVALID_VOLUME = 10014
        TRADE_RETCODE_MARKET_CLOSED = 10018
        TRADE_RETCODE_NO_MONEY = 10019
        TRADE_RETCODE_TRADE_DISABLED = 10017

        # Actions & Types
        TRADE_ACTION_DEAL = 1
        TRADE_ACTION_SLTP = 6
        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        POSITION_TYPE_BUY = 0
        POSITION_TYPE_SELL = 1
        ORDER_TIME_GTC = 0
        ORDER_FILLING_IOC = 1
        ORDER_FILLING_FOK = 0

        _positions = {}
        _history_deals = {}
        _ticket_counter = 1000000
        _last_prices = {"EURUSD": 1.12600, "XAUUSD": 2650.50}
        _last_tick_ts = {}

        @classmethod
        def set_symbol_price(cls, symbol: str, price: float):
            """Đồng bộ mức giá khởi tạo từ dữ liệu nến thực tế cho bất kỳ mã nào trong 355 thị trường."""
            sym = (symbol or "EURUSD").upper()
            info = exness_markets.get_market_by_symbol(sym)
            digits = int(info.get("digits", 5))
            cls._last_prices[sym] = round(float(price), digits)
            cls._last_tick_ts[sym] = time.monotonic()

        @classmethod
        def symbol_info_tick(cls, symbol: str):
            sym = (symbol or "EURUSD").upper()
            info = exness_markets.get_market_by_symbol(sym)
            digits = int(info.get("digits", 5))
            point = float(info.get("point", 0.00001))
            spread_pts = float(info.get("spread", 15))
            base_default = float(info.get("base", 1.12600))
            prev_price = cls._last_prices.get(sym, base_default)

            # Giữ nguyên mức giá tick trong cùng một chu kỳ khớp lệnh (< 1.0s) để giá kiểm tra và giá đặt/đóng lệnh khớp 100%
            now_mono = time.monotonic()
            last_mono = cls._last_tick_ts.get(sym, 0.0)
            if (now_mono - last_mono) >= 1.0:
                cat = info.get("category", "Forex")
                if cat == "Crypto":
                    volatility = max(point * 5, prev_price * 0.00025)
                elif cat in ("Kim loại & Dầu", "Chỉ số", "Cổ phiếu"):
                    volatility = max(point * 3, prev_price * 0.00015)
                else:
                    volatility = max(point * 5, 0.00005 if digits == 5 else 0.005)
                trend_bias = volatility * 0.25
                drift = float(np.random.normal(trend_bias, volatility))
                new_price = round(prev_price + drift, digits)
                cls._last_prices[sym] = new_price
                cls._last_tick_ts[sym] = now_mono
            else:
                new_price = prev_price

            spread = spread_pts * point
            tick = MockTick(sym)
            tick.bid = new_price
            tick.ask = round(new_price + spread, digits)
            tick.last = tick.ask
            tick.time = int(time.time())
            return tick

        @classmethod
        def order_send(cls, request: dict):
            action = request.get("action")
            if action == cls.TRADE_ACTION_DEAL:
                # Nếu đóng lệnh (truyền ticket vị thế qua tham số position)
                pos_ticket = request.get("position")
                if pos_ticket is not None:
                    if pos_ticket in cls._positions:
                        pos = cls._positions.pop(pos_ticket)
                        close_p = float(request.get("price", pos.price_open))
                        mult = get_contract_multiplier(pos.symbol)
                        gross = (
                            (close_p - pos.price_open) * mult * pos.volume
                            if pos.type == cls.POSITION_TYPE_BUY
                            else (pos.price_open - close_p) * mult * pos.volume
                        )
                        comm = -round(float(pos.volume) * float(getattr(config, "COMMISSION_PER_LOT_USD", 7.0)), 2)
                        swap_val = float(getattr(pos, "swap", 0.0))
                        cls._history_deals[pos_ticket] = [
                            MockDeal(
                                ticket=pos_ticket * 10 + 1,
                                position_id=pos_ticket,
                                symbol=pos.symbol,
                                entry=1,
                                deal_type=request.get("type", cls.ORDER_TYPE_SELL),
                                volume=pos.volume,
                                price=close_p,
                                profit=round(gross, 2),
                                commission=comm,
                                swap=swap_val,
                                comment=request.get("comment", "Position closed"),
                            )
                        ]
                        return MockOrderResult(cls.TRADE_RETCODE_DONE, pos_ticket, close_p, "Position closed")
                    return MockOrderResult(cls.TRADE_RETCODE_REJECT, 0, 0.0, "Position not found")

                # Mở lệnh mới (đồng bộ _ticket_counter với MAX(ticket_id) trong SQLite để không bao giờ trùng khóa chính)
                try:
                    from db import get_connection
                    with get_connection() as conn:
                        row = conn.execute("SELECT MAX(ticket_id) FROM orders;").fetchone()
                        if row and row[0] and int(row[0]) >= cls._ticket_counter:
                            cls._ticket_counter = int(row[0])
                except Exception:
                    pass
                cls._ticket_counter += 1
                ticket = cls._ticket_counter
                symbol = request.get("symbol", "EURUSD")
                p_type = request.get("type", cls.ORDER_TYPE_BUY)
                volume = request.get("volume", 0.01)
                price = request.get("price", 1.0850)
                sl = request.get("sl", 0.0)
                tp = request.get("tp", 0.0)
                magic = request.get("magic", 888888)
                comment = request.get("comment", "")

                pos = MockPosition(ticket, symbol, p_type, volume, price, sl, tp, magic, comment)
                cls._positions[ticket] = pos
                return MockOrderResult(cls.TRADE_RETCODE_DONE, ticket, price, "Request executed")

            if action == cls.TRADE_ACTION_SLTP:
                pos_ticket = int(request.get("position", 0))
                if pos_ticket in cls._positions:
                    pos = cls._positions[pos_ticket]
                    if "sl" in request and request["sl"] is not None:
                        pos.sl = float(request["sl"])
                    if "tp" in request and request["tp"] is not None:
                        pos.tp = float(request["tp"])
                    return MockOrderResult(cls.TRADE_RETCODE_DONE, pos_ticket, pos.price_current, "SL/TP modified")
                return MockOrderResult(cls.TRADE_RETCODE_REJECT, 0, 0.0, "Position not found")

            return MockOrderResult(cls.TRADE_RETCODE_REJECT, 0, 0.0, "Action not supported")

        @classmethod
        def positions_get(cls, ticket=None, symbol=None, group=None):
            if ticket is not None:
                if ticket in cls._positions:
                    return (cls._positions[ticket],)
                return ()
            positions = list(cls._positions.values())
            if symbol is not None:
                positions = [p for p in positions if p.symbol == symbol]
            return tuple(positions)

        _account_balance: float = None

        @classmethod
        def set_balance(cls, balance: float):
            """Cập nhật số dư tài khoản thực tế từ Exness."""
            cls._account_balance = float(balance)

        @staticmethod
        def initialize(**kwargs) -> bool:
            return True

        @staticmethod
        def login(login: int, password: str, server: str) -> bool:
            return True

        @classmethod
        def history_deals_get(cls, date_from=None, date_to=None, group=None, ticket=None, position=None):
            if position is not None:
                return tuple(cls._history_deals.get(int(position), []))
            all_deals = []
            for deals in cls._history_deals.values():
                all_deals.extend(deals)
            return tuple(all_deals)

        @classmethod
        def order_calc_margin(cls, action: int, symbol: str, volume: float, price: float) -> float:
            """Tính tiền ký quỹ (Margin USD) cần thiết để mở lệnh theo đòn bẩy tài khoản."""
            mult = get_contract_multiplier(symbol)
            leverage = 100.0
            notional_usd = float(volume) * mult * float(price if price > 0 else 1.0)
            if symbol.startswith("USD") and symbol not in ("USDX",):
                notional_usd = float(volume) * mult
            return round(notional_usd / leverage, 2)

        @classmethod
        def account_info(cls):
            acc = MockAccountInfo(config.MT5_LOGIN, config.MT5_SERVER, cls._account_balance)
            # Tính Equity, Margin, Free Margin thực tế tự động trừ sạch phí Commission (7 USD/lot), Swap và Spread thả nổi
            floating_net = 0.0
            used_margin = 0.0
            comm_per_lot = float(getattr(config, "COMMISSION_PER_LOT_USD", 7.0))
            for pos in cls._positions.values():
                sym = (pos.symbol or "EURUSD").upper()
                info = exness_markets.get_market_by_symbol(sym)
                digits = int(info.get("digits", 5))
                point = float(info.get("point", 0.00001))
                spread_val = float(info.get("spread", 15)) * point
                bid_p = cls._last_prices.get(sym, pos.price_open)
                ask_p = round(bid_p + spread_val, digits)
                mult = get_contract_multiplier(sym)
                gross = (bid_p - pos.price_open) * mult * pos.volume if pos.type == cls.POSITION_TYPE_BUY else (pos.price_open - ask_p) * mult * pos.volume
                swap_val = float(getattr(pos, "swap", 0.0))
                floating_net += gross - (pos.volume * comm_per_lot) + swap_val
                used_margin += cls.order_calc_margin(pos.type, sym, pos.volume, pos.price_open)
            acc.equity = round(acc.balance + floating_net, 2)
            acc.margin = round(used_margin, 2)
            acc.margin_free = round(max(0.0, acc.equity - acc.margin), 2)
            acc.margin_level = round((acc.equity / acc.margin) * 100.0, 2) if acc.margin > 0 else 500.0
            return acc

        @staticmethod
        def symbols_total() -> int:
            """Tổng số lượng thị trường trên sàn Exness."""
            return len(exness_markets.ALL_EXNESS_MARKETS)

        @staticmethod
        def symbols_get(group: str = None) -> tuple:
            """Trả về toàn bộ danh sách thị trường có sẵn trên Exness."""
            all_syms = exness_markets.ALL_EXNESS_MARKETS
            if group:
                all_syms = [m for m in all_syms if group.lower() in m.get("category", "").lower()]
            return tuple(MockSymbolInfo(m["symbol"]) for m in all_syms)

        @staticmethod
        def symbol_info(symbol: str):
            return MockSymbolInfo(symbol)

        @staticmethod
        def symbol_select(symbol: str, enable: bool = True) -> bool:
            return True

        @staticmethod
        def copy_rates_from_pos(symbol: str, tf: int, start_pos: int, count: int):
            """Tạo dữ liệu nến giả lập định dạng NumPy structured array chuẩn của MetaTrader 5."""
            now = int(time.time())
            # Giả định bước thời gian: tf (phút) * 60 (giây), mặc định 300s cho M5
            step_seconds = 300 if tf not in (1, 5, 15, 30, 16385, 16388, 16408) else (
                60 if tf == 1 else
                300 if tf == 5 else
                900 if tf == 15 else
                1800 if tf == 30 else
                3600 if tf == 16385 else
                14400 if tf == 16388 else 86400
            )
            timestamps = now - np.arange(count, 0, -1, dtype=np.int64) * step_seconds
            
            # Base price & biến động theo đúng loại tài sản Exness
            info = exness_markets.get_market_by_symbol(symbol)
            base_price = float(info.get("base", 1.1260))
            cat = info.get("category", "")
            if cat == "Crypto":
                volatility = base_price * 0.0008
            elif cat == "Kim loại & Dầu":
                volatility = base_price * 0.0004
            elif cat == "Chỉ số":
                volatility = base_price * 0.0003
            elif cat == "Cổ phiếu":
                volatility = base_price * 0.0008
            else:
                volatility = 0.0002

            returns = np.random.normal(0, volatility, count)
            close_p = base_price + np.cumsum(returns)
            open_p = np.roll(close_p, 1)
            open_p[0] = base_price
            high_p = np.maximum(open_p, close_p) + np.abs(np.random.normal(0, volatility * 0.5, count))
            low_p = np.minimum(open_p, close_p) - np.abs(np.random.normal(0, volatility * 0.5, count))
            tick_volume = np.random.randint(50, 1500, count, dtype=np.uint64)
            spread = np.full(count, 12, dtype=np.int32)
            real_volume = np.zeros(count, dtype=np.uint64)

            dtype = [
                ("time", "<i8"),
                ("open", "<f8"),
                ("high", "<f8"),
                ("low", "<f8"),
                ("close", "<f8"),
                ("tick_volume", "<u8"),
                ("spread", "<i4"),
                ("real_volume", "<u8")
            ]
            rates = np.empty(count, dtype=dtype)
            rates["time"] = timestamps
            rates["open"] = open_p
            rates["high"] = high_p
            rates["low"] = low_p
            rates["close"] = close_p
            rates["tick_volume"] = tick_volume
            rates["spread"] = spread
            rates["real_volume"] = real_volume
            return rates

        @staticmethod
        def copy_rates_range(symbol: str, tf: int, start_date, end_date):
            start_ts = int(start_date.timestamp())
            end_ts = int(end_date.timestamp())
            step_seconds = 300 if tf not in (1, 5, 15, 30, 16385, 16388, 16408) else (
                60 if tf == 1 else
                300 if tf == 5 else
                900 if tf == 15 else
                1800 if tf == 30 else
                3600 if tf == 16385 else
                14400 if tf == 16388 else 86400
            )
            count = max(1, (end_ts - start_ts) // step_seconds)
            rates = MockMT5.copy_rates_from_pos(symbol, tf, 0, count)
            # Đồng bộ timestamps chính xác trong khoảng start_date -> end_date
            rates["time"] = np.arange(start_ts, start_ts + count * step_seconds, step_seconds, dtype=np.int64)[:count]
            return rates

        @staticmethod
        def shutdown() -> None:
            pass

        @staticmethod
        def last_error():
            return (0, "Success (Simulation)")

    _mock_mt5 = MockMT5()
    try:
        from mt5_wine_bridge import WineMT5Bridge
        if WineMT5Bridge.is_available():
            mt5 = WineMT5Bridge(fallback_mock=_mock_mt5)
            IS_SIMULATION = False
        else:
            mt5 = _mock_mt5
            IS_SIMULATION = True
    except Exception as _bridge_err:
        logging.warning(f"Không thể khởi tạo WineMT5Bridge, chuyển về MockMT5: {_bridge_err}")
        mt5 = _mock_mt5
        IS_SIMULATION = True

    import sys
    sys.modules.setdefault("MetaTrader5", mt5)


def get_pip_size(symbol: str, info=None) -> float:
    """
    Trả về kích thước 1 Pip chuẩn theo từng nhóm tài sản trên MT5 / Exness:
    - Vàng / Bạc (XAUUSD, XAGUSD): 1 pip = 0.10
    - Crypto / Chỉ số (BTCUSD, ETHUSD, US30, NAS100, US500...): 1 pip = 1.0
    - Cặp JPY (USDJPY, EURJPY, GBPJPY...): 1 pip = 0.01
    - Cổ phiếu / Dầu (2 chữ số thập phân): 1 pip = 0.10
    - Forex chuẩn 5 chữ số (EURUSD, GBPUSD...): 1 pip = 0.0001 (point * 10)
    """
    sym = (symbol or "EURUSD").upper()
    if info is None and mt5:
        info = mt5.symbol_info(sym)
    if "XAU" in sym or "GOLD" in sym or "XAG" in sym:
        return 0.1
    if any(k in sym for k in ("BTC", "ETH", "SOL", "BNB", "BCH", "US30", "NAS100", "US500", "USTEC", "DE30", "JP225", "UK100")):
        return 1.0
    if "JPY" in sym:
        return 0.01
    if info and getattr(info, "digits", 5) == 2:
        return 0.1
    if info and getattr(info, "digits", 5) in (3, 5):
        return float(info.point) * 10.0
    return float(getattr(info, "point", 0.0001)) if info else 0.0001


def get_current_spread_pips(symbol: str) -> float:
    """
    Hàm đo Spread thực tế từ MT5 quy đổi sang đơn vị Pips (Mục 2.2 Tài liệu Nâng cấp):
    - Trước mỗi lần chuẩn bị phát lệnh order_send(), lấy báo giá thực tế ask và bid.
    - Nếu không lấy được tick hoặc symbol_info, trả về 999.0 để chặn lệnh an toàn.
    """
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if not tick or not info:
        return 999.0
    raw_spread = float(tick.ask - tick.bid)
    divider = get_pip_size(symbol, info)
    return round(raw_spread / divider, 2) if divider > 0 else 999.0


def get_contract_multiplier(symbol: str) -> float:
    """
    Trả về quy mô hợp đồng (Contract Size) chuẩn cho từng loại tài sản trên Ví thực MT5:
    - Crypto (BTCUSD, ETHUSD) / Chỉ số (US30, NAS100, US500) / Cổ phiếu: 1 Lot = 1 đơn vị (1.0)
    - Vàng (XAUUSD, GOLD): 1 Lot = 100 oz (100.0)
    - Bạc (XAGUSD): 1 Lot = 5,000 oz (5000.0)
    - Dầu (USOIL, UKOIL): 1 Lot = 1,000 thùng (1000.0)
    - Forex chuẩn (EURUSD, GBPUSD, USDJPY...): 1 Lot = 100,000 đơn vị tiền tệ cơ sở (100000.0)
    """
    sym = (symbol or "EURUSD").upper()
    info = mt5.symbol_info(sym) if mt5 else None
    if info and hasattr(info, "trade_contract_size") and float(getattr(info, "trade_contract_size", 0)) > 0:
        return float(info.trade_contract_size)
    if any(k in sym for k in ("BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "US30", "NAS100", "US500", "USTEC", "DE30", "JP225")):
        return 1.0
    if "XAU" in sym or "GOLD" in sym:
        return 100.0
    if "XAG" in sym:
        return 5000.0
    if "OIL" in sym:
        return 1000.0
    return 100000.0


def get_pip_value_per_lot(symbol: str, current_price: float = 0.0) -> float:
    """
    Tính chính xác giá trị 1 Pip trên 1 Standard Lot (USD) cho mọi cặp tiền/tài sản:
    - Cặp XXXUSD (EURUSD, GBPUSD, AUDUSD, XAUUSD...): $10.0 / pip / lot
    - Cặp USDXXX (USDJPY, USDCAD, USDCHF...): $10.0 / tỷ giá (nếu JPY thì 1000.0 / tỷ giá)
    - BTCUSD / Crypto (1 pip = $1.0, 1 lot = 1 coin): $1.0 / pip / lot
    """
    sym = (symbol or "EURUSD").upper()
    if current_price <= 0 and mt5:
        tick = mt5.symbol_info_tick(sym)
        if tick:
            current_price = float(tick.ask or tick.bid or 0.0)

    if any(k in sym for k in ("BTC", "ETH", "SOL", "US30", "NAS100", "US500")):
        return 1.0
    if "XAU" in sym or "GOLD" in sym:
        return 10.0
    if sym.endswith("USD"):
        return 10.0
    if sym.startswith("USD") and current_price > 0:
        if "JPY" in sym:
            return round(1000.0 / current_price, 4)
        return round(10.0 / current_price, 4)
    return 10.0


def calculate_rollover_swap(symbol: str, lot_size: float, open_time_str: str = None) -> float:
    """
    Tính phí qua đêm (Swap / Rollover USD) khi giữ lệnh qua mốc 00:00 Server.
    Đêm Thứ Tư sang Thứ Năm (weekday == 2) tính Swap x3 theo chuẩn sàn Quốc tế.
    """
    if not open_time_str:
        return 0.0
    try:
        from datetime import datetime, timedelta
        open_dt = datetime.strptime(str(open_time_str)[:19], "%Y-%m-%d %H:%M:%S")
        now_dt = datetime.now()
        if now_dt.date() <= open_dt.date():
            return 0.0

        sym = (symbol or "EURUSD").upper()
        swap_rates = getattr(config, "SWAP_PER_LOT_DAILY_USD", {})
        daily_rate = float(swap_rates.get(sym, swap_rates.get("DEFAULT", -3.0)))

        total_nights = 0
        cur_date = open_dt.date()
        while cur_date < now_dt.date():
            # Đêm Thứ Tư (weekday == 2) bị tính phí Swap x3
            total_nights += 3 if cur_date.weekday() == 2 else 1
            cur_date += timedelta(days=1)

        return round(float(lot_size) * daily_rate * total_nights, 2)
    except Exception:
        return 0.0


def get_position_swap_and_commission(
    ticket: int,
    symbol: str,
    lot_size: float,
    open_time_str: str = None,
) -> tuple[float, float]:
    """
    Trả về (swap_usd, commission_usd) của một lệnh mở hoặc vừa đóng trên Ví thực:
    - Ưu tiên đọc trực tiếp `pos.swap` và `pos.commission` từ Terminal MT5 thật.
    - Nếu sàn tính commission ở deal hoặc chạy giả lập, áp dụng COMMISSION_PER_LOT_USD (7.0 USD/lot) và rollover swap.
    """
    comm_per_lot = float(getattr(config, "COMMISSION_PER_LOT_USD", 7.0))
    default_comm = round(float(lot_size) * comm_per_lot, 2)
    swap_usd = calculate_rollover_swap(symbol, lot_size, open_time_str)

    if mt5 and ticket:
        positions = mt5.positions_get(ticket=int(ticket))
        if positions:
            pos = positions[0]
            mt5_swap = float(getattr(pos, "swap", 0.0))
            if mt5_swap != 0.0:
                swap_usd = round(mt5_swap, 2)
            mt5_comm = abs(float(getattr(pos, "commission", 0.0)))
            if mt5_comm > 0.0:
                default_comm = round(mt5_comm, 2)
    return swap_usd, default_comm


def sync_closed_deal_from_mt5(ticket: int) -> dict | None:
    """
    Kiểm tra lịch sử khớp lệnh thực tế `mt5.history_deals_get(position=ticket)` từ Terminal MT5
    để đồng bộ những vị thế đã tự đóng trên Server Exness (do chạm SL/TP trên sàn hoặc đóng trên điện thoại).
    """
    if not mt5 or not ticket or not hasattr(mt5, "history_deals_get"):
        return None
    try:
        deals = mt5.history_deals_get(position=int(ticket))
        if not deals:
            return None
        # Tìm deal đóng vị thế (entry == 1: DEAL_ENTRY_OUT)
        out_deals = [d for d in deals if getattr(d, "entry", 1) == 1]
        target_deal = out_deals[-1] if out_deals else deals[-1]
        gross_profit = float(getattr(target_deal, "profit", 0.0))
        total_comm = sum(abs(float(getattr(d, "commission", 0.0))) for d in deals)
        total_swap = sum(float(getattr(d, "swap", 0.0)) for d in deals)
        total_fee = sum(float(getattr(d, "fee", 0.0)) for d in deals)
        vol = float(getattr(target_deal, "volume", 0.01))
        if total_comm == 0.0:
            total_comm = round(vol * float(getattr(config, "COMMISSION_PER_LOT_USD", 7.0)), 2)
        net_profit = round(gross_profit - total_comm + total_swap + total_fee, 2)
        return {
            "close_price": float(getattr(target_deal, "price", 0.0)),
            "gross_profit": round(gross_profit, 2),
            "commission": round(total_comm, 2),
            "swap": round(total_swap, 2),
            "net_profit": net_profit,
            "comment": str(getattr(target_deal, "comment", "MT5_DEAL_SYNC")),
        }
    except Exception:
        return None


class MT5Connector:
    @staticmethod
    def connect() -> bool:
        """Khởi động terminal và đăng nhập vào tài khoản sàn."""
        if IS_SIMULATION:
            logging.warning(
                "⚠️ Đang chạy ở chế độ Giả lập (Simulation Mode) vì macOS không hỗ trợ thư viện MetaTrader5 native (yêu cầu Windows/VPS). "
                "Hệ thống sẽ sử dụng dữ liệu mẫu để bạn kiểm thử logic."
            )

        # 1. Khởi tạo terminal MT5
        init_params = {}
        if config.MT5_PATH:
            init_params["path"] = config.MT5_PATH

        if not mt5.initialize(**init_params):
            logging.error(f"Khởi tạo MT5 thất bại, mã lỗi: {mt5.last_error()}")
            return False

        # 2. Đăng nhập vào broker
        authorized = mt5.login(
            login=config.MT5_LOGIN,
            password=config.MT5_PASSWORD,
            server=config.MT5_SERVER
        )

        if not authorized:
            logging.error(f"Đăng nhập thất bại vào tài khoản {config.MT5_LOGIN}, mã lỗi: {mt5.last_error()}")
            mt5.shutdown()
            return False

        account_info = mt5.account_info()
        if account_info is None:
            logging.error("Không lấy được thông tin tài khoản.")
            mt5.shutdown()
            return False

        logging.info("=== Kết nối MT5 thành công ===")
        logging.info(f"Tài khoản: {account_info.login} ({account_info.name})")
        logging.info(f"Server: {account_info.server}")
        logging.info(f"Số dư (Balance): {account_info.balance} {account_info.currency}")
        logging.info(f"Tài sản ròng (Equity): {account_info.equity} {account_info.currency}")
        logging.info(f"Đòn bẩy (Leverage): 1:{account_info.leverage}")

        # Tự động đồng bộ số dư ví Exness thực tế
        config.MT5_BALANCE = float(account_info.balance)
        return True

    @staticmethod
    def disconnect():
        """Đóng kết nối MT5 an toàn."""
        mt5.shutdown()
        logging.info("Đã đóng kết nối MT5.")


if __name__ == "__main__":
    # Test thử kết nối
    if MT5Connector.connect():
        MT5Connector.disconnect()
