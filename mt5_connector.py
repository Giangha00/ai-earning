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
                self.balance = float(getattr(config, "MT5_BALANCE", 10000.0))
            self.equity = self.balance
            self.currency = "USD"
            self.leverage = 100
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
            self.volume_min = 0.01
            self.volume_max = 100.0
            self.volume_step = 0.01
            self.bid = info.get("base", 1.1260)
            self.ask = round(self.bid + self.spread * self.point, self.digits)
            self.last = self.ask

    class MockTick:
        def __init__(self, symbol: str = "EURUSD"):
            is_gold = "XAU" in symbol or "GOLD" in symbol
            base = 2650.0 if is_gold else 1.1260
            spread = 0.30 if is_gold else 0.00015
            self.bid = base
            self.ask = round(base + spread, 2 if is_gold else 5)
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
            self.magic = magic
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
        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        POSITION_TYPE_BUY = 0
        POSITION_TYPE_SELL = 1
        ORDER_TIME_GTC = 0
        ORDER_FILLING_IOC = 1
        ORDER_FILLING_FOK = 0

        _positions = {}
        _ticket_counter = 1000000
        _last_prices = {"EURUSD": 1.12600, "XAUUSD": 2650.50}

        @classmethod
        def set_symbol_price(cls, symbol: str, price: float):
            """Đồng bộ mức giá khởi tạo từ dữ liệu nến thực tế để tránh nhảy gáp."""
            is_gold = "XAU" in symbol or "GOLD" in symbol
            key = "XAUUSD" if is_gold else "EURUSD"
            cls._last_prices[key] = round(float(price), 2 if is_gold else 5)

        @classmethod
        def symbol_info_tick(cls, symbol: str):
            is_gold = "XAU" in symbol or "GOLD" in symbol
            key = "XAUUSD" if is_gold else "EURUSD"
            prev_price = cls._last_prices.get(key, 2650.0 if is_gold else 1.12600)

            # Mô phỏng biến động tick ngẫu nhiên sinh động (Brownian motion micro-ticks)
            volatility = 0.20 if is_gold else 0.00008
            drift = float(np.random.normal(0, volatility))
            new_price = round(prev_price + drift, 2 if is_gold else 5)
            cls._last_prices[key] = new_price

            spread = 0.30 if is_gold else 0.00015
            tick = MockTick(symbol)
            tick.bid = new_price
            tick.ask = round(new_price + spread, 2 if is_gold else 5)
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
                        return MockOrderResult(cls.TRADE_RETCODE_DONE, pos_ticket, request.get("price", pos.price_open), "Position closed")
                    return MockOrderResult(cls.TRADE_RETCODE_REJECT, 0, 0.0, "Position not found")

                # Mở lệnh mới
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
        def account_info(cls):
            return MockAccountInfo(config.MT5_LOGIN, config.MT5_SERVER, cls._account_balance)

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

    mt5 = MockMT5()
    import sys
    sys.modules.setdefault("MetaTrader5", mt5)


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
