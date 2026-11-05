"""
Module risk_manager.py
Hiện thực hóa CHƯƠNG 3.1 (Thuật toán tự động tính R:R & Khối lượng Lot Size cố định 1R),
CHƯƠNG 4.4 (Cầu dao ngắt mạch tự động Daily Circuit Breaker LOCK_BOT_24H),
và CHƯƠNG 5 (Bảng tham số Hyperparameters chuẩn).
"""

import importlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any
import numpy as np

# Import MetaTrader5 an toàn (native trên Windows, hoặc fallback giả lập trên macOS/Linux)
try:
    mt5 = importlib.import_module("MetaTrader5")
except (ImportError, ModuleNotFoundError):
    from mt5_connector import mt5

from ai_math_models import MonteCarloRiskEstimator
import config as config_module
from config import config, BASE_DIR
from mt5_connector import get_pip_value_per_lot, get_contract_multiplier

# Cấu hình ghi log ra cả console và tệp trading.log (Chương 4.3)
_log_formatter = logging.Formatter("%(asctime)s - [%(levelname)s] - %(message)s")
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "").endswith("trading.log") for h in _root_logger.handlers):
    _file_handler = logging.FileHandler(BASE_DIR / "trading.log", encoding="utf-8")
    _file_handler.setFormatter(_log_formatter)
    _root_logger.addHandler(_file_handler)


