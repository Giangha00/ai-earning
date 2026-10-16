# Module Summary: Model Trainer (`train_model.py`)

## 1. Mục đích
Huấn luyện mô hình Machine Learning nhị phân (Binary Classification) sử dụng thuật toán Gradient Boosting (LightGBM) để dự đoán xác suất lệnh BUY thành công (chạm Take-Profit trước Stop-Loss) trên dữ liệu chuỗi thời gian tài chính.

## 2. Thiết kế cốt lõi
- **Tránh Look-ahead Bias (Time-series Split):**
  - Không áp dụng shuffle/k-fold ngẫu nhiên.
  - Phân chia tuyến tính theo thời gian: 70% Train, 15% Validation (Early Stopping), 15% Test (Out-Of-Sample).
- **Cân bằng nhãn (Class Imbalance):**
  - Tự động tính toán tham số `scale_pos_weight = (N_0) / (N_1 + 1e-9)` theo tỷ lệ nhãn thực tế của tập Train.
- **Tối ưu hóa Hyperparameters (LightGBM):**
  - `objective="binary"`, `metric="auc"`, `boosting_type="gbdt"`.
  - `learning_rate=0.03`, `num_leaves=31`, `min_data_in_leaf=50`.
  - Subsampling: `feature_fraction=0.8`, `bagging_fraction=0.8`.
  - Cơ chế `early_stopping(stopping_rounds=50)` dựa trên tập Validation.
- **Đánh giá Out-Of-Sample:**
  - Báo cáo ROC-AUC, Precision, Recall, F1-Score, Accuracy theo các ngưỡng threshold xác suất.
  - Xếp hạng Top 10 chỉ báo kỹ thuật có mức độ đóng góp (Feature Importance) cao nhất.
- **Đóng gói Artifacts:**
  - Lưu trữ mô hình đã huấn luyện và danh sách tên features tại `models/lgbm_forex_model.pkl` bằng `joblib`.
