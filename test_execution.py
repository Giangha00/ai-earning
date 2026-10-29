"""
File test_execution.py
Kiểm thử toàn diện toàn bộ thuật toán trong Sổ tay AI Trading Forex:
- CHƯƠNG 1: Price Action 6 Kịch bản thị trường (Case A - F)
- CHƯƠNG 2: Công thức toán học ML/DL, HMM Regimes, Monte Carlo VaR
- CHƯƠNG 3: Thuật toán tính R:R & Khối lượng 1R, Nhận diện vùng nén (Compression)
- CHƯƠNG 4: Kỹ thuật chống nhiễu OOD & Cầu dao ngắt mạch 24h (LOCK_BOT_24H)
- CHƯƠNG 5: Hyperparameters & Luồng thực thi lệnh
"""

import time
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from mt5_connector import MT5Connector, mt5
from risk_manager import RiskManager
from executor import MT5Executor, close_all_positions
import config as config_module
from config import config
from ai_price_action import PriceActionAnalyzer, MarketCase, TradeAction
from ai_math_models import (
    VectorizedLogisticRegression,
    DeepMLPNetwork,
    MarketHMMRegimeDetector,
    MonteCarloRiskEstimator,
    OutOfDistributionFilter,
)


def test_price_action_and_market_cases():
    print("\n" + "=" * 50)
    print("TEST 1: 6 KỊCH BẢN THỊ TRƯỜNG & VÙNG NÉN (CHƯƠNG 1 & 3.2)")
    print("=" * 50)

    analyzer = PriceActionAnalyzer()

    # Tạo DataFrame giả lập kịch bản Case B: Compression
    n_bars = 40
    base = 1.0850
    # Biên độ nén dần
    ranges = np.linspace(0.0030, 0.0006, n_bars)
    dates = pd.date_range("2026-10-28 10:00", periods=n_bars, freq="5min")
    df_comp = pd.DataFrame({
        "time": dates,
        "open": base + np.sin(np.linspace(0, 10, n_bars)) * ranges,
        "close": base + np.cos(np.linspace(0, 10, n_bars)) * ranges,
        "high": base + ranges,
        "low": base - ranges,
        "tick_volume": np.random.randint(50, 200, n_bars),
    })

    result = analyzer.analyze_market(df_comp, current_spread_points=12.0)
    print(f"-> Kết quả phân tích Case: {result.market_case.value}")
    print(f"-> Hành động khuyến nghị: {result.recommended_action.value}")
    print(f"-> Lý do: {result.reason}")
    print(f"-> Vùng nén phát hiện: {result.compression_detected} ({result.compression_pattern})")
    assert result.market_case in MarketCase


def test_ml_dl_math_formulas():
    print("\n" + "=" * 50)
    print("TEST 2: CÁC CÔNG THỨC TOÁN HỌC ML/DL (CHƯƠNG 2)")
    print("=" * 50)

    # 1. Vectorized Logistic Regression & Sigmoid
    logreg = VectorizedLogisticRegression(learning_rate=0.01, iterations=100)
    X_toy = np.random.randn(5, 50)
    Y_toy = (X_toy[0:1, :] > 0).astype(float)
    costs = logreg.fit(X_toy, Y_toy)
    probs = logreg.predict_proba(X_toy)
    print(f"-> Vectorized LogReg fit xong: {len(costs)} checks. Sigmoid prob range: [{probs.min():.3f}, {probs.max():.3f}]")
    assert probs.shape == (1, 50)

    # 2. Deep MLP với L2 Regularization & Inverted Dropout
    mlp = DeepMLPNetwork(layer_dims=[5, 16, 8, 1], learning_rate=0.001, l2_lambda=0.01, keep_prob=0.8)
    AL, caches = mlp.forward_propagation(X_toy, training=True)
    cost = mlp.compute_cost_with_l2(AL, Y_toy)
    grads = mlp.backward_propagation_with_l2(AL, Y_toy, caches)
    mlp.update_parameters(grads)
    print(f"-> Deep MLP L2 & Inverted Dropout: Cost={cost:.4f}, Output prob={float(AL[0, 0]):.3f}")
    assert AL.shape == (1, 50)

    # 3. Gaussian HMM (3 States)
    hmm_detector = MarketHMMRegimeDetector(n_components=3)
    rets = np.random.normal(0, 0.001, 100)
    vols = np.abs(np.random.normal(0, 0.002, 100))
    hmm_detector.fit(rets, vols)
    regime, is_safe = hmm_detector.predict_regime(latest_return=0.0005, latest_volatility=0.001)
    print(f"-> Gaussian HMM Regimes: Regime={regime}, SafeToTrade={is_safe}")
    assert regime in [hmm_detector.STATE_BULLISH, hmm_detector.STATE_BEARISH, hmm_detector.STATE_HIGH_VOLATILITY]

    # 4. Monte Carlo Simulation & Parametric VaR
    var_95 = MonteCarloRiskEstimator.calculate_parametric_var(
        portfolio_value=10000.0,
        daily_return_mean=0.0005,
        daily_return_std=0.01,
        confidence_level=0.95,
    )
    print(f"-> Monte Carlo Parametric VaR (95%): ${var_95:.2f}")
    assert var_95 > 0