class RiskManager:
    """
    Bộ quản trị rủi ro chuyên sâu chuẩn định lượng:
    - R:R tối thiểu 1:1.5 (khuyên dùng 1:2.0). Nếu R:R < 1.5 -> REJECT bỏ lệnh.
    - Rủi ro cố định 1R trên mỗi lệnh (1.0% vốn hoặc 0.5%).
    - Cầu dao cắt lỗ tự động 24h (LOCK_BOT_24H): Kích hoạt khi dính chuỗi 2 lệnh thua liên tiếp hoặc lỗ >= 2R.
    - Cầu dao bảo vệ khung giờ Rollover (4h-5h sáng VN) và bão tin tức.
    """

    def __init__(
        self,
        risk_per_trade: float = 0.01,       # 1R = 1.0% Vốn (Tham số chuẩn Chương 5)
        min_rr_ratio: float = 1.5,          # Tối thiểu 1:1.5, khuyên dùng 1:2.0
        max_daily_loss_r: float = 2.0,      # Max 2R (2% vốn) -> Cầu dao 24h
        max_consecutive_losses: int = 2,    # 2 lệnh thua liên tiếp -> Kích hoạt ngắt mạch
        target_balance: float = 1000000.0,  # Mục tiêu chốt lời toàn phần (1 triệu USD hoặc VNĐ)
        buffer_pips: float = 1.0,           # Buffer khoảng an toàn Stop Loss (pips)
    ):
        self.risk_per_trade = risk_per_trade
        self.min_rr_ratio = min_rr_ratio
        self.max_daily_loss_r = max_daily_loss_r
        self.max_consecutive_losses = max_consecutive_losses
        self.target_balance = target_balance
        self.buffer_pips = buffer_pips

        # Theo dõi trạng thái vốn và cầu dao
        self.daily_start_balance: Optional[float] = None
        self.consecutive_losses: int = 0
        self.circuit_breaker_locked_until: Optional[datetime] = None
        self.lock_reason: str = ""

    def get_execution_lot(self) -> float:
        """
        Ưu tiên sử dụng Số Lot cố định do người dùng chỉ định (Custom Lot Size) từ Web UI (v2).
        """
        custom_lot = getattr(config, "CUSTOM_LOT_SIZE", 0) or getattr(config_module, "CUSTOM_LOT_SIZE", 0)
        if custom_lot and float(custom_lot) > 0:
            return round(float(custom_lot), 2)
        return 0.01  # Mặc định an toàn

    def calculate_standard_lot(
        self,
        balance: float,
        sl_pips: float,
        pip_value: float = 10.0,
        symbol: Optional[str] = None,
        entry_price: float = 0.0,
        include_slippage: bool = False,
    ) -> float:
        """
        Tính Lot Size chuẩn gộp cả phí hoa hồng để chỉ mất đúng 1R (Mục 4 & 5 Tài liệu Nâng cấp):
        Lot Size = (Tổng Vốn * % Rủi Ro) / [ ((SL Pips + Slippage Buffer) * Pip Value) + Commission Per Lot ]
        - Tự động quy đổi `pip_value` động theo `symbol` (EURUSD, XAUUSD, BTCUSD, USDJPY...) nếu truyền `symbol`.
        """
        if getattr(config, "USE_CUSTOM_LOT", False) and config.CUSTOM_LOT_SIZE > 0:
            return config.CUSTOM_LOT_SIZE
        if symbol:
            pip_value = get_pip_value_per_lot(symbol, entry_price)
        effective_sl_pips = float(sl_pips) + (float(getattr(config, "SLIPPAGE_BUFFER_PIPS", 0.3)) if include_slippage else 0.0)
        risk_money = balance * getattr(config, "RISK_PER_TRADE", 0.01)
        comm_per_lot = getattr(config, "COMMISSION_PER_LOT_USD", 7.0)
        cost_per_lot = (effective_sl_pips * pip_value) + comm_per_lot
        if cost_per_lot <= 0:
            return 0.01
        raw_lot = risk_money / cost_per_lot
        return max(0.01, round(raw_lot - 0.005, 2))  # Làm tròn xuống bước 0.01

    def check_free_margin_and_cap_lot(
        self,
        symbol: str,
        order_type: str,
        lot_size: float,
        entry_price: float,
    ) -> Tuple[bool, float, str]:
        """
        Kiểm tra Tiền ký quỹ khả dụng (Free Margin & Margin Level %) trước khi mở lệnh trên Ví thực:
        - Chống lỗi `TRADE_RETCODE_NO_MONEY` khi đòn bẩy thấp hoặc SL ngắn khiến Lot phình to.
        - Giữ lại tối thiểu `MIN_FREE_MARGIN_RATIO` (15%) Free Margin dự phòng chống Stop-Out.
        """
        acc = mt5.account_info() if mt5 else None
        if acc is None:
            return True, lot_size, "Không lấy được account_info, giữ nguyên lot."

        equity = float(getattr(acc, "equity", getattr(acc, "balance", 10000.0)))
        margin_free = float(getattr(acc, "margin_free", equity))
        min_keep_ratio = float(getattr(config, "MIN_FREE_MARGIN_RATIO", 0.15))
        usable_free_margin = max(0.0, margin_free - (equity * min_keep_ratio))

        action = getattr(mt5, "ORDER_TYPE_BUY", 0) if order_type.upper() == "BUY" else getattr(mt5, "ORDER_TYPE_SELL", 1)
        req_margin_1lot = None
        if hasattr(mt5, "order_calc_margin"):
            try:
                req_margin_1lot = mt5.order_calc_margin(action, symbol, 1.0, entry_price)
            except Exception:
                req_margin_1lot = None

        if not req_margin_1lot or req_margin_1lot <= 0:
            leverage = float(getattr(acc, "leverage", 100) or 100)
            mult = get_contract_multiplier(symbol)
            notional_1lot = mult if symbol.upper().startswith("USD") else (mult * max(entry_price, 0.0001))
            req_margin_1lot = notional_1lot / max(leverage, 1.0)

        required_margin = lot_size * req_margin_1lot
        if required_margin <= usable_free_margin:
            return True, lot_size, f"Đủ Free Margin (${usable_free_margin:,.2f} >= ${required_margin:,.2f})."

        # Nếu vượt quá Free Margin khả dụng -> hạ Lot xuống mức tối đa tài khoản chịu được
        max_affordable_lot = round((usable_free_margin / req_margin_1lot) - 0.005, 2)
        if max_affordable_lot < 0.01:
            return (
                False,
                0.0,
                f"Không đủ Free Margin khả dụng (${margin_free:,.2f} USD) để mở tối thiểu 0.01 lot {symbol} (cần ${req_margin_1lot * 0.01:,.2f} USD).",
            )
        logging.warning(
            f"⚠️ [FREE MARGIN CAP] Hạ Lot {symbol} từ {lot_size} xuống {max_affordable_lot} lot để bảo toàn Free Margin (${usable_free_margin:,.2f})."
        )
        return True, max_affordable_lot, f"Đã giới hạn Lot xuống {max_affordable_lot} theo Free Margin."

    def calculate_tp_with_buffer(self, entry: float, sl: float, order_type: str, point: float = 0.0001) -> float:
        """
        Tính mức Take Profit (2R) có bù thêm Buffer Pips để bù phí sàn (Mục 3 & 5 Tài liệu Nâng cấp):
        - Buffer Pips = Phí Round-Turn trên 1 Lot (USD) / Giá trị 1 Pip của 1 Lot (USD) (VD: 7 / 10 = 0.7 Pips)
        - TP Distance = (Stop Loss Distance * 2) + Buffer Pips
        """
        sl_distance = abs(entry - sl)
        pip_size = point * 10 if point in (0.00001, 0.001) else point
        buffer_dist = getattr(config, "COMMISSION_BUFFER_PIPS", 0.7) * pip_size
        tp_distance = (sl_distance * 2.0) + buffer_dist
        return round(entry + tp_distance if order_type.upper() == "BUY" else entry - tp_distance, 5)

    def check_target_goal(self, current_equity: Optional[float] = None) -> bool:
        """
        Kiểm tra điều kiện ngắt Bot đạt mục tiêu (Mục 6 Tài liệu Nâng cấp):
        Luôn đọc giá trị Equity (thay vì Balance) từ MT5 vì Equity đã tự động trừ sạch
        toàn bộ phí Commission và Spread thả nổi theo thời gian thực.
        """
        if current_equity is None:
            acc = mt5.account_info()
            current_equity = float(getattr(acc, "equity", getattr(config, "INITIAL_CAPITAL", 0.0)))
        return self.is_target_goal_reached(current_equity)

    def is_target_goal_reached(self, current_equity: float) -> bool:
        """
        Cầu dao chốt lời tổng (Target Profit Circuit Breaker - v2):
        Kiểm tra tổng tài sản thực tế (Equity USD) đã đạt mốc mục tiêu TARGET_PROFIT_GOAL (USD) chưa.
        """
        target = getattr(config, "TARGET_PROFIT_GOAL", 0) or getattr(config_module, "TARGET_PROFIT_GOAL", 0)
        if target and float(target) > 0 and current_equity >= float(target):
            msg = f"🎯 [TARGET REACHED] Equity ${current_equity:,.2f} USD >= Mục tiêu ${float(target):,.2f} USD"
            print(msg)
            logging.info(msg)
            return True
        return False

    def is_capital_stop_out_reached(
        self,
        bot_equity: float,
        initial_capital: Optional[float] = None,
    ) -> Tuple[bool, float, str]:
        """
        Cầu dao Chống Cháy Vốn Đánh (Hard Capital Stop-Out Protection):
        - Bảo vệ phần `Vốn đánh (Initial Capital)` mà người dùng cấp cho Bot (VD: $100 USD trên tổng ví $100,000 USD).
        - Khi `bot_equity` sụt giảm chạm ngưỡng sàn an toàn (20% Vốn đánh ban đầu, tức lỗ tối đa 80% vốn cấp cho Bot),
          hệ thống lập tức đóng toàn bộ lệnh và ngắt Bot để bảo toàn vốn còn lại và tuyệt đối không ăn lẹm vào số dư ví Exness gốc.
        """
        init_cap = float(
            initial_capital
            if initial_capital is not None
            else (getattr(config, "INITIAL_CAPITAL", 0.0) or getattr(config_module, "INITIAL_CAPITAL", 0.0))
        )
        if init_cap <= 0:
            return False, 0.0, ""

        stop_out_floor = round(init_cap * 0.20, 2)
        if bot_equity <= stop_out_floor:
            msg = (
                f"🛡️ [CAPITAL STOP-OUT] Vốn đánh thực tế (${bot_equity:,.2f} USD) đã chạm ngưỡng bảo vệ tối thiểu "
                f"${stop_out_floor:,.2f} USD (20% của Vốn đánh ${init_cap:,.2f} USD). "
                f"Tự động đóng toàn bộ vị thế và dừng Bot để chống cháy ví!"
            )
            logging.critical(msg)
            return True, stop_out_floor, msg
        return False, stop_out_floor, ""

    def evaluate_trailing_and_breakeven(
        self,
        order_type: str,
        open_price: float,
        current_eval_price: float,
        current_sl: float,
        tp_price: float,
        pip_size: float,
        digits: int = 5,
    ) -> Tuple[bool, float, str]:
        """
        Cơ chế 1: Dời SL về Hòa Vốn (Break-Even) & Khóa Lãi Tự Động (Trailing Stop):
        - Khi giá chạy thuận chiều đạt >= 50% quãng đường tới TP:
          Dời SL về `open_price +/- 1.0 pip` (bù phí Commission + Spread) -> Lệnh bất tử (Risk-Free).
        - Khi giá chạy thuận chiều đạt >= 75% quãng đường tới TP:
          Kích hoạt Trailing Stop khóa cứng 55% lợi nhuận đang nổi theo đà tăng của giá.
        """
        if not tp_price or tp_price <= 0 or open_price <= 0 or pip_size <= 0:
            return False, current_sl, ""

        o_type = order_type.upper()
        if o_type == "BUY":
            tp_dist = tp_price - open_price
            if tp_dist <= 0:
                return False, current_sl, ""
            fav_dist = current_eval_price - open_price
            progress = fav_dist / tp_dist

            # Mốc 2: Đạt >= 75% quãng đường tới TP -> Khóa cứng 55% quãng đường lãi hiện tại
            if progress >= 0.75:
                trail_sl = round(open_price + (fav_dist * 0.55), digits)
                if current_sl <= 0 or (trail_sl - current_sl) >= (0.5 * pip_size):
                    return True, trail_sl, f"TRAILING_STOP (Đạt {progress * 100:.0f}% TP -> Khóa 55% lãi tại {trail_sl})"

            # Mốc 1: Đạt >= 50% quãng đường tới TP -> Dời SL về Hòa vốn + 1.0 pip bù phí sàn
            if progress >= 0.50:
                be_sl = round(open_price + (1.0 * pip_size), digits)
                if current_sl <= 0 or (be_sl - current_sl) >= (0.2 * pip_size):
                    return True, be_sl, f"BREAKEVEN_LOCK (Đạt {progress * 100:.0f}% TP -> Dời SL về Hòa vốn +1 pip tại {be_sl})"

        elif o_type == "SELL":
            tp_dist = open_price - tp_price
            if tp_dist <= 0:
                return False, current_sl, ""
            fav_dist = open_price - current_eval_price
            progress = fav_dist / tp_dist

            # Mốc 2: Đạt >= 75% quãng đường tới TP -> Khóa cứng 55% quãng đường lãi hiện tại
            if progress >= 0.75:
                trail_sl = round(open_price - (fav_dist * 0.55), digits)
                if current_sl <= 0 or (current_sl - trail_sl) >= (0.5 * pip_size):
                    return True, trail_sl, f"TRAILING_STOP (Đạt {progress * 100:.0f}% TP -> Khóa 55% lãi tại {trail_sl})"

            # Mốc 1: Đạt >= 50% quãng đường tới TP -> Dời SL về Hòa vốn - 1.0 pip bù phí sàn
            if progress >= 0.50:
                be_sl = round(open_price - (1.0 * pip_size), digits)
                if current_sl <= 0 or (current_sl - be_sl) >= (0.2 * pip_size):
                    return True, be_sl, f"BREAKEVEN_LOCK (Đạt {progress * 100:.0f}% TP -> Dời SL về Hòa vốn +1 pip tại {be_sl})"

        return False, current_sl, ""

    def should_early_exit_position(
        self,
        order_type: str,
        profit: float,
        one_r_money: float,
        recommended_action: str,
        confidence: float,
        market_case: str,
        hmm_safe: bool,
    ) -> Tuple[bool, str]:
        """
        Cơ chế 2: Đóng Lệnh Sớm Khi AI Phát Hiện Đảo Chiều Hoặc Nhiễu Loạn (AI Early Exit):
        - Nếu đang giữ lệnh BUY mà AI phát hiện tín hiệu đảo chiều SELL mạnh (Confidence >= 75%) hoặc ngược lại -> Chốt sớm.
        - Nếu thị trường rơi vào cấu trúc Loa Kèn Hỗn Loạn (CASE_C_BROADENING_CHAOS) / Bão tin tức (CASE_F_ROLLOVER_NEWS)
          hoặc HMM báo HIGH_VOLATILITY_CHAOS (`hmm_safe == False`) khi lệnh đang có lãi nhẹ hoặc đang âm >= 0.6R -> Thoát lệnh sớm bảo toàn vốn.
        """
        o_type = order_type.upper()
        rec_act = (recommended_action or "").upper()
        conf_ratio = confidence / 100.0 if confidence > 1.0 else confidence

        # 1. Đảo chiều xu hướng mạnh từ AI
        if o_type == "BUY" and rec_act == "SELL" and conf_ratio >= 0.75:
            return True, f"AI_REVERSAL_EXIT (AI báo đảo chiều SELL mạnh {conf_ratio * 100:.1f}%)"
        if o_type == "SELL" and rec_act == "BUY" and conf_ratio >= 0.75:
            return True, f"AI_REVERSAL_EXIT (AI báo đảo chiều BUY mạnh {conf_ratio * 100:.1f}%)"

        # 2. Thị trường chuyển sang Hỗn loạn / Bão tin tức / HMM bất ổn
        is_chaos = market_case in ("CASE_C_BROADENING_CHAOS", "CASE_F_ROLLOVER_NEWS") or (not hmm_safe)
        if is_chaos and (profit > 0 or profit <= -0.60 * max(one_r_money, 1.0)):
            return True, f"AI_CHAOS_EARLY_EXIT (Thị trường rơi vào {market_case}, đóng lệnh sớm bảo vệ vốn)"

        return False, ""

    def update_daily_balance(self, current_balance: float) -> None:
        """Cập nhật số dư đầu ngày."""
        if self.daily_start_balance is None:
            self.daily_start_balance = current_balance

    def reset_daily_state(self, current_balance: float) -> None:
        """Reset vào phiên ngày mới nếu không bị khóa 24h."""
        self.daily_start_balance = current_balance
        if not self.is_locked_24h():
            self.consecutive_losses = 0

    def trigger_circuit_breaker_lock_24h(self, reason: str) -> None:
        """
        Hiện thực hóa CHƯƠNG 4.4:
        If Total_Daily_Loss >= 2 * 1R (Lỗ 2 lệnh liên tiếp trong ngày):
        ==> KÍCH HOẠT LOCK_BOT_24H()
        ==> Cưỡng chế đóng toàn bộ luồng phát lệnh trong 24 giờ tiếp theo.
        """
        now = datetime.now(timezone.utc)
        self.circuit_breaker_locked_until = now + timedelta(hours=24)
        self.lock_reason = reason
        logging.critical(
            f"🚨 [CIRCUIT BREAKER] KÍCH HOẠT LOCK_BOT_24H! Lý do: {reason}. "
            f"Khóa phát lệnh đến {self.circuit_breaker_locked_until.strftime('%Y-%m-%d %H:%M:%S UTC')}."
        )

    def is_locked_24h(self) -> Tuple[bool, str]:
        """Kiểm tra bot có đang bị khóa bởi cầu dao 24h không."""
        if self.circuit_breaker_locked_until is None:
            return False, ""

        now = datetime.now(timezone.utc)
        if now < self.circuit_breaker_locked_until:
            remain = self.circuit_breaker_locked_until - now
            hours_left = remain.total_seconds() / 3600.0
            return True, f"CẦU DAO 24H ĐANG KÍCH HOẠT ({self.lock_reason}). Còn {hours_left:.1f} giờ."
        else:
            # Hết thời gian phạt 24h
            self.circuit_breaker_locked_until = None
            self.lock_reason = ""
            self.consecutive_losses = 0
            return False, ""

    def record_trade_result(self, profit: float, one_r_money: float) -> None:
        """Ghi nhận kết quả lệnh để đếm chuỗi thua và kích hoạt cầu dao nếu cần."""
        if profit < 0:
            self.consecutive_losses += 1
            logging.warning(f"Lệnh thua ghi nhận ({profit:.2f}). Chuỗi thua hiện tại: {self.consecutive_losses}")
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.trigger_circuit_breaker_lock_24h(
                    f"Dính {self.consecutive_losses} lệnh thua liên tiếp trong ngày (Quy tắc 2R)"
                )
        else:
            self.consecutive_losses = 0
            logging.info(f"Lệnh thắng (+{profit:.2f}). Reset chuỗi thua về 0.")

    def check_rr_ratio(
        self,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        spread: float = 0.00015,
        point: float = 0.00001,
    ) -> Tuple[bool, float, float, float, str]:
        """
        Hiện thực hóa CHƯƠNG 3.1: Thuật Toán Tính R:R
        1) Khoảng cách Rủi ro (Risk Distance): D_risk = |Entry - Stop_Loss| + Spread + Buffer_Pip
        2) Khoảng cách Lợi nhuận (Reward Distance): D_reward = |Take_Profit - Entry|
        3) Tỷ lệ R:R = D_reward / D_risk
        ==> KIỂM TRA: If R:R < 1.5 ==> REJECT / BỎ LỆNH (Không thỏa mãn lợi thế xác suất).
        """
        buffer_val = self.buffer_pips * point * 10.0
        d_risk = abs(entry_price - sl_price) + spread + buffer_val
        d_reward = abs(tp_price - entry_price)

        if d_risk <= 0:
            return False, 0.0, d_risk, d_reward, "Khoảng cách rủi ro D_risk không hợp lệ (<= 0)"

        rr_ratio = d_reward / d_risk

        if rr_ratio < self.min_rr_ratio:
            return (
                False,
                rr_ratio,
                d_risk,
                d_reward,
                f"REJECT / BỎ LỆNH: Tỷ lệ R:R = 1:{rr_ratio:.2f} < 1:{self.min_rr_ratio:.2f} (Không thỏa mãn lợi thế xác suất).",
            )

        return (
            True,
            rr_ratio,
            d_risk,
            d_reward,
            f"Thỏa mãn R:R chuẩn (1:{rr_ratio:.2f} >= 1:{self.min_rr_ratio:.2f}).",
        )

    def is_safe_to_trade(self) -> Tuple[bool, str]:
        """Kiểm tra toàn diện tất cả các lớp phòng thủ trước khi vào lệnh."""
        # 1. Kiểm tra Cầu dao 24H
        locked, lock_msg = self.is_locked_24h()
        if locked:
            return False, lock_msg

        # 2. Thông tin tài khoản
        account = mt5.account_info()
        if account is None:
            return False, "Không lấy được thông tin tài khoản MT5."

        self.update_daily_balance(account.balance)

        # 3. Đạt mục tiêu chốt lời toàn phần
        if account.balance >= self.target_balance:
            return False, f"ĐÃ ĐẠT MỤC TIÊU: {account.balance:,.2f} >= {self.target_balance:,.2f}. Dừng bot an toàn!"

        # 4. Kiểm tra Max Daily Drawdown 2R (hoặc 2% vốn theo Chương 5)
        one_r = self.daily_start_balance * self.risk_per_trade
        max_daily_loss = self.max_daily_loss_r * one_r
        current_daily_loss = self.daily_start_balance - account.equity

        if current_daily_loss >= max_daily_loss:
            self.trigger_circuit_breaker_lock_24h(
                f"Chạm ngưỡng sụt giảm ngày 2R (Lỗ {current_daily_loss:,.2f} >= {max_daily_loss:,.2f})"
            )
            return False, f"Chạm ngưỡng cắt lỗ 2R ngày ({current_daily_loss:,.2f} >= {max_daily_loss:,.2f}). Ngắt mạch 24h!"

        # 5. Kiểm tra Margin Level (ngăn Stop Out)
        if account.margin_level is not None and 0 < account.margin_level < 250:
            return False, f"Mức ký quỹ quá thấp ({account.margin_level:.1f}% < 250%). Tránh rủi ro Stop-Out."

        return True, "Hệ thống bảo vệ đa tầng an toàn. Đủ điều kiện giao dịch."

    def calculate_lot_size_1r(
        self,
        symbol: str,
        entry_price: float,
        sl_price: float,
        spread: float = 0.00015,
    ) -> Tuple[float, float, float]:
        """
        Hiện thực hóa CHƯƠNG 3.1: Công Thức Tính Khối Lượng Lot Size (Chỉ lỗ đúng 1R)
        1R_Money = Capital * Risk_Percent (1.0% Vốn)
        D_risk = |Entry - Stop_Loss| + Spread + Buffer_Pip
        Lot_Size = 1R_Money / (D_risk * Pip_Value)
        Trả về: (lot_size, 1r_money, d_risk)
        """
        symbol_info = mt5.symbol_info(symbol)
        account = mt5.account_info()

        if symbol_info is None or account is None:
            logging.error(f"Không thể lấy symbol info {symbol} hoặc account info.")
            return 0.0, 0.0, 0.0

        point = symbol_info.point
        tick_size = symbol_info.trade_tick_size if symbol_info.trade_tick_size > 0 else point
        tick_value = symbol_info.trade_tick_value if symbol_info.trade_tick_value > 0 else 1.0

        # 1. 1R Money: Đúng 1.0% vốn
        one_r_money = account.equity * self.risk_per_trade

        # 2. D_risk có tính spread + buffer
        buffer_val = self.buffer_pips * point * 10.0
        d_risk = abs(entry_price - sl_price) + spread + buffer_val

        if d_risk <= 0:
            return 0.0, one_r_money, 0.0

        # Số ticks chịu rủi ro và giá trị tổn thất trên 1 standard lot (gộp cả phí hoa hồng Round-Turn 7 USD/lot - Mục 4 PDF)
        risk_ticks = d_risk / tick_size
        comm_per_lot = float(getattr(config, "COMMISSION_PER_LOT_USD", 7.0))
        risk_per_standard_lot = (risk_ticks * tick_value) + comm_per_lot

        if risk_per_standard_lot <= 0:
            return 0.0, one_r_money, d_risk

        # Khối lượng raw lot làm tròn xuống bước 0.01
        raw_lot = one_r_money / risk_per_standard_lot
        calculated_lot = max(0.01, round(raw_lot - 0.005, 2))

        min_lot = symbol_info.volume_min
        max_lot = symbol_info.volume_max

        if calculated_lot < min_lot:
            calculated_lot = min_lot

        if calculated_lot > max_lot:
            calculated_lot = max_lot

        calculated_lot = round(calculated_lot, 2)

        logging.info(
            f"[{symbol}] Equity: ${account.equity:,.2f} | 1R = ${one_r_money:,.2f} (1.0%) | "
            f"D_risk: {d_risk:.5f} | Lot chuẩn 1R: {calculated_lot}"
        )

        return calculated_lot, one_r_money, d_risk

    def evaluate_portfolio_var(self, returns_history: list[float], portfolio_value: float) -> Dict[str, float]:
        """
        Tính toán Monte Carlo Value at Risk (VaR 95% và 99%) để giám sát mức rủi ro tối đa của danh mục.
        """
        if not returns_history or len(returns_history) < 20:
            return {"var_95": portfolio_value * 0.02, "var_99": portfolio_value * 0.03}

        mean_ret = float(np.mean(returns_history))
        std_ret = float(np.std(returns_history))

        var_95 = MonteCarloRiskEstimator.calculate_parametric_var(
            portfolio_value=portfolio_value,
            daily_return_mean=mean_ret,
            daily_return_std=std_ret,
            confidence_level=0.95,
        )

        var_99 = MonteCarloRiskEstimator.calculate_parametric_var(
            portfolio_value=portfolio_value,
            daily_return_mean=mean_ret,
            daily_return_std=std_ret,
            confidence_level=0.99,
        )

        return {"var_95": round(var_95, 2), "var_99": round(var_99, 2)}
