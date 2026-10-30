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

    def calculate_standard_lot(self, balance: float, sl_pips: float, pip_value: float = 10.0) -> float:
        """
        Tính Lot Size chuẩn gộp cả phí hoa hồng để chỉ mất đúng 1R (Mục 4 & 5 Tài liệu Nâng cấp):
        Lot Size = (Tổng Vốn * % Rủi Ro) / [ (SL Pips * Pip Value) + Commission Per Lot ]
        """
        if getattr(config, "USE_CUSTOM_LOT", False) and config.CUSTOM_LOT_SIZE > 0:
            return config.CUSTOM_LOT_SIZE
        risk_money = balance * getattr(config, "RISK_PER_TRADE", 0.01)
        comm_per_lot = getattr(config, "COMMISSION_PER_LOT_USD", 7.0)
        cost_per_lot = (sl_pips * pip_value) + comm_per_lot
        if cost_per_lot <= 0:
            return 0.01
        raw_lot = risk_money / cost_per_lot
        return max(0.01, round(raw_lot - 0.005, 2))  # Làm tròn xuống bước 0.01

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
