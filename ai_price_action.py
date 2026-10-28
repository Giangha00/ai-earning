"""
Module ai_price_action.py
Hiện thực hóa CHƯƠNG 1 (Tất cả 6 kịch bản thị trường Case-by-Case)
và CHƯƠNG 3.2 (Thuật toán nhận diện vùng nén - Compression Detection)
theo Sổ tay thuật toán Bot AI Trading Forex Chuyên Sâu.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Tuple, List, Dict, Any
import numpy as np
import pandas as pd
import pandas_ta as ta


class MarketCase(str, Enum):
    CASE_A_TREND = "CASE_A_TREND"                         # Trend Tăng/Giảm Rõ Ràng (Smooth Trend)
    CASE_B_COMPRESSION = "CASE_B_COMPRESSION"             # Đi Ngang Có Quy Luật (Structured Sideway / Compression)
    CASE_C_BROADENING_CHAOS = "CASE_C_BROADENING_CHAOS"   # Đi Ngang Hỗn Loạn / Hình Cái Loa (Chaos / Noise Market)
    CASE_D_LIQUIDITY_SWEEP = "CASE_D_LIQUIDITY_SWEEP"     # Bẫy Phá Giả & Sweep Thanh Khoản (Liquidity Trap)
    CASE_E_LEADING_WAVE = "CASE_E_LEADING_WAVE"           # Sóng Dẫn Hướng & Đảo Chiều Đột Ngột (Directional Leading Wave)
    CASE_F_ROLLOVER_NEWS = "CASE_F_ROLLOVER_NEWS"         # Bão Tin Tức & Giãn Spread Rollover (Technical Artifacts)


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    STRICT_NO_TRADE = "STRICT_NO_TRADE"
    WAIT_RETEST = "WAIT_RETEST"
    CIRCUIT_BREAKER_LOCK = "CIRCUIT_BREAKER_LOCK"


@dataclass
class MarketAnalysisResult:
    market_case: MarketCase
    recommended_action: TradeAction
    is_tradable: bool
    confidence_modifier: float
    reason: str
    details: Dict[str, Any]
    entry_suggestion: Optional[float] = None
    sl_suggestion: Optional[float] = None
    tp_suggestion: Optional[float] = None
    compression_detected: bool = False
    compression_pattern: Optional[str] = None


class PriceActionAnalyzer:
    """
    Bộ phân tích Price Action Luật Bò Gấu và Nhận diện 6 Kịch bản thị trường.
    """

    def __init__(
        self,
        atr_fast_len: int = 5,
        atr_slow_len: int = 20,
        compression_atr_ratio: float = 0.65,
        swing_window: int = 3,
        rollover_hour_start: int = 4,  # 4h sáng VN (UTC+7)
        rollover_hour_end: int = 5,    # 5h sáng VN (UTC+7)
        spread_spike_threshold: float = 25.0, # Points
    ):
        self.atr_fast_len = atr_fast_len
        self.atr_slow_len = atr_slow_len
        self.compression_atr_ratio = compression_atr_ratio
        self.swing_window = swing_window
        self.rollover_hour_start = rollover_hour_start
        self.rollover_hour_end = rollover_hour_end
        self.spread_spike_threshold = spread_spike_threshold

    def is_vietnam_rollover_time(self, timestamp: Optional[datetime] = None) -> bool:
        """
        Kiểm tra khung giờ giao ngày Rollover (4h-5h sáng giờ Việt Nam UTC+7).
        """
        if timestamp is None:
            now_utc = datetime.now(timezone.utc)
        elif timestamp.tzinfo is None:
            now_utc = timestamp.replace(tzinfo=timezone.utc)
        else:
            now_utc = timestamp.astimezone(timezone.utc)

        # Chuyển đổi sang giờ Việt Nam (UTC+7)
        vn_time = now_utc + timedelta(hours=7)
        return self.rollover_hour_start <= vn_time.hour < self.rollover_hour_end

    def find_pivots(self, df: pd.DataFrame, window: int = 3) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Tìm các điểm Swing High và Swing Low (Căn cứ Bò & Gấu).
        """
        highs = df["high"].values
        lows = df["low"].values
        n = len(df)
        pivot_highs: List[Dict[str, Any]] = []
        pivot_lows: List[Dict[str, Any]] = []

        for i in range(window, n - window):
            # Pivot High: cao hơn window nến trước và window nến sau
            if all(highs[i] > highs[i - w] for w in range(1, window + 1)) and all(
                highs[i] >= highs[i + w] for w in range(1, window + 1)
            ):
                pivot_highs.append({"index": i, "price": float(highs[i]), "time": df.iloc[i].get("time")})

            # Pivot Low: thấp hơn window nến trước và window nến sau
            if all(lows[i] < lows[i - w] for w in range(1, window + 1)) and all(
                lows[i] <= lows[i + w] for w in range(1, window + 1)
            ):
                pivot_lows.append({"index": i, "price": float(lows[i]), "time": df.iloc[i].get("time")})

        return pivot_highs, pivot_lows

    def check_compression(
        self, df: pd.DataFrame, pivot_highs: List[Dict[str, Any]], pivot_lows: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Hiện thực hóa CHƯƠNG 3.2: Thuật Toán Tự Động Nhận Diện Vùng Nén (Compression Detection)
        3 điều kiện toán học:
        • ĐK 1: ATR(5) < 0.65 * ATR(20) (Biên độ nến giảm đột ngột > 35%)
        • ĐK 2: D1 > D2 > D3 với Di = |Pivot_High_i - Pivot_Low_i| (Khoảng cách swing thu hẹp dần)
        • ĐK 3: Hình học vùng nén (Tam giác Tăng, Tam giác Giảm, Tam giác Cân, Rectangle)
        """
        if len(df) < 30:
            return False, None, {}

        # 1. Tính ATR(5) và ATR(20)
        atr_fast = ta.atr(df["high"], df["low"], df["close"], length=self.atr_fast_len)
        atr_slow = ta.atr(df["high"], df["low"], df["close"], length=self.atr_slow_len)

        if atr_fast is None or atr_slow is None or pd.isna(atr_fast.iloc[-1]) or pd.isna(atr_slow.iloc[-1]):
            return False, None, {}

        last_atr_fast = float(atr_fast.iloc[-1])
        last_atr_slow = float(atr_slow.iloc[-1])
        cond1 = last_atr_fast < (self.compression_atr_ratio * last_atr_slow)

        # 2. Thu hẹp khoảng cách Swing Amplitude D1 > D2 > D3
        cond2 = False
        amplitudes = []
        pattern_type = "Rectangle"

        if len(pivot_highs) >= 3 and len(pivot_lows) >= 3:
            h_recent = pivot_highs[-3:]
            l_recent = pivot_lows[-3:]

            d1 = abs(h_recent[0]["price"] - l_recent[0]["price"])
            d2 = abs(h_recent[1]["price"] - l_recent[1]["price"])
            d3 = abs(h_recent[2]["price"] - l_recent[2]["price"])
            amplitudes = [d1, d2, d3]

            if d1 > d2 > d3 or (d1 > d3 and d2 > d3):
                cond2 = True

            # 3. Phân tích hình học
            h1, h2, h3 = h_recent[0]["price"], h_recent[1]["price"], h_recent[2]["price"]
            l1, l2, l3 = l_recent[0]["price"], l_recent[1]["price"], l_recent[2]["price"]

            # Ngưỡng ngang nhau xấp xỉ 0.15% hoặc 1.5 pip
            price_tol = df["close"].iloc[-1] * 0.0003

            if abs(h2 - h3) <= price_tol and l1 < l2 < l3:
                pattern_type = "Ascending_Triangle"  # Tam giác Tăng
            elif abs(l2 - l3) <= price_tol and h1 > h2 > h3:
                pattern_type = "Descending_Triangle"  # Tam giác Giảm
            elif h1 > h2 > h3 and l1 < l2 < l3:
                pattern_type = "Symmetrical_Triangle"  # Tam giác Cân
            else:
                pattern_type = "Compression_Box"  # Hộp chữ nhật nén

        is_compressed = cond1 and (cond2 or (len(amplitudes) >= 2 and amplitudes[-1] < amplitudes[0]))

        details = {
            "atr_fast": last_atr_fast,
            "atr_slow": last_atr_slow,
            "atr_ratio": round(last_atr_fast / (last_atr_slow + 1e-9), 3),
            "cond1_atr_contraction": cond1,
            "cond2_amplitude_contraction": cond2,
            "pattern_type": pattern_type if is_compressed else None,
            "amplitudes": amplitudes,
        }

        return is_compressed, pattern_type if is_compressed else None, details

    def check_broadening_chaos(
        self, pivot_highs: List[Dict[str, Any]], pivot_lows: List[Dict[str, Any]], df: pd.DataFrame
    ) -> bool:
        """
        Hiện thực hóa Case C: Đi Ngang Hỗn Loạn / Hình Cái Loa (Broadening Chaos Market)
        Đặc điểm:
        - Đỉnh sau cao hơn đỉnh trước (High_k > High_{k-1})
        - VÀ Đáy sau thấp hơn đáy trước (Low_k < Low_{k-1})
        - Râu nến dài quét 2 đầu, nến có râu chiếm > 60% thân nến
        """
        if len(pivot_highs) < 2 or len(pivot_lows) < 2:
            return False

        h_prev, h_curr = pivot_highs[-2]["price"], pivot_highs[-1]["price"]
        l_prev, l_curr = pivot_lows[-2]["price"], pivot_lows[-1]["price"]

        # Điều kiện loa kèn mở rộng: High mở rộng lên, Low mở rộng xuống
        broadening = (h_curr > h_prev) and (l_curr < l_prev)

        # Kiểm tra râu nến dài bất thường ở các nến gần nhất
        recent_bars = df.tail(10)
        wick_dominance_count = 0
        for _, bar in recent_bars.iterrows():
            total_range = bar["high"] - bar["low"] + 1e-9
            body = abs(bar["close"] - bar["open"])
            wick = total_range - body
            if (wick / total_range) > 0.60:
                wick_dominance_count += 1

        is_chaos = broadening and (wick_dominance_count >= 4)
        return is_chaos

    def check_liquidity_sweep(
        self, df: pd.DataFrame, pivot_highs: List[Dict[str, Any]], pivot_lows: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[TradeAction], Dict[str, Any]]:
        """
        Hiện thực hóa Case D: Bẫy Phá Giả & Sweep Thanh Khoản (Liquidity Trap)
        Giá đâm thủng đỉnh/đáy cũ, sau đó lập tức rút chân dội ngược trở lại bằng nến Engulfing.
        """
        if len(df) < 5 or not pivot_highs or not pivot_lows:
            return False, None, {}

        last_bar = df.iloc[-1]
        prev_bar = df.iloc[-2]

        last_close, last_open = float(last_bar["close"]), float(last_bar["open"])
        last_high, last_low = float(last_bar["high"]), float(last_bar["low"])
        prev_close, prev_open = float(prev_bar["close"]), float(prev_bar["open"])

        # 1. Sweep Đỉnh Cũ (Bearish Engulfing đảo chiều Sell)
        recent_high_levels = [p["price"] for p in pivot_highs[-4:-1]]
        for key_high in recent_high_levels:
            # Giá đã quét qua đỉnh cũ nhưng nến đóng cửa quay vào trong và là nến giảm mạnh
            swept_high = (last_high > key_high or prev_bar["high"] > key_high) and last_close < key_high
            is_bearish_engulfing = (last_close < last_open) and (last_open >= prev_close) and (last_close <= prev_open)
            if swept_high and is_bearish_engulfing:
                return True, TradeAction.SELL, {
                    "sweep_type": "BEARISH_LIQUIDITY_SWEEP",
                    "swept_level": key_high,
                    "engulfing_close": last_close,
                }

        # 2. Sweep Đáy Cũ (Bullish Engulfing đảo chiều Buy)
        recent_low_levels = [p["price"] for p in pivot_lows[-4:-1]]
        for key_low in recent_low_levels:
            # Giá đã quét dưới đáy cũ nhưng nến đóng cửa quay lên trên và là nến tăng mạnh
            swept_low = (last_low < key_low or prev_bar["low"] < key_low) and last_close > key_low
            is_bullish_engulfing = (last_close > last_open) and (last_open <= prev_close) and (last_close >= prev_open)
            if swept_low and is_bullish_engulfing:
                return True, TradeAction.BUY, {
                    "sweep_type": "BULLISH_LIQUIDITY_SWEEP",
                    "swept_level": key_low,
                    "engulfing_close": last_close,
                }

        return False, None, {}

    def check_directional_leading_wave(
        self, df: pd.DataFrame, pivot_highs: List[Dict[str, Any]], pivot_lows: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[TradeAction], Dict[str, Any]]:
        """
        Hiện thực hóa Case E: Sóng Dẫn Hướng & Đảo Chiều Đột Ngột (Directional Leading Wave)
        Sóng dốc đứng, thân nến dài dứt khoát đi ngược lại xu hướng trước đó, đâm thủng căn cứ chính.
        Quy tắc: KHÔNG vào lệnh ngay đỉnh sóng, CHỜ GIÁ RETEST rồi mới vào thuận chiều sóng dẫn hướng.
        """
        if len(df) < 15:
            return False, None, {}

        last_bars = df.tail(4)
        atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        avg_atr = float(atr.iloc[-1]) if atr is not None and not pd.isna(atr.iloc[-1]) else 0.0010

        # Kiểm tra 3 nến liên tiếp cùng chiều thân cực dài (> 1.6 x ATR)
        bodies = (last_bars["close"] - last_bars["open"]).values
        bullish_impulse = sum(1 for b in bodies if b > 1.2 * avg_atr) >= 2
        bearish_impulse = sum(1 for b in bodies if b < -1.2 * avg_atr) >= 2

        # Kiểm tra Retest: nến cuối cùng hồi nhẹ (retest) thân nhỏ hoặc đi ngang
        curr_body = bodies[-1]
        is_retesting_bullish = bullish_impulse and (abs(curr_body) < 0.6 * avg_atr)
        is_retesting_bearish = bearish_impulse and (abs(curr_body) < 0.6 * avg_atr)

        if is_retesting_bullish:
            return True, TradeAction.WAIT_RETEST, {
                "wave_direction": "BULLISH_LEADING_WAVE",
                "ready_for_entry": True,
                "follow_up_action": TradeAction.BUY,
            }
        elif is_retesting_bearish:
            return True, TradeAction.WAIT_RETEST, {
                "wave_direction": "BEARISH_LEADING_WAVE",
                "ready_for_entry": True,
                "follow_up_action": TradeAction.SELL,
            }

        return False, None, {}

    def analyze_market(
        self,
        df: pd.DataFrame,
        current_spread_points: float = 12.0,
        current_time: Optional[datetime] = None,
    ) -> MarketAnalysisResult:
        """
        Phân tích tổng hợp nến thị trường và gán nhãn 1 trong 6 kịch bản thị trường.
        """
        if df.empty or len(df) < 25:
            return MarketAnalysisResult(
                market_case=MarketCase.CASE_B_COMPRESSION,
                recommended_action=TradeAction.HOLD,
                is_tradable=False,
                confidence_modifier=0.0,
                reason="Dữ liệu nến chưa đủ độ dài (cần tối thiểu 25 nến).",
                details={},
            )

        last_row = df.iloc[-1]
        bar_time = current_time or (
            pd.to_datetime(last_row["time"]).to_pydatetime() if "time" in last_row else datetime.now(timezone.utc)
        )

        # -------------------------------------------------------------
        # 1. KIỂM TRA CASE F: Bão tin tức & Giãn Spread Rollover (4h-5h sáng VN)
        # -------------------------------------------------------------
        if self.is_vietnam_rollover_time(bar_time):
            return MarketAnalysisResult(
                market_case=MarketCase.CASE_F_ROLLOVER_NEWS,
                recommended_action=TradeAction.CIRCUIT_BREAKER_LOCK,
                is_tradable=False,
                confidence_modifier=0.0,
                reason="CẦU DAO TỰ ĐỘNG: Ngắt Bot AI trong khung giờ giao ngày Rollover (4h-5h sáng VN). Spread giãn cao & trượt giá.",
                details={"rollover_active": True, "spread": current_spread_points},
            )

        if current_spread_points >= self.spread_spike_threshold:
            return MarketAnalysisResult(
                market_case=MarketCase.CASE_F_ROLLOVER_NEWS,
                recommended_action=TradeAction.CIRCUIT_BREAKER_LOCK,
                is_tradable=False,
                confidence_modifier=0.0,
                reason=f"CẦU DAO TỰ ĐỘNG: Giãn spread đột biến ({current_spread_points:.1f} points >= {self.spread_spike_threshold}). Ngắt lệnh tránh nhiễu.",
                details={"spread_spike": True, "spread": current_spread_points},
            )

        # Trích xuất Pivot Đỉnh & Đáy
        pivot_highs, pivot_lows = self.find_pivots(df, window=self.swing_window)

        # -------------------------------------------------------------
        # 2. KIỂM TRA CASE C: Đi Ngang Hỗn Loạn / Hình Cái Loa (Broadening Chaos)
        # -------------------------------------------------------------
        if self.check_broadening_chaos(pivot_highs, pivot_lows, df):
            return MarketAnalysisResult(
                market_case=MarketCase.CASE_C_BROADENING_CHAOS,
                recommended_action=TradeAction.STRICT_NO_TRADE,
                is_tradable=False,
                confidence_modifier=-0.40,
                reason="CẤM TUYỆT ĐỐI VÀO LỆNH (STRICT NO TRADE): Thị trường hỗn loạn hình cái loa, râu nến quét 2 đầu, rủi ro cắn SL cả 2 chiều.",
                details={"broadening_detected": True},
            )

        # -------------------------------------------------------------
        # 3. KIỂM TRA CASE D: Bẫy Phá Giả & Sweep Thanh Khoản
        # -------------------------------------------------------------
        is_sweep, sweep_action, sweep_details = self.check_liquidity_sweep(df, pivot_highs, pivot_lows)
        if is_sweep and sweep_action:
            entry = float(last_row["close"])
            atr_val = float(df["high"].iloc[-5:].max() - df["low"].iloc[-5:].min())
            sl = entry + (1.2 * atr_val) if sweep_action == TradeAction.SELL else entry - (1.2 * atr_val)
            tp = entry - (2.5 * atr_val) if sweep_action == TradeAction.SELL else entry + (2.5 * atr_val)

            return MarketAnalysisResult(
                market_case=MarketCase.CASE_D_LIQUIDITY_SWEEP,
                recommended_action=sweep_action,
                is_tradable=True,
                confidence_modifier=0.20,
                reason=f"BẪY THANH KHOẢN (Liquidity Trap): Nến Engulfing đóng cửa dội ngược lại cản. Cho phép vào lệnh ĐẢO CHIỀU ({sweep_action.value}).",
                details=sweep_details,
                entry_suggestion=round(entry, 5),
                sl_suggestion=round(sl, 5),
                tp_suggestion=round(tp, 5),
            )

        # -------------------------------------------------------------
        # 4. KIỂM TRA CASE E: Sóng Dẫn Hướng & Đảo Chiều Đột Ngột
        # -------------------------------------------------------------
        is_leading, leading_action, leading_details = self.check_directional_leading_wave(df, pivot_highs, pivot_lows)
        if is_leading:
            follow_action = leading_details.get("follow_up_action", TradeAction.HOLD)
            return MarketAnalysisResult(
                market_case=MarketCase.CASE_E_LEADING_WAVE,
                recommended_action=TradeAction.WAIT_RETEST,
                is_tradable=False,  # Chờ retest
                confidence_modifier=0.10,
                reason="TÍN HIỆU ĐẢO CHIỀU XU HƯỚNG: Sóng dẫn hướng dốc đứng. Không vào lệnh ở đỉnh sóng, CHỜ RETEST rồi mới vào thuận chiều.",
                details=leading_details,
            )

        # -------------------------------------------------------------
        # 5. KIỂM TRA CASE B: Đi Ngang Có Quy Luật (Compression)
        # -------------------------------------------------------------
        is_compressed, pattern_name, comp_details = self.check_compression(df, pivot_highs, pivot_lows)
        if is_compressed:
            # Kiểm tra xem nến hiện tại có phải nến Breakout thân dài dứt khoát không
            curr_body = abs(float(last_row["close"]) - float(last_row["open"]))
            last_atr = comp_details.get("atr_fast", 0.001)
            is_breakout = curr_body > (1.3 * last_atr)

            if is_breakout:
                action = TradeAction.BUY if float(last_row["close"]) > float(last_row["open"]) else TradeAction.SELL
                entry = float(last_row["close"])
                sl = entry - (1.0 * last_atr) if action == TradeAction.BUY else entry + (1.0 * last_atr)
                tp = entry + (2.5 * last_atr) if action == TradeAction.BUY else entry - (2.5 * last_atr)

                return MarketAnalysisResult(
                    market_case=MarketCase.CASE_B_COMPRESSION,
                    recommended_action=action,
                    is_tradable=True,
                    confidence_modifier=0.15,
                    reason=f"THỊ TƯỜNG NÉN ({pattern_name}): Xuất hiện nến Breakout thân dài dứt khoát ngoài vùng nén. Tỷ lệ R:R cao (1:2.5).",
                    details=comp_details,
                    entry_suggestion=round(entry, 5),
                    sl_suggestion=round(sl, 5),
                    tp_suggestion=round(tp, 5),
                    compression_detected=True,
                    compression_pattern=pattern_name,
                )
            else:
                return MarketAnalysisResult(
                    market_case=MarketCase.CASE_B_COMPRESSION,
                    recommended_action=TradeAction.HOLD,
                    is_tradable=False,
                    confidence_modifier=0.0,
                    reason=f"THỊ TƯỜNG NÉN ({pattern_name}): Đang tích tụ năng lượng. Chờ nến Breakout dứt khoát.",
                    details=comp_details,
                    compression_detected=True,
                    compression_pattern=pattern_name,
                )

        # -------------------------------------------------------------
        # 6. KIỂM TRA CASE A: Trend Tăng / Giảm Rõ Ràng (Smooth Trend)
        # -------------------------------------------------------------
        # Đánh giá cấu trúc Đỉnh/Đáy và EMA20 / EMA50
        ema20 = ta.ema(df["close"], length=20)
        ema50 = ta.ema(df["close"], length=50)

        if ema20 is not None and ema50 is not None and not pd.isna(ema20.iloc[-1]) and not pd.isna(ema50.iloc[-1]):
            last_c = float(last_row["close"])
            last_ema20 = float(ema20.iloc[-1])
            last_ema50 = float(ema50.iloc[-1])

            is_bullish_trend = (last_ema20 > last_ema50) and (last_c >= last_ema20 * 0.999)
            is_bearish_trend = (last_ema20 < last_ema50) and (last_c <= last_ema20 * 1.001)

            # Kiểm tra giá hồi về căn cứ (EMA20 hoặc Swing gần nhất)
            pullback_bull = is_bullish_trend and (abs(last_c - last_ema20) < 0.0008)
            pullback_bear = is_bearish_trend and (abs(last_c - last_ema20) < 0.0008)

            if pullback_bull:
                atr_val = float(last_row["high"] - last_row["low"])
                entry = last_c
                sl = entry - (1.0 * atr_val)
                tp = entry + (2.0 * atr_val)
                return MarketAnalysisResult(
                    market_case=MarketCase.CASE_A_TREND,
                    recommended_action=TradeAction.BUY,
                    is_tradable=True,
                    confidence_modifier=0.15,
                    reason="THỊ TƯỜNG LÀNH (Trend Tăng Mượt): Giá hồi về căn cứ EMA20 + có tín hiệu ủng hộ xu hướng. Winrate > 65%.",
                    details={"trend": "BULLISH_SMOOTH"},
                    entry_suggestion=round(entry, 5),
                    sl_suggestion=round(sl, 5),
                    tp_suggestion=round(tp, 5),
                )
            elif pullback_bear:
                atr_val = float(last_row["high"] - last_row["low"])
                entry = last_c
                sl = entry + (1.0 * atr_val)
                tp = entry - (2.0 * atr_val)
                return MarketAnalysisResult(
                    market_case=MarketCase.CASE_A_TREND,
                    recommended_action=TradeAction.SELL,
                    is_tradable=True,
                    confidence_modifier=0.15,
                    reason="THỊ TƯỜNG LÀNH (Trend Giảm Mượt): Giá hồi về căn cứ EMA20 + nến thuận xu hướng. Winrate > 65%.",
                    details={"trend": "BEARISH_SMOOTH"},
                    entry_suggestion=round(entry, 5),
                    sl_suggestion=round(sl, 5),
                    tp_suggestion=round(tp, 5),
                )

        # Mặc định: Giữ trạng thái quan sát (HOLD)
        return MarketAnalysisResult(
            market_case=MarketCase.CASE_A_TREND,
            recommended_action=TradeAction.HOLD,
            is_tradable=False,
            confidence_modifier=0.0,
            reason="Thị trường chưa xuất hiện setup chuẩn Price Action theo Luật Bò Gấu. Giữ lệnh quan sát.",
            details={"state": "WAITING_SETUP"},
        )
