"""
Module train_model.py
Hiện thực hóa Bước 4 (HƯỚNG DẪN THIẾT LẬP TRAINING POOL DATASET) & CHƯƠNG 2, 4, 5:
- Đọc trực tiếp từ data/training_pool.csv (hoặc fallback data/processed_dataset.parquet).
- Chia tỷ lệ chuẩn: Train (70%), Validation (15%), Test (15%).
- Huấn luyện mô hình AI (LightGBM / Logistic Regression + Gaussian HMM + Isolation Forest OOD Filter)
  với ngưỡng tự tin Confidence Score >= 0.75 (75%) và kiểm định Precision >= 70%.
- Xuất đồng thời models/model.pkl và models/lgbm_forex_model.pkl.
"""

import logging
from typing import List, Dict, Any
from pathlib import Path
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from config import BASE_DIR
from ai_math_models import (
    VectorizedLogisticRegression,
    MarketHMMRegimeDetector,
    OutOfDistributionFilter,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")


class ModelTrainer:
    def __init__(self, dataset_path: Path, models_dir: str = "models"):
        self.dataset_path = dataset_path
        self.models_dir = BASE_DIR / models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self.ignore_cols = [
            "time", "open", "high", "low", "close", "tick_volume",
            "spread", "real_volume", "target"
        ]

    def load_data(self) -> pd.DataFrame:
        logging.info(f"Đang nạp Training Pool dataset từ {self.dataset_path}...")
        if str(self.dataset_path).endswith(".csv"):
            df = pd.read_csv(self.dataset_path)
        else:
            df = pd.read_parquet(self.dataset_path)
        df = df.sort_values(by=["time"]).reset_index(drop=True)
        return df

    def prepare_data(self, df: pd.DataFrame):
        features = [col for col in df.columns if col not in self.ignore_cols]
        X = df[features]
        y = df["target"].astype(int)

        logging.info(f"Tổng số features trong Training Pool: {len(features)} -> {features}")
        n = len(df)
        train_end = int(n * 0.70)
        val_end = int(n * 0.85)

        X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
        X_val, y_val = X.iloc[train_end:val_end], y.iloc[train_end:val_end]
        X_test, y_test = X.iloc[val_end:], y.iloc[val_end:]

        logging.info(
            f"Chia tỷ lệ 70/15/15 -> Train: {len(X_train):,} (70%) | Val: {len(X_val):,} (15%) | Test (OOS): {len(X_test):,} (15%)"
        )
        return X_train, y_train, X_val, y_val, X_test, y_test, features

    def train_classifier(self, X_train, y_train, X_val, y_val):
        """Huấn luyện mô hình phân loại dự đoán xác suất thắng (Confidence Score)."""
        logging.info("Huấn luyện mô hình AI Gradient Boosting & Logistic Regression trên Training Pool...")

        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "boosting_type": "gbdt",
            "learning_rate": 0.03,
            "num_leaves": 31,
            "max_depth": 6,
            "min_data_in_leaf": 40,
            "feature_fraction": 0.85,
            "bagging_fraction": 0.85,
            "bagging_freq": 1,
            "random_state": 42,
            "n_jobs": -1,
            "verbose": -1,
        }

        model = lgb.LGBMClassifier(**params, n_estimators=600)
        callbacks = [
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.log_evaluation(period=100),
        ]

        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], callbacks=callbacks)
        logging.info(f"Huấn luyện hoàn tất! Best iteration: {model.best_iteration_}")
        return model

    def train_logistic_baseline(self, X_train: pd.DataFrame, y_train: pd.Series) -> VectorizedLogisticRegression:
        """Huấn luyện Vectorized Logistic Regression với Sigmoid (Bước 4)."""
        logreg = VectorizedLogisticRegression(learning_rate=0.05, iterations=300)
        X_vals = X_train.values
        X_norm = (X_vals - X_vals.mean(axis=0)) / (X_vals.std(axis=0) + 1e-8)
        logreg.fit(X_norm.T, y_train.values.reshape(1, -1))
        return logreg

    def train_hmm(self, df: pd.DataFrame) -> MarketHMMRegimeDetector:
        """Huấn luyện Gaussian HMM tách 3 trạng thái thị trường (Bullish, Bearish, High Volatility Chaos)."""
        logging.info("Huấn luyện Gaussian HMM 3 trạng thái ẩn (Bullish, Bearish, High Volatility Chaos)...")
        returns = df["close"].pct_change().fillna(0).values
        hl_volatility = ((df["high"] - df["low"]) / df["close"]).fillna(0).values

        detector = MarketHMMRegimeDetector(n_components=3, random_state=42)
        detector.fit(returns, hl_volatility)
        return detector

    def train_ood_filter(self, X_train: pd.DataFrame, threshold: float = 0.75) -> OutOfDistributionFilter:
        """Huấn luyện Isolation Forest phát hiện dữ liệu lạ OOD (Chương 1.2 & 4.3)."""
        logging.info(f"Huấn luyện Isolation Forest OOD Filter với ngưỡng tự tin >= {threshold * 100:.1f}%...")
        ood_filter = OutOfDistributionFilter(contamination=0.05, confidence_threshold=threshold)
        ood_filter.fit(X_train.values)
        return ood_filter

    def evaluate(self, model, X_test, y_test, threshold: float = 0.75) -> Dict[str, float]:
        """Đánh giá theo Bước 4: Ngưỡng tự tin >= 0.75 & Kiểm định Precision >= 70%."""
        logging.info(f"\n{'='*20} ĐÁNH GIÁ TRÊN TẬP TEST VỚI NGƯỠNG CONFIDENCE >= {threshold * 100:.1f}% {'='*20}")
        y_probs = model.predict_proba(X_test)[:, 1]
        y_pred = (y_probs >= threshold).astype(int)

        roc_auc = roc_auc_score(y_test, y_probs) if len(np.unique(y_test)) > 1 else 0.5
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        accuracy = accuracy_score(y_test, y_pred)

        logging.info(f"Số lệnh kích hoạt với ngưỡng >= {threshold * 100:.1f}%: {int(np.sum(y_pred)):,} lệnh")
        logging.info(f"ROC-AUC Score:  {roc_auc:.4f}")
        logging.info(f"Precision:      {precision * 100:.2f}% (Yêu cầu Bước 4: >= 70.00%)")
        logging.info(f"Recall:         {recall * 100:.2f}%")
        logging.info(f"F1-Score:       {f1:.4f}")
        logging.info(f"Accuracy:       {accuracy * 100:.2f}%")

        return {
            "roc_auc": float(roc_auc),
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            "accuracy": float(accuracy),
            "trades_triggered": int(np.sum(y_pred)),
        }

    def save_full_pipeline(
        self,
        model,
        logreg_model: VectorizedLogisticRegression,
        features: List[str],
        hmm_detector: MarketHMMRegimeDetector,
        ood_filter: OutOfDistributionFilter,
        metrics: Dict[str, float],
    ):
        """Lưu toàn bộ pipeline AI vào cả models/model.pkl và models/lgbm_forex_model.pkl."""
        lgbm_path = self.models_dir / "lgbm_forex_model.pkl"
        std_model_path = self.models_dir / "model.pkl"

        payload = {
            "model": model,
            "logistic_regression": logreg_model,
            "features": features,
            "hmm_detector": hmm_detector,
            "ood_filter": ood_filter,
            "confidence_threshold": 0.75,
            "metrics": metrics,
            "version": "2.1.0_TrainingPool_RR1_2",
        }
        joblib.dump(payload, lgbm_path)
        joblib.dump(payload, std_model_path)

        if metrics.get("precision", 0.0) >= 0.70:
            logging.info(
                f"✅ ĐẠT CHUẨN PRECISION ({metrics['precision'] * 100:.2f}% >= 70%)! "
                f"Đã xuất file model tại: {std_model_path} & {lgbm_path}"
            )
        else:
            logging.info(f"Đã lưu toàn bộ pipeline AI vào: {std_model_path} & {lgbm_path}")


