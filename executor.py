import importlib
import logging
from typing import Optional

# Import MetaTrader5 an toàn (native trên Windows, hoặc fallback giả lập trên macOS/Linux)
try:
    mt5 = importlib.import_module("MetaTrader5")
except (ImportError, ModuleNotFoundError):
    from mt5_connector import mt5

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")


class MT5Executor:
    # Bảng mô tả lỗi phổ biến từ MetaTrader 5
    RETCODE_MESSAGES = {
        mt5.TRADE_RETCODE_REQUOTE: "Báo giá lại (Requote)",
        mt5.TRADE_RETCODE_REJECT: "Sàn từ chối yêu cầu đặt lệnh",
        mt5.TRADE_RETCODE_PRICE_OFF: "Không có giá thị trường",
        mt5.TRADE_RETCODE_INVALID_PRICE: "Giá đặt không hợp lệ",
        mt5.TRADE_RETCODE_INVALID_STOPS: "Stop-Loss hoặc Take-Profit không hợp lệ (quá gần giá hiện tại)",
        mt5.TRADE_RETCODE_INVALID_VOLUME: "Khối lượng lot không hợp lệ",
        mt5.TRADE_RETCODE_MARKET_CLOSED: "Thị trường đang đóng cửa",
        mt5.TRADE_RETCODE_NO_MONEY: "Không đủ tiền ký quỹ (No money)",
        mt5.TRADE_RETCODE_TRADE_DISABLED: "Tài khoản bị sàn cấm giao dịch",
    }

    @staticmethod
    def _normalize_price(symbol: str, price: float) -> float:
        """Làm tròn mức giá theo số thập phân chuẩn (digits) của symbol."""
        info = mt5.symbol_info(symbol)
        if info is None:
            return price
        return round(price, info.digits)

    @classmethod
    def open_position(
        cls,
        symbol: str,
        order_type: str,     # 'BUY' hoặc 'SELL'
        lot_size: float,
        sl_price: float,
        tp_price: float,
        deviation: int = 20, # Độ trượt giá cho phép (slippage in points)
        magic_number: int = 888888,
        comment: str = "AI_LGBM_Trade",
    ) -> Optional[int]:
        """Gửi lệnh Market Order kèm SL/TP cứng lên MT5. Trả về ticket ID nếu thành công."""
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None or not symbol_info.visible:
            logging.error(f"Mã {symbol} không khả dụng.")
            return None

        # Xác định chiều lệnh và giá khớp
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logging.error(f"Không lấy được tick realtime của {symbol}.")
            return None

        if order_type.upper() == "BUY":
            mt5_action = mt5.ORDER_TYPE_BUY
            price = tick.ask
        elif order_type.upper() == "SELL":
            mt5_action = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            logging.error(f"Loại lệnh '{order_type}' không hợp lệ. Chọn 'BUY' hoặc 'SELL'.")
            return None

        # Chuẩn hóa mức giá
        price = cls._normalize_price(symbol, price)
        sl_price = cls._normalize_price(symbol, sl_price)
        tp_price = cls._normalize_price(symbol, tp_price)

        # Cấu hình request gửi lên sàn
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": mt5_action,
            "price": price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": deviation,
            "magic": magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,  # Immediate or Cancel (hoặc FOK tùy sàn)
        }

        # Gửi lệnh
        result = mt5.order_send(request)
        if result is None:
            logging.error(f"Lỗi hệ thống MT5 khi gửi lệnh: {mt5.last_error()}")
            return None

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            error_msg = cls.RETCODE_MESSAGES.get(result.retcode, f"Mã lỗi retcode={result.retcode}")
            logging.error(f"Gửi lệnh {order_type} thất bại: {error_msg} ({result.comment})")
            return None

        logging.info(
            f"Khớp lệnh thành công! Ticket: #{result.order} | {order_type} {lot_size} lot {symbol} "
            f"@ {result.price:.5f} | SL: {sl_price} | TP: {tp_price}"
        )
        return result.order

    @classmethod
    def close_position_by_ticket(cls, ticket_id: int, deviation: int = 20) -> bool:
        """Đóng một vị thế đang mở dựa theo ticket_id."""
        position = mt5.positions_get(ticket=ticket_id)
        if not position:
            logging.warning(f"Không tìm thấy vị thế mở với ticket #{ticket_id} (có thể đã chạm SL/TP tự đóng).")
            return False

        pos = position[0]
        symbol = pos.symbol
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logging.error(f"Không lấy được tick giá để đóng lệnh #{ticket_id}.")
            return False

        # Đảo chiều để đóng vị thế: Buy thì đóng bằng Sell (giá Bid), Sell đóng bằng Buy (giá Ask)
        if pos.type == mt5.POSITION_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            close_price = tick.bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            close_price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket_id,
            "symbol": symbol,
            "volume": pos.volume,
            "type": close_type,
            "price": cls._normalize_price(symbol, close_price),
            "deviation": deviation,
            "magic": pos.magic,
            "comment": "AI_Close_Order",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else mt5.last_error()
            logging.error(f"Đóng lệnh #{ticket_id} thất bại: {err}")
            return False

        logging.info(f"Đã đóng vị thế #{ticket_id} tại giá {result.price:.5f}.")
        return True

    @classmethod
    def get_open_positions(cls, magic_number: Optional[int] = None) -> list:
        """Lấy danh sách các lệnh đang chạy của bot."""
        positions = mt5.positions_get()
        if positions is None:
            return []

        if magic_number is not None:
            return [p for p in positions if p.magic == magic_number]
        return list(positions)

    @classmethod
    def close_all_positions(cls) -> int:
        """Quét và đóng sạch toàn bộ các vị thế đang mở trên sàn MT5/Exness."""
        return close_all_positions()