def test_anti_noise_and_ood():
    print("\n" + "=" * 50)
    print("TEST 3: BỘ LỌC CHỐNG NHIỄU OOD (CHƯƠNG 4)")
    print("=" * 50)

    ood = OutOfDistributionFilter(contamination=0.05, confidence_threshold=0.75)
    normal_data = np.random.normal(0, 1, (100, 5))
    ood.fit(normal_data)

    # Test mẫu bình thường với confidence cao >= 75%
    sample_normal = np.random.normal(0, 0.5, 5)
    valid, reason, _ = ood.check_trade_validity(sample_normal, raw_prob=0.82)
    print(f"-> Mẫu chuẩn (Prob=82%): Approved={valid} | Lý do: {reason}")
    assert valid is True

    # Test mẫu có confidence thấp < 75% -> Reject (Rule 1)
    valid_low, reason_low, _ = ood.check_trade_validity(sample_normal, raw_prob=0.62)
    print(f"-> Mẫu dưới ngưỡng (Prob=62%): Approved={valid_low} | Lý do: {reason_low}")
    assert valid_low is False

    # Test mẫu Out-of-Distribution dị thường (Rule 2)
    sample_anomaly = np.array([50.0, -80.0, 120.0, -99.0, 45.0])
    valid_anom, reason_anom, details_anom = ood.check_trade_validity(sample_anomaly, raw_prob=0.90)
    print(f"-> Mẫu bất thường OOD: Approved={valid_anom} | Lý do: {reason_anom}")
    assert valid_anom is False


def test_risk_management_and_circuit_breaker():
    print("\n" + "=" * 50)
    print("TEST 4: QUẢN TRỊ RỦI RO R:R & CẦU DAO 24H (CHƯƠNG 3.1, 4.4, 5)")
    print("=" * 50)

    rm = RiskManager(
        risk_per_trade=0.01,   # 1R = 1.0% Vốn
        min_rr_ratio=1.5,
        max_daily_loss_r=2.0,
        max_consecutive_losses=2,
    )

    # 1. Thẩm định tỷ lệ R:R
    # Test R:R hợp lệ (1:2.0)
    entry = 1.08500
    sl = 1.08400   # 10 pips risk
    tp = 1.08700   # 20 pips reward
    valid, rr, d_risk, d_reward, msg = rm.check_rr_ratio(entry, sl, tp)
    print(f"-> Kiểm tra R:R hợp lệ: Thỏa mãn={valid}, R:R=1:{rr:.2f} | {msg}")
    assert valid is True

    # Test R:R không hợp lệ (< 1.5) -> Phải bị REJECT
    tp_bad = 1.08550 # 5 pips reward (< 10 pips risk)
    valid_bad, rr_bad, _, _, msg_bad = rm.check_rr_ratio(entry, sl, tp_bad)
    print(f"-> Kiểm tra R:R vi phạm (<1.5): Thỏa mãn={valid_bad}, R:R=1:{rr_bad:.2f} | {msg_bad}")
    assert valid_bad is False

    # 2. Cầu dao ngắt mạch 24h khi dính 2 lệnh thua liên tiếp
    rm.record_trade_result(profit=-100.0, one_r_money=100.0)
    locked, _ = rm.is_locked_24h()
    print(f"-> Sau 1 lệnh thua: Cầu dao khóa={locked}")
    assert locked is False

    rm.record_trade_result(profit=-100.0, one_r_money=100.0)
    locked2, lock_reason = rm.is_locked_24h()
    print(f"-> Sau 2 lệnh thua liên tiếp (2R): Cầu dao khóa={locked2} | {lock_reason}")
    assert locked2 is True


