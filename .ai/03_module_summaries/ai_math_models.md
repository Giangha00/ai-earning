# Module Summary: Mathematical Models & Anti-Noise Framework (`ai_math_models.py`)

## 1. Mục đích
Hiện thực hóa toàn bộ các công thức toán học Machine Learning & Deep Learning (CHƯƠNG 2) và 5 lớp màng lọc kỹ thuật chống nhiễu OOD (CHƯƠNG 4) theo Sổ tay thuật toán Bot AI Trading Forex Chuyên Sâu.

## 2. Các thành phần toán học
1. **Vectorized Logistic Regression & Sigmoid (2.1 - 2.4)**:
   - $Z = w^T X + b$, $a = \hat{y} = \sigma(Z) = \frac{1}{1 + e^{-Z}}$ (Confidence Score).
   - Binary Cross-Entropy Cost: $J(w, b) = -\frac{1}{m} \sum [y \log \hat{y} + (1-y)\log(1-\hat{y})]$.
   - Lan truyền ngược vectơ hóa: $dZ = A - Y$, $dw = \frac{1}{m} X dZ^T$, $db = \frac{1}{m} \sum dZ$.
2. **Deep MLP với L2 Regularization & Inverted Dropout (2.5, 4.1, 4.2)**:
   - $L$-layer neural network: Hidden layer ReLU, Output layer Sigmoid.
   - L2 Regularization ($\lambda = 0.01$): Phạt độ lớn trọng số $W$, ngăn ngừa Overfitting.
   - Inverted Dropout ($keep\_prob = 0.8$): Ngắt ngẫu nhiên 20% neuron ở mỗi lần lặp, buộc mô hình học các đặc trưng độc lập.
3. **Gaussian Hidden Markov Model (HMM) 3 Trạng thái (2.6)**:
   - Tách 3 trạng thái ẩn ($K=3$): `BULLISH`, `BEARISH`, `HIGH_VOLATILITY_CHAOS`.
   - Quy tắc lọc nhiễu: Nếu $S_t == \text{HIGH\_VOLATILITY\_CHAOS}$ -> Bot AI lập tức ngắt lệnh!
4. **Monte Carlo Simulation & Parametric VaR (2.8)**:
   - Geometric Brownian Motion: $S_t = S_0 \exp\left((\mu - 0.5\sigma^2)t + \sigma \sqrt{t} Z_t\right)$.
   - Parametric VaR tại độ tin cậy $(1-\alpha)$: $\text{VaR}_\alpha = \text{Portfolio\_Value} \cdot (Z_{1-\alpha}\sigma\sqrt{t} - \mu t)$.
5. **Out-of-Distribution (OOD) Filter bằng Isolation Forest (4.3)**:
   - Rule 1: Confidence Score $< 0.75$ -> Không vào lệnh (HOLD).
   - Rule 2: Anomaly Score từ Isolation Forest $> \text{Threshold\_OOD}$ -> Tự động cảnh báo DỮ LIỆU LẠ & BỎ QUA.