def close_all_positions() -> int:
    """
    Hàm đóng toàn bộ vị thế đang mở trên MT5 (Chương 3.2 - Cầu dao chốt lời tổng v2).
    Sử dụng deviation = 20 để đảm bảo khớp đóng tức thì ngay cả khi thị trường biến động.
    """
    closed_count = 0
    positions = mt5.positions_get()
    if positions:
        for pos in positions:
            tick = mt5.symbol_info_tick(pos.symbol)
            if tick is None:
                continue
            type_dict = {0: mt5.ORDER_TYPE_SELL, 1: mt5.ORDER_TYPE_BUY}
            price_dict = {0: tick.bid, 1: tick.ask}
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": type_dict.get(pos.type, mt5.ORDER_TYPE_SELL),
                "price": price_dict.get(pos.type, tick.bid),
                "deviation": 20,
                "magic": 100001,
                "comment": "Close All on Target Goal",
            }
            res = mt5.order_send(req)
            if res is not None:
                closed_count += 1
                logging.info(f"Đã đóng vị thế MT5 #{pos.ticket} ({pos.symbol}, {pos.volume} lot) do chạm mục tiêu chốt lời tổng.")

    # Đồng bộ đóng toàn bộ các lệnh đang OPEN trong SQLite Database để UI và số dư đồng nhất
    try:
        from datetime import datetime
        from db import get_connection, set_setting
        from config import config

        close_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT ticket_id, symbol, order_type, lot_size, open_price FROM orders WHERE status = 'OPEN';"
            )
            open_orders = cursor.fetchall()
            realized_delta = 0.0
            comm_per_lot = float(getattr(config, "COMMISSION_PER_LOT_USD", 7.0))
            for ticket_id, sym, o_type, lot, o_price in open_orders:
                tick = mt5.symbol_info_tick(sym)
                close_price = float(tick.bid if o_type == "BUY" else tick.ask) if tick else float(o_price)
                mult = 100.0 if "XAU" in sym or "GOLD" in sym else 100000.0
                gross_profit = (close_price - o_price) * mult * lot if o_type == "BUY" else (o_price - close_price) * mult * lot
                profit = round(gross_profit - (float(lot) * comm_per_lot), 2)
                realized_delta += profit

                cursor.execute(
                    """
                    UPDATE orders
                    SET close_time = ?, close_price = ?, profit = ?, close_reason = 'TARGET_GOAL_REACHED', status = 'CLOSED'
                    WHERE ticket_id = ?;
                    """,
                    (close_time, close_price, profit, ticket_id),
                )
                closed_count += 1

            if open_orders:
                cursor.execute(
                    "INSERT INTO bot_logs (log_level, module, message) VALUES ('INFO', 'target_breaker', ?);",
                    (f"Cầu dao chốt lời tổng: Đã tự động đóng sạch {len(open_orders)} vị thế đang mở để bảo toàn mục tiêu lợi nhuận.",),
                )
            conn.commit()

            if realized_delta != 0.0:
                acc = mt5.account_info()
                if acc is not None:
                    new_bal = round(float(acc.balance) + realized_delta, 2)
                    config.MT5_BALANCE = new_bal
                    set_setting("account_balance", str(new_bal))
                    if hasattr(mt5, "set_balance"):
                        mt5.set_balance(new_bal)
    except Exception as e:
        logging.error(f"Lỗi khi đồng bộ đóng vị thế trong DB: {e}")

    return closed_count
