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

    class MockAccountInfo:
        def __init__(self, login: int, server: str):
            self.login = login
            self.name = "Demo Trader (Chế độ giả lập macOS)"
            self.server = server
            self.balance = 10000.0
            self.equity = 10000.0
            self.currency = "USD"
            self.leverage = 100

    class MockSymbolInfo:
        def __init__(self, symbol: str):
            self.name = symbol
            self.visible = True

    class MockMT5:
        """Bộ giả lập MT5 khi chạy trên macOS / Linux hoặc môi trường không cài MT5 Windows."""
        TIMEFRAME_M1 = 1
        TIMEFRAME_M5 = 5
        TIMEFRAME_M15 = 15
        TIMEFRAME_M30 = 30
        TIMEFRAME_H1 = 16385
        TIMEFRAME_H4 = 16388
        TIMEFRAME_D1 = 16408

        @staticmethod
        def initialize(**kwargs) -> bool:
            return True

        @staticmethod
        def login(login: int, password: str, server: str) -> bool:
            return True

        @staticmethod
        def account_info():
            return MockAccountInfo(config.MT5_LOGIN, config.MT5_SERVER)

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
            
            # Base price tùy cặp
            base_price = 2650.0 if "XAU" in symbol or "GOLD" in symbol else 1.0850
            volatility = 0.5 if "XAU" in symbol or "GOLD" in symbol else 0.0003

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
