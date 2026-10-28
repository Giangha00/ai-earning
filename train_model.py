"""
Module train_model.py
Hiện thực hóa CHƯƠNG 2, CHƯƠNG 4 & CHƯƠNG 5:
- Huấn luyện mô hình phân loại dự đoán xác suất (Confidence Score) với ngưỡng >= 0.75 (75%).
- Huấn luyện Gaussian HMM (3 States: Bullish, Bearish, High Volatility Chaos).
- Huấn luyện Isolation Forest để phát hiện dữ liệu bất thường Out-of-Distribution (OOD).
- Khởi tạo và lưu trữ đầy đủ trọng số chuẩn toán học theo Sổ tay thuật toán Bot AI.
"""

import logging
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score,
    classification_report,
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
        logging.info(f"Đang nạp dataset từ {self.dataset_path}...")
        df = pd.read_parquet(self.dataset_path)
        df = df.sort_values(by=["time"]).reset_index(drop=True)
        return df

    def prepare_data(self, df: pd.DataFrame):
        features = [col for col in df.columns if col not in self.ignore_cols]
        X = df[features]
        y = df["target"]

        logging.info(f"Tổng số features: {len(features)}")
        n = len(df)
        train_end = int(n * 0.70)
        val_end = int(n * 0.85)

        X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
        X_val, y_val = X.iloc[train_end:val_end], y.iloc[train_end:val_end]
        X_test, y_test = X.iloc[val_end:], y.iloc[val_end:]

        logging.info(f"Train: {len(X_train):,} | Val: {len(X_val):,} | Test (OOS): {len(X_test):,}")
        return X_train, y_train, X_val, y_val, X_test, y_test, features

    def train_classifier(self, X_train, y_train, X_val, y_val):
        """Huấn luyện mô hình phân loại dự đoán xác suất thắng."""
        logging.info("Huấn luyện mô hình LightGBM với tham số chuẩn hóa...")
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

        model = lgb.LGBMClassifier(**params, n_estimators=1000)
        callbacks = [
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.log_evaluation(period=100),
        ]

        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], callbacks=callbacks)
        logging.info(f"Huấn luyện hoàn tất! Best iteration: {model.best_iteration_}")
        return model

    def train_hmm(self, df: pd.DataFrame) -> MarketHMMRegimeDetector:
        """Huấn luyện Gaussian HMM tách 3 trạng thái thị trường (Chương 2.6)."""
        logging.info("Huấn luyện Gaussian HMM 3 trạng thái ẩn (Bullish, Bearish, High Volatility Chaos)...")
        returns = df["close"].pct_change().fillna(0).values
        hl_volatility = ((df["high"] - df["low"]) / df["close"]).fillna(0).values

        detector = MarketHMMRegimeDetector(n_components=3, random_state=42)
        detector.fit(returns, hl_volatility)
        return detector

    def train_ood_filter(self, X_train: pd.DataFrame, threshold: float = 0.75) -> OutOfDistributionFilter:
        """Huấn luyện Isolation Forest phát hiện dữ liệu lạ OOD (Chương 4.3)."""
        logging.info(f"Huấn luyện Isolation Forest OOD Filter với ngưỡng tự tin >= {threshold * 100:.1f}%...")
        ood_filter = OutOfDistributionFilter(contamination=0.05, confidence_threshold=threshold)
        ood_filter.fit(X_train.values)
        return ood_filter

    def evaluate(self, model, X_test, y_test, threshold: float = 0.75):
        """Đánh giá theo CHƯƠNG 4.3 & 5: Ngưỡng tự tin chuẩn >= 0.75."""
        logging.info(f"\n{'='*20} ĐÁNH GIÁ TRÊN TẬP TEST VỚI NGƯỠNG CONFIDENCE >= {threshold * 100:.1f}% {'='*20}")
        y_probs = model.predict_proba(X_test)[:, 1]
        y_pred = (y_probs >= threshold).astype(int)

        roc_auc = roc_auc_score(y_test, y_probs)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        accuracy = accuracy_score(y_test, y_pred)

        logging.info(f"Số lệnh kích hoạt với ngưỡng >= {threshold * 100:.1f}%: {int(np.sum(y_pred)):,} lệnh")
        logging.info(f"ROC-AUC Score:  {roc_auc:.4f}")
        logging.info(f"Precision:      {precision * 100:.2f}% (Tỷ lệ thắng thực tế trên các lệnh bot chọn)")
        logging.info(f"Recall:         {recall * 100:.2f}%")
        logging.info(f"F1-Score:       {f1:.4f}")
        logging.info(f"Accuracy:       {accuracy * 100:.2f}%")

        return y_probs

    def save_full_pipeline(
        self,
        model,
        features: List[str],
        hmm_detector: MarketHMMRegimeDetector,
        ood_filter: OutOfDistributionFilter,
    ):
        """Lưu toàn bộ pipeline AI bao gồm Model + Features + HMM + OOD Filter."""
        model_path = self.models_dir / "lgbm_forex_model.pkl"
        payload = {
            "model": model,
            "features": features,
            "hmm_detector": hmm_detector,
            "ood_filter": ood_filter,
            "confidence_threshold": 0.75,
            "version": "2.0.0_DeepQuant",
        }
        joblib.dump(payload, model_path)
        logging.info(f"Đã lưu toàn bộ pipeline AI (Model + HMM + OOD) vào: {model_path}")


def main():
    dataset_file = BASE_DIR / "data" / "processed_dataset.parquet"
    if not dataset_file.exists():
        logging.error(f"Không tìm thấy file {dataset_file}.")
        return

    trainer = ModelTrainer(dataset_path=dataset_file)
    df = trainer.load_data()
    X_train, y_train, X_val, y_val, X_test, y_test, features = trainer.prepare_data(df)

    # 1. Huấn luyện Classifier
    model = trainer.train_classifier(X_train, y_train, X_val, y_val)

    # 2. Huấn luyện HMM Regime Detector
    hmm_detector = trainer.train_hmm(df)

    # 3. Huấn luyện Isolation Forest OOD Filter
    ood_filter = trainer.train_ood_filter(X_train, threshold=0.75)

    # 4. Đánh giá với ngưỡng chuẩn >= 0.75
    trainer.evaluate(model, X_test, y_test, threshold=0.75)

    # 5. Lưu toàn bộ pipeline
    trainer.save_full_pipeline(model, features, hmm_detector, ood_filter)


if __name__ == "__main__":
    main()