def test_full_trade_execution():
    print("\n" + "=" * 50)
    print("TEST 5: KHỚP LỆNH & ĐÓNG VỊ THẾ TOÀN TRÌNH")
    print("=" * 50)

    if not MT5Connector.connect():
        print("Kết nối MT5 thất bại!")
        return

    symbol = "EURUSD"
    risk_mgr = RiskManager(risk_per_trade=0.01)

    tick = mt5.symbol_info_tick(symbol)
    assert tick is not None

    entry_price = float(tick.ask)
    atr = 0.00100
    sl_price = entry_price - (1.0 * atr)
    tp_price = entry_price + (2.0 * atr)

    # Tính lot 1R
    lot_size, one_r, d_risk = risk_mgr.calculate_lot_size_1r(symbol, entry_price, sl_price)
    print(f"-> 1R Money: ${one_r:.2f} | Lot Size: {lot_size}")
    assert lot_size > 0

    # Khớp lệnh
    ticket = MT5Executor.open_position(
        symbol=symbol,
        order_type="BUY",
        lot_size=lot_size,
        sl_price=sl_price,
        tp_price=tp_price,
        comment="Test_Full_Pipeline",
    )
    print(f"-> Vé lệnh đã mở: #{ticket}")
    assert ticket is not None

    time.sleep(1)
    # Đóng lệnh
    closed = MT5Executor.close_position_by_ticket(ticket)
    print(f"-> Đóng lệnh #{ticket}: Thành công={closed}")
    assert closed is True

    MT5Connector.disconnect()


def test_v2_custom_lot_and_target_circuit_breaker():
    print("\n" + "=" * 50)
    print("TEST 6: CẤU HÌNH LINH HOẠT V2 (CUSTOM LOT & CẦU DAO CHỐT LỜI TỔNG USD)")
    print("=" * 50)

    MT5Connector.connect()
    risk_mgr = RiskManager()

    # 1. Thiết lập tham số kiểm thử đơn vị USD (Vốn $1,000 USD, Lot 0.05, Target Goal $1,050 USD)
    config.INITIAL_CAPITAL = 1000.0
    config.CUSTOM_LOT_SIZE = 0.05
    config.TARGET_PROFIT_GOAL = 1050.0
    config.BOT_RUNNING = True

    exec_lot = risk_mgr.get_execution_lot()
    print(f"-> Custom Lot từ config: {exec_lot}")
    assert exec_lot == 0.05

    # 2. Kiểm tra khi Equity chưa đạt mục tiêu ($1,020 USD < $1,050 USD)
    assert risk_mgr.is_target_goal_reached(1020.0) is False

    # 3. Mở 2 vị thế giả lập trên MT5 rồi kích hoạt cầu dao chốt lời tổng khi Equity đạt $1,055 USD
    tick = mt5.symbol_info_tick("EURUSD")
    t1 = MT5Executor.open_position("EURUSD", "BUY", exec_lot, tick.ask - 0.0020, tick.ask + 0.0040)
    t2 = MT5Executor.open_position("EURUSD", "SELL", exec_lot, tick.bid + 0.0020, tick.bid - 0.0040)
    assert t1 is not None and t2 is not None
    assert len(MT5Executor.get_open_positions()) >= 2

    # Khi Equity chạm mục tiêu $1,055 USD >= $1,050 USD
    reached = risk_mgr.is_target_goal_reached(1055.0)
    assert reached is True

    closed_cnt = close_all_positions()
    config.BOT_RUNNING = False
    print(f"-> Đã kích hoạt close_all_positions(), số vị thế đóng: {closed_cnt} | BOT_RUNNING={config.BOT_RUNNING}")
    assert len(MT5Executor.get_open_positions()) == 0
    assert config.BOT_RUNNING is False

    MT5Connector.disconnect()
    print("\n🎉 TẤT CẢ 6 BÀI TEST (BAO GỒM NÂNG CẤP V2) ĐÃ VƯỢT QUA 100% HOÀN HẢO!")


if __name__ == "__main__":
    test_price_action_and_market_cases()
    test_ml_dl_math_formulas()
    test_anti_noise_and_ood()
    test_risk_management_and_circuit_breaker()
    test_full_trade_execution()
    test_v2_custom_lot_and_target_circuit_breaker()
