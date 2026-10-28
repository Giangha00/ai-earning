"""
Module ai_math_models.py
Hiện thực hóa CHƯƠNG 2: CÁC CÔNG THỨC TOÁN HỌC DỰ ĐOÁN CỦA MACHINE LEARNING & DEEP LEARNING
và CHƯƠNG 4: KỸ THUẬT CHỐNG NHIỄU & CHỐNG OVERFITTING BÀI BẢN (ANTI-NOISE FRAMEWORK)
theo Sổ tay thuật toán Bot AI Trading Forex Chuyên Sâu.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List
import numpy as np
from sklearn.ensemble import IsolationForest
from hmmlearn import hmm

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")


# =====================================================================
# 2.1 - 2.4: LOGISTIC REGRESSION VECTƠ HÓA & SIGMOID ACTIVATION
# =====================================================================

class VectorizedLogisticRegression:
    """
    Hiện thực hóa CHƯƠNG 2.1 - 2.4:
    - Hàm kích hoạt Sigmoid: a = sigma(z) = 1 / (1 + e^-z)
    - Hàm mất mát Binary Cross-Entropy Cost: J(w,b) = - 1/m * sum(y*log(a) + (1-y)*log(1-a))
    - Vectorized Gradient Descent:
        dZ = A - Y
        dw = (1/m) * X @ dZ.T
        db = (1/m) * sum(dZ)
        w := w - alpha * dw
        b := b - alpha * db
    """

    def __init__(self, learning_rate: float = 0.001, iterations: int = 1000):
        self.learning_rate = learning_rate
        self.iterations = iterations
        self.w: Optional[np.ndarray] = None  # Shape (n_x, 1)
        self.b: float = 0.0

    @staticmethod
    def sigmoid(z: np.ndarray) -> np.ndarray:
        """Hàm kích hoạt Sigmoid giới hạn nghiêm ngặt xác suất trong [0, 1]."""
        # Tránh overflow số mũ với np.clip
        z_clipped = np.clip(z, -500, 500)
        return 1.0 / (1.0 + np.exp(-z_clipped))

    @staticmethod
    def compute_bce_cost(a: np.ndarray, y: np.ndarray, eps: float = 1e-15) -> float:
        """Hàm chi phí Binary Cross-Entropy."""
        m = y.shape[1]
        a_safe = np.clip(a, eps, 1.0 - eps)
        cost = - (1.0 / m) * np.sum(y * np.log(a_safe) + (1.0 - y) * np.log(1.0 - a_safe))
        return float(np.squeeze(cost))

    def fit(self, X: np.ndarray, Y: np.ndarray) -> List[float]:
        """
        Huấn luyện Vectorized Gradient Descent.
        X shape: (n_x, m) - n_x features, m samples
        Y shape: (1, m)
        """
        n_x, m = X.shape
        self.w = np.zeros((n_x, 1))
        self.b = 0.0
        costs = []

        for i in range(self.iterations):
            # Lan truyền tiến (Forward Propagation)
            Z = np.dot(self.w.T, X) + self.b  # Shape (1, m)
            A = self.sigmoid(Z)

            # Tính đạo hàm lan truyền ngược (Backward Propagation)
            dZ = A - Y  # Shape (1, m)
            dw = (1.0 / m) * np.dot(X, dZ.T)  # Shape (n_x, 1)
            db = float((1.0 / m) * np.sum(dZ))

            # Cập nhật tham số
            self.w -= self.learning_rate * dw
            self.b -= self.learning_rate * db

            if i % 100 == 0:
                cost = self.compute_bce_cost(A, Y)
                costs.append(cost)

        return costs

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Trả về xác suất Confidence Score P(y=1 | x)."""
        if self.w is None:
            raise ValueError("Mô hình chưa được huấn luyện.")
        Z = np.dot(self.w.T, X) + self.b
        return self.sigmoid(Z)


