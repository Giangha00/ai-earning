import logging
from pathlib import Path
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from config import BASE_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")


class ModelTrainer:
    def __init__(self, dataset_path: Path, models_dir: str = "models"):
        self.dataset_path = dataset_path
        self.models_dir = BASE_DIR / models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)

        # Danh sách các cột KHÔNG dùng làm feature đầu vào
        self.ignore_cols = [
            "time", "open", "high", "low", "close", "tick_volume", 
            "spread", "real_volume", "target"
        ]

    def load_data(self) -> pd.DataFrame:
        logging.info(f"Đang nạp dataset từ {self.dataset_path}...")
        df = pd.read_parquet(self.dataset_path)
        # Đảm bảo sắp xếp chuẩn theo thời gian
        df = df.sort_values(by=["time"]).reset_index(drop=True)
        return df

    def prepare_data(self, df: pd.DataFrame):
        """Tách Features (X), Target (y) và phân chia theo Time-series Split."""
        features = [col for col in df.columns if col not in self.ignore_cols]
        X = df[features]
        y = df["target"]

        logging.info(f"Tổng số features đưa vào huấn luyện: {len(features)}")
        logging.info(f"Danh sách features: {features}")

        n = len(df)
        train_end = int(n * 0.70)
        val_end = int(n * 0.85)

        # 1. Tập Train (70% đầu)
        X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
        # 2. Tập Validation (15% tiếp theo để Early Stopping)
        X_val, y_val = X.iloc[train_end:val_end], y.iloc[train_end:val_end]
        # 3. Tập Test OOS - Out Of Sample (15% cuối cùng để đánh giá khách quan)
        X_test, y_test = X.iloc[val_end:], y.iloc[val_end:]

        logging.info(f"Kích thước tập Train:      {len(X_train):,} mẫu")
        logging.info(f"Kích thước tập Validation: {len(X_val):,} mẫu")
        logging.info(f"Kích thước tập Test (OOS): {len(X_test):,} mẫu")

        return X_train, y_train, X_val, y_val, X_test, y_test, features

    def train(self, X_train, y_train, X_val, y_val):
        """Huấn luyện mô hình LightGBM với cơ chế Early Stopping."""
        logging.info("Bắt đầu huấn luyện mô hình LightGBM...")

        # Tính tỷ lệ mất cân bằng nhãn (class imbalance)
        scale_pos_weight = (len(y_train) - sum(y_train)) / (sum(y_train) + 1e-9)

        params = {
            "objective": "binary",
            "metric": "auc",
            "boosting_type": "gbdt",
            "learning_rate": 0.03,
            "num_leaves": 31,
            "max_depth": -1,
            "min_data_in_leaf": 50,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "scale_pos_weight": scale_pos_weight,
            "random_state": 42,
            "n_jobs": -1,
            "verbose": -1,
        }

        # Khởi tạo mô hình
        model = lgb.LGBMClassifier(**params, n_estimators=1000)

        # Huấn luyện với early stopping (dừng nếu sau 50 vòng không cải thiện AUC trên tập val)
        callbacks = [
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.log_evaluation(period=100)
        ]

        model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            callbacks=callbacks
        )

        logging.info(f"Huấn luyện hoàn tất! Vòng lặp tối ưu nhất: {model.best_iteration_}")
        return model

    def evaluate(self, model, X_test, y_test, threshold: float = 0.55):
        """Đánh giá mô hình trên tập Test (dữ liệu tương lai mà mô hình chưa từng thấy)."""
        logging.info(f"\n{'='*20} ĐÁNH GIÁ TRÊN TẬP TEST (OUT-OF-SAMPLE) {'='*20}")

        # Lấy xác suất dự đoán nhãn 1 (Buy thắng)
        y_probs = model.predict_proba(X_test)[:, 1]
        
        # Áp dụng ngưỡng xác suất (Threshold):
        # Chỉ vào lệnh khi AI tin tưởng xác suất thắng >= threshold
        y_pred = (y_probs >= threshold).astype(int)

        roc_auc = roc_auc_score(y_test, y_probs)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        accuracy = accuracy_score(y_test, y_pred)

        logging.info(f"Ngưỡng kích hoạt lệnh (Threshold): {threshold * 100:.1f}%")
        logging.info(f"ROC-AUC Score:  {roc_auc:.4f}")
        logging.info(f"Precision:      {precision * 100:.2f}% (Trong các lệnh bot đánh, bao nhiêu % thực sự thắng)")
        logging.info(f"Recall:         {recall * 100:.2f}% (Tỷ lệ bắt được cơ hội thắng trên toàn thị trường)")
        logging.info(f"F1-Score:       {f1:.4f}")
        logging.info(f"Accuracy:       {accuracy * 100:.2f}%")

        print("\nChi tiết Classification Report:")
        print(classification_report(y_test, y_pred, digits=4, zero_division=0))

        # Hiển thị Top 10 Features quan trọng nhất
        importance_df = pd.DataFrame({
            "feature": X_test.columns,
            "importance": model.feature_importances_
        }).sort_values(by="importance", ascending=False)

        print("\nTop 10 chỉ báo/features ảnh hưởng nhiều nhất đến quyết định của AI:")
        print(importance_df.head(10).to_string(index=False))

        return y_probs

    def save(self, model, features):
        """Lưu model và danh sách features vào file."""
        model_path = self.models_dir / "lgbm_forex_model.pkl"
        payload = {
            "model": model,
            "features": features
        }
        joblib.dump(payload, model_path)
        logging.info(f"Đã lưu mô hình thành công vào: {model_path}")


def main():
    dataset_file = BASE_DIR / "data" / "processed_dataset.parquet"
    if not dataset_file.exists():
        logging.error(f"Không tìm thấy file {dataset_file}. Hãy chạy feature_engineering.py trước.")
        return

    trainer = ModelTrainer(dataset_path=dataset_file)
    df = trainer.load_data()
    X_train, y_train, X_val, y_val, X_test, y_test, features = trainer.prepare_data(df)

    model = trainer.train(X_train, y_train, X_val, y_val)
    
    # Đánh giá với ngưỡng xác suất vào lệnh 0.55 (chỉ đánh khi AI tự tin trên 55%)
    trainer.evaluate(model, X_test, y_test, threshold=0.55)
    
    # Lưu mô hình
    trainer.save(model, features)


if __name__ == "__main__":
    main()