def main():
    csv_pool = BASE_DIR / "data" / "training_pool.csv"
    parquet_pool = BASE_DIR / "data" / "processed_dataset.parquet"

    if not csv_pool.exists():
        logging.info("Chưa tìm thấy data/training_pool.csv, tự động khởi tạo từ create_training_pool.py...")
        from create_training_pool import fetch_and_label_data
        fetch_and_label_data()

    dataset_file = csv_pool if csv_pool.exists() else parquet_pool
    if not dataset_file.exists():
        logging.error(f"Không tìm thấy file {dataset_file}.")
        return

    trainer = ModelTrainer(dataset_path=dataset_file)
    df = trainer.load_data()
    X_train, y_train, X_val, y_val, X_test, y_test, features = trainer.prepare_data(df)

    # 1. Huấn luyện Classifier chính & Logistic Regression
    model = trainer.train_classifier(X_train, y_train, X_val, y_val)
    logreg_model = trainer.train_logistic_baseline(X_train, y_train)

    # 2. Huấn luyện HMM Regime Detector
    hmm_detector = trainer.train_hmm(df)

    # 3. Huấn luyện Isolation Forest OOD Filter
    ood_filter = trainer.train_ood_filter(X_train, threshold=0.75)

    # 4. Đánh giá với ngưỡng chuẩn >= 0.75 và kiểm tra Precision >= 70%
    metrics = trainer.evaluate(model, X_test, y_test, threshold=0.75)

    # 5. Lưu toàn bộ pipeline ra model.pkl & lgbm_forex_model.pkl
    trainer.save_full_pipeline(model, logreg_model, features, hmm_detector, ood_filter, metrics)


if __name__ == "__main__":
    main()
