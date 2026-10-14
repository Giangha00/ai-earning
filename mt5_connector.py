import importlib
import logging
from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

# Kiểm tra thư viện MetaTrader5 chính thức (chỉ có trên Windows)
# Trên macOS / Linux: tự động kích hoạt MockMT5 để phát triển & test thử logic
try:
    mt5 = importlib.import_module("MetaTrader5")
    IS_SIMULATION = False
except (ImportError, ModuleNotFoundError):
    IS_SIMULATION = True

    class MockAccountInfo:
        def __init__(self, login: int, server: str):
            self.login = login
            self.name = "Demo Trader (Chế độ giả lập macOS)"
            self.server = server
            self.balance = 10000.0
            self.equity = 10000.0
            self.currency = "USD"
            self.leverage = 100

    class MockMT5:
        """Bộ giả lập MT5 khi chạy trên macOS / Linux hoặc môi trường không cài MT5 Windows."""
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