# =====================================================================
# 2.5: MULTI-LAYER PERCEPTRON (MLP) VỚI L2 REGULARIZATION & DROPOUT
# =====================================================================

class DeepMLPNetwork:
    """
    Hiện thực hóa CHƯƠNG 2.5 & CHƯƠNG 4.1, 4.2:
    - Deep Neural Network L layers (ReLU cho hidden, Sigmoid cho output).
    - L2 Regularization (Weight Decay): lambda_reg = 0.01.
    - Inverted Dropout: keep_prob = 0.8.
    """

    def __init__(
        self,
        layer_dims: List[int],
        learning_rate: float = 0.001,
        l2_lambda: float = 0.01,
        keep_prob: float = 0.8,
    ):
        self.layer_dims = layer_dims  # e.g. [n_x, 32, 16, 1]
        self.learning_rate = learning_rate
        self.l2_lambda = l2_lambda
        self.keep_prob = keep_prob
        self.parameters: Dict[str, np.ndarray] = {}
        self.L = len(layer_dims) - 1
        self._initialize_parameters()

    def _initialize_parameters(self):
        """Khởi tạo trọng số He/Xavier."""
        np.random.seed(42)
        for l in range(1, len(self.layer_dims)):
            self.parameters[f"W{l}"] = np.random.randn(
                self.layer_dims[l], self.layer_dims[l - 1]
            ) * np.sqrt(2.0 / self.layer_dims[l - 1])
            self.parameters[f"b{l}"] = np.zeros((self.layer_dims[l], 1))

    @staticmethod
    def relu(z: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        return np.maximum(0, z), z

    @staticmethod
    def relu_backward(dA: np.ndarray, z: np.ndarray) -> np.ndarray:
        dZ = np.array(dA, copy=True)
        dZ[z <= 0] = 0
        return dZ

    @staticmethod
    def sigmoid(z: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        z_clipped = np.clip(z, -500, 500)
        s = 1.0 / (1.0 + np.exp(-z_clipped))
        return s, z

    def forward_propagation(self, X: np.ndarray, training: bool = True) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Lan truyền tiến với Inverted Dropout cho các lớp ẩn:
        d[l] = rand(...) < keep_prob
        A[l] = (A[l] * d[l]) / keep_prob
        """
        caches = {}
        A = X
        caches["A0"] = A

        for l in range(1, self.L):
            W = self.parameters[f"W{l}"]
            b = self.parameters[f"b{l}"]
            Z = np.dot(W, A) + b
            A, z_cache = self.relu(Z)
            caches[f"Z{l}"] = z_cache
            caches[f"A{l}"] = A

            if training and self.keep_prob < 1.0:
                D = np.random.rand(A.shape[0], A.shape[1]) < self.keep_prob
                A = (A * D) / self.keep_prob
                caches[f"D{l}"] = D
                caches[f"A{l}"] = A

        # Lớp đầu ra (Sigmoid Activation)
        W_last = self.parameters[f"W{self.L}"]
        b_last = self.parameters[f"b{self.L}"]
        Z_last = np.dot(W_last, A) + b_last
        AL, z_cache_last = self.sigmoid(Z_last)
        caches[f"Z{self.L}"] = z_cache_last
        caches[f"A{self.L}"] = AL

        return AL, caches

    def compute_cost_with_l2(self, AL: np.ndarray, Y: np.ndarray) -> float:
        """
        Cost Function cộng L2 Regularization (Weight Decay):
        J_reg = J + (lambda / (2m)) * sum(||W[l]||_F^2)
        """
        m = Y.shape[1]
        eps = 1e-15
        AL_safe = np.clip(AL, eps, 1.0 - eps)
        cross_entropy_cost = - (1.0 / m) * np.sum(Y * np.log(AL_safe) + (1.0 - Y) * np.log(1.0 - AL_safe))

        l2_cost = 0.0
        for l in range(1, self.L + 1):
            l2_cost += np.sum(np.square(self.parameters[f"W{l}"]))
        l2_cost = (self.l2_lambda / (2.0 * m)) * l2_cost

        return float(cross_entropy_cost + l2_cost)

    def backward_propagation_with_l2(self, AL: np.ndarray, Y: np.ndarray, caches: Dict[str, Any]) -> Dict[str, np.ndarray]:
        """
        Lan truyền ngược có tích hợp L2 Regularization:
        dW[l] = dW[l]_unreg + (lambda / m) * W[l]
        """
        grads = {}
        m = Y.shape[1]

        # Đạo hàm lớp Sigmoid đầu ra: dZ = AL - Y
        dZ = AL - Y
        grads[f"dZ{self.L}"] = dZ
        A_prev = caches[f"A{self.L - 1}"]
        W_curr = self.parameters[f"W{self.L}"]

        grads[f"dW{self.L}"] = (1.0 / m) * np.dot(dZ, A_prev.T) + (self.l2_lambda / m) * W_curr
        grads[f"db{self.L}"] = (1.0 / m) * np.sum(dZ, axis=1, keepdims=True)
        dA_prev = np.dot(W_curr.T, dZ)

        # Lan truyền ngược qua các lớp ẩn
        for l in reversed(range(1, self.L)):
            if self.keep_prob < 1.0 and f"D{l}" in caches:
                dA_prev = (dA_prev * caches[f"D{l}"]) / self.keep_prob

            Z_curr = caches[f"Z{l}"]
            dZ = self.relu_backward(dA_prev, Z_curr)
            A_prev = caches[f"A{l - 1}"]
            W_curr = self.parameters[f"W{l}"]

            grads[f"dW{l}"] = (1.0 / m) * np.dot(dZ, A_prev.T) + (self.l2_lambda / m) * W_curr
            grads[f"db{l}"] = (1.0 / m) * np.sum(dZ, axis=1, keepdims=True)
            if l > 1:
                dA_prev = np.dot(W_curr.T, dZ)

        return grads

    def update_parameters(self, grads: Dict[str, np.ndarray]):
        for l in range(1, self.L + 1):
            self.parameters[f"W{l}"] -= self.learning_rate * grads[f"dW{l}"]
            self.parameters[f"b{l}"] -= self.learning_rate * grads[f"db{l}"]

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Dự đoán ở chế độ Inference (tắt Dropout)."""
        AL, _ = self.forward_propagation(X, training=False)
        return AL


# =====================================================================
# 2.6: GAUSSIAN HIDDEN MARKOV MODEL (HMM - PHÂN LOẠI TRẠNG THÁI THỊ TRƯỜNG)
# =====================================================================

class MarketHMMRegimeDetector:
    """
    Hiện thực hóa CHƯƠNG 2.6:
    Gaussian Hidden Markov Model phân tách 3 trạng thái ẩn (K=3):
    - State 0: Bullish (Thị trường bò)
    - State 1: Bearish (Thị trường gấu)
    - State 2: High Volatility / Chaos (Nhiễu loạn cao)
    QUY TẮC LỌC NHIỄU: Nếu S_t == State_High_Volatility, Bot lập tức ngắt lệnh giao dịch!
    """

    STATE_BULLISH = "BULLISH"
    STATE_BEARISH = "BEARISH"
    STATE_HIGH_VOLATILITY = "HIGH_VOLATILITY_CHAOS"

    def __init__(self, n_components: int = 3, random_state: int = 42):
        self.n_components = n_components
        self.model = hmm.GaussianHMM(
            n_components=n_components,
            covariance_type="diag",
            min_covar=1e-4,
            n_iter=100,
            random_state=random_state,
        )
        self.is_fitted = False
        self.state_labels: Dict[int, str] = {}

    def fit(self, returns: np.ndarray, volatility: np.ndarray):
        """
        Huấn luyện HMM với ma trận quan sát X = [Returns, Volatility].
        """
        X = np.column_stack([returns, volatility])
        # Loại bỏ NaN
        mask = ~np.isnan(X).any(axis=1)
        X_clean = X[mask]

        if len(X_clean) < 50:
            logging.warning("Dữ liệu không đủ để fit HMM.")
            return

        self.model.fit(X_clean)
        self.is_fitted = True

        # Gán nhãn cho các trạng thái dựa trên mean return và variance
        means = self.model.means_  # Shape (K, 2)
        covars = self.model.covars_  # Shape (K, 2) với covariance_type="diag"

        # Trạng thái có phương sai biến động lớn nhất -> High Volatility
        vol_variances = [covars[i, 1] if covars.ndim == 2 else covars[i][1, 1] for i in range(self.n_components)]
        chaos_idx = int(np.argmax(vol_variances))

        remaining_indices = [i for i in range(self.n_components) if i != chaos_idx]
        if len(remaining_indices) >= 2:
            if means[remaining_indices[0]][0] > means[remaining_indices[1]][0]:
                bull_idx, bear_idx = remaining_indices[0], remaining_indices[1]
            else:
                bear_idx, bull_idx = remaining_indices[0], remaining_indices[1]
        else:
            bull_idx, bear_idx = 0, 1

        self.state_labels = {
            bull_idx: self.STATE_BULLISH,
            bear_idx: self.STATE_BEARISH,
            chaos_idx: self.STATE_HIGH_VOLATILITY,
        }
        logging.info(f"HMM fitted successfully: {self.state_labels}")

    def predict_regime(self, latest_return: float, latest_volatility: float) -> Tuple[str, bool]:
        """
        Dự đoán trạng thái thị trường hiện tại.
        Trả về: (tên_trạng_thái, is_safe_to_trade)
        Nếu là HIGH_VOLATILITY_CHAOS -> is_safe_to_trade = False!
        """
        if not self.is_fitted:
            # Fallback nếu chưa fit
            if abs(latest_return) > 0.005 or latest_volatility > 0.003:
                return self.STATE_HIGH_VOLATILITY, False
            return self.STATE_BULLISH if latest_return >= 0 else self.STATE_BEARISH, True

        obs = np.array([[latest_return, latest_volatility]])
        try:
            state_idx = int(self.model.predict(obs)[-1])
            regime = self.state_labels.get(state_idx, self.STATE_HIGH_VOLATILITY)
            is_safe = (regime != self.STATE_HIGH_VOLATILITY)
            return regime, is_safe
        except Exception as e:
            logging.error(f"Lỗi dự đoán HMM: {e}")
            return self.STATE_HIGH_VOLATILITY, False


# =====================================================================
# 2.8: MÔ PHỎNG MONTE CARLO & VALUE AT RISK (VaR)
# =====================================================================

class MonteCarloRiskEstimator:
    """
    Hiện thực hóa CHƯƠNG 2.8:
    - Geometric Brownian Motion: S_t = S_0 * exp((mu - 0.5 * sigma^2)*t + sigma * sqrt(t) * Z_t)
    - Parametric VaR (Value at Risk): VaR_alpha = Portfolio_Value * (Z_{1-alpha} * sigma * sqrt(t) - mu * t)
    Định lượng số tiền lỗ lớn nhất có thể xảy ra để thiết lập cầu dao ngắt mạch an toàn.
    """

    @staticmethod
    def simulate_gbm_paths(
        s0: float,
        mu: float,
        sigma: float,
        t: float = 1.0,  # Thời gian dự phóng (e.g. 1 ngày = 1.0)
        n_steps: int = 50,
        n_simulations: int = 1000,
    ) -> np.ndarray:
        """Tạo n_simulations kịch bản đường giá tương lai."""
        dt = t / n_steps
        paths = np.zeros((n_steps + 1, n_simulations))
        paths[0] = s0

        for step in range(1, n_steps + 1):
            zt = np.random.standard_normal(n_simulations)
            paths[step] = paths[step - 1] * np.exp(
                (mu - 0.5 * (sigma ** 2)) * dt + sigma * np.sqrt(dt) * zt
            )
        return paths

    @staticmethod
    def calculate_parametric_var(
        portfolio_value: float,
        daily_return_mean: float,
        daily_return_std: float,
        confidence_level: float = 0.95,
        horizon_days: int = 1,
    ) -> float:
        """
        Tính Parametric Value at Risk (VaR):
        Với confidence 95% -> Z = 1.645, 99% -> Z = 2.326.
        """
        # Tra cứu Z-score
        z_scores = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}
        z_val = z_scores.get(confidence_level, 1.645)

        t = horizon_days
        var = portfolio_value * (z_val * daily_return_std * np.sqrt(t) - daily_return_mean * t)
        return float(max(0.0, var))


# =====================================================================
# 4.3 & 4.4: BỘ LỌC CHỐNG NHIỄU OOD (ISOLATION FOREST) & CẦU DAO 24H
# =====================================================================

class OutOfDistributionFilter:
    """
    Hiện thực hóa CHƯƠNG 4.3:
    Phát hiện bất thường Out-of-Distribution (OOD) bằng Isolation Forest:
    - Rule 1: Confidence Score P(y=1 | x) < 0.75 ==> KHÔNG VÀO LỆNH (HOLD).
    - Rule 2: Anomaly Score từ Isolation Forest > Threshold_OOD ==> Cảnh báo Dữ liệu Lạ & Bỏ qua!
    """

    def __init__(self, contamination: float = 0.05, confidence_threshold: float = 0.75):
        self.confidence_threshold = confidence_threshold
        self.iso_forest = IsolationForest(
            n_estimators=100,
            contamination=contamination,
            random_state=42,
            n_jobs=-1,
        )
        self.is_fitted = False

    def fit(self, X: np.ndarray):
        """Fit Isolation Forest trên dữ liệu bình thường."""
        if len(X) < 50:
            return
        self.iso_forest.fit(X)
        self.is_fitted = True

    def check_trade_validity(
        self,
        features_vector: np.ndarray,
        raw_prob: float,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Đánh giá độ tự tin và phát hiện dị thường OOD:
        Trả về: (is_approved, reason, details)
        """
        # Rule 1: Ngưỡng tự tin tối thiểu >= 75%
        if raw_prob < self.confidence_threshold:
            return False, f"Confidence Score ({raw_prob * 100:.1f}%) < {self.confidence_threshold * 100:.1f}%. Không đủ độ an toàn (HOLD).", {
                "rule1_passed": False,
                "confidence": raw_prob,
                "threshold": self.confidence_threshold,
            }

        # Rule 2: Kiểm tra dữ liệu lạ (OOD) với Isolation Forest
        is_anomaly = False
        anomaly_score = 0.0
        if self.is_fitted and features_vector is not None:
            feat = features_vector.reshape(1, -1)
            pred = self.iso_forest.predict(feat)[0]  # -1 là bất thường, 1 là bình thường
            anomaly_score = float(-self.iso_forest.score_samples(feat)[0])
            if pred == -1:
                is_anomaly = True
                return False, f"TỰ ĐỘNG CẢNH BÁO DỮ LIỆU LẠ (OOD Anomaly Score: {anomaly_score:.3f}). Dữ liệu chưa từng có trong tập đào tạo -> Bỏ qua!", {
                    "rule1_passed": True,
                    "rule2_passed": False,
                    "anomaly_score": anomaly_score,
                    "is_ood": True,
                }

        return True, "Thỏa mãn cả Ngưỡng tự tin (>=75%) và Màng lọc chống nhiễu OOD.", {
            "rule1_passed": True,
            "rule2_passed": True,
            "confidence": raw_prob,
            "anomaly_score": anomaly_score,
            "is_ood": False,
        }
