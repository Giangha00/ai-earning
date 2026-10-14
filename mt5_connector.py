import logging
from config import config

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")

class MT5Connector:
    @staticmethod
    def connect() -> bool:
        """Khởi động terminal và đăng nhập vào tài khoản sàn."""
        if mt5 is None:
            logging.error(
                "Thư viện MetaTrader5 chưa được cài đặt hoặc không hỗ trợ trên hệ điều hành này. "
                "(MetaTrader5 package yêu cầu Windows với terminal MT5 64-bit hoặc Windows VPS)."
            )
            return False

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
        if mt5 is not None:
            mt5.shutdown()
        logging.info("Đã đóng kết nối MT5.")

if __name__ == "__main__":
    # Test thử kết nối
    if MT5Connector.connect():
        MT5Connector.disconnect()
