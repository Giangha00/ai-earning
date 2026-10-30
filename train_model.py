"""
Module train_model.py
Hiện thực hóa Bước 4 (HƯỚNG DẪN THIẾT LẬP TRAINING POOL DATASET) & CHƯƠNG 2, 4, 5:
- Đọc trực tiếp từ Multi-Dataset Training Pool (data/training_pool.csv hoặc data/processed_dataset.parquet)
  đã hợp nhất:
  1. HuggingFace Dataset 1: arvind7754/btc-candlestick-dataset (13,081 mẫu nến BTC)
  2. HuggingFace Dataset 2: tripolskypetr/tradingview-ideas-signals (51,963 ideas + 22,384 nến M5)
  3. MT5 / Exness Historical Candlesticks (20,000 nến)
- Chia tỷ lệ chuẩn: Train (70%), Validation (15%), Test (15%).
- Huấn luyện toàn diện 5 mô hình AI:
  1. LightGBM Classifier (Gradient Boosting)
  2. Vectorized Logistic Regression (Sigmoid + Binary Cross-Entropy)
  3. Deep Multi-Layer Perceptron (L2 Regularization + Inverted Dropout)
  4. Gaussian Hidden Markov Model (3 Market Regimes: Bullish, Bearish, High Volatility Chaos)
  5. Isolation Forest OOD Filter (Out-of-Distribution Anomaly Detection)
- Đánh giá với ngưỡng tự tin Confidence Score >= 0.75 (75%) và kiểm định Precision >= 70%.
- Xuất đồng thời models/model.pkl và models/lgbm_forex_model.pkl.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

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
    DeepMLPNetwork,
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
            "time",
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
            "spread",
            "real_volume",
            "target",
        ]

    def load_data(self) -> pd.DataFrame:
        logging.info(f"Đang nạp Multi-Dataset Training Pool từ {self.dataset_path}...")
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

        logging.info(f"Tổng số dòng trong Training Pool: {len(df):,} | Số features: {len(features)} -> {features}")
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
        logging.info("Huấn luyện mô hình AI LightGBM Gradient Boosting trên Multi-Dataset Training Pool...")

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
        logging.info(f"Huấn luyện LightGBM hoàn tất! Best iteration: {model.best_iteration_}")
        return model

    def train_logistic_baseline(self, X_train: pd.DataFrame, y_train: pd.Series) -> VectorizedLogisticRegression:
        """Huấn luyện Vectorized Logistic Regression với Sigmoid (Chương 2.1 - 2.4)."""
        logging.info("Huấn luyện Vectorized Logistic Regression (Sigmoid + Binary Cross-Entropy)...")
        logreg = VectorizedLogisticRegression(learning_rate=0.05, iterations=300)
        X_vals = X_train.values
        X_norm = (X_vals - X_vals.mean(axis=0)) / (X_vals.std(axis=0) + 1e-8)
        logreg.fit(X_norm.T, y_train.values.reshape(1, -1))
        return logreg

    def train_deep_mlp(self, X_train: pd.DataFrame, y_train: pd.Series, epochs: int = 120) -> DeepMLPNetwork:
        """Huấn luyện mạng nơ-ron sâu Deep MLP với L2 Regularization & Inverted Dropout (Chương 2.5 & 4.1-4.2)."""
        logging.info("Huấn luyện Deep MLP Network (L2 Regularization lambda=0.01 & Inverted Dropout keep_prob=0.8)...")
        X_vals = X_train.values
        X_norm = ((X_vals - X_vals.mean(axis=0)) / (X_vals.std(axis=0) + 1e-8)).T
        Y_mat = y_train.values.reshape(1, -1).astype(float)

        mlp = DeepMLPNetwork(
            layer_dims=[X_norm.shape[0], 32, 16, 1],
            learning_rate=0.02,
            l2_lambda=0.01,
            keep_prob=0.8,
        )
        for _ in range(epochs):
            AL, caches = mlp.forward_propagation(X_norm, training=True)
            grads = mlp.backward_propagation_with_l2(AL, Y_mat, caches)
            mlp.update_parameters(grads)
        return mlp

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
        deep_mlp: DeepMLPNetwork,
        features: List[str],
        hmm_detector: MarketHMMRegimeDetector,
        ood_filter: OutOfDistributionFilter,
        metrics: Dict[str, float],
        total_rows: int,
    ):
        """Lưu toàn bộ pipeline AI vào cả models/model.pkl và models/lgbm_forex_model.pkl."""
        lgbm_path = self.models_dir / "lgbm_forex_model.pkl"
        std_model_path = self.models_dir / "model.pkl"
        meta_path = BASE_DIR / "data" / "hf_datasets" / "pool_metadata.json"

        pool_metadata: Dict[str, Any] = {}
        if meta_path.exists():
            try:
                pool_metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pool_metadata = {}

        pool_metadata["last_trained_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pool_metadata["test_metrics"] = {
            "roc_auc": round(metrics["roc_auc"], 4),
            "precision_pct": round(metrics["precision"] * 100, 2),
            "recall_pct": round(metrics["recall"] * 100, 2),
            "f1_score": round(metrics["f1"], 4),
            "accuracy_pct": round(metrics["accuracy"] * 100, 2),
            "trades_triggered": metrics["trades_triggered"],
        }
        if meta_path.parent.exists():
            meta_path.write_text(json.dumps(pool_metadata, indent=2, ensure_ascii=False), encoding="utf-8")

        payload = {
            "model": model,
            "logistic_regression": logreg_model,
            "deep_mlp": deep_mlp,
            "features": features,
            "hmm_detector": hmm_detector,
            "ood_filter": ood_filter,
            "confidence_threshold": 0.75,
            "metrics": metrics,
            "total_pool_rows": total_rows,
            "datasets_used": [
                "arvind7754/btc-candlestick-dataset",
                "tripolskypetr/tradingview-ideas-signals",
                "jukik45/mt5_eurusd",
                "akashkumar5/EURUSD-15M-RegimeBench",
                "vichetkao/xauusd_dataset_2026",
                "MT5_EXNESS_EURUSD",
            ],
            "pool_metadata": pool_metadata,
            "version": "2.3.0_HF_6Dataset_MegaPool_RR1_2",
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

    dataset_file = parquet_pool if parquet_pool.exists() else csv_pool
    if not dataset_file.exists():
        logging.error(f"Không tìm thấy file {dataset_file}.")
        return

    trainer = ModelTrainer(dataset_path=dataset_file)
    df = trainer.load_data()
    X_train, y_train, X_val, y_val, X_test, y_test, features = trainer.prepare_data(df)

    # 1. Huấn luyện Classifier chính LightGBM, Logistic Regression & Deep MLP
    model = trainer.train_classifier(X_train, y_train, X_val, y_val)
    logreg_model = trainer.train_logistic_baseline(X_train, y_train)
    deep_mlp = trainer.train_deep_mlp(X_train, y_train)

    # 2. Huấn luyện HMM Regime Detector
    hmm_detector = trainer.train_hmm(df)

    # 3. Huấn luyện Isolation Forest OOD Filter
    ood_filter = trainer.train_ood_filter(X_train, threshold=0.75)

    # 4. Đánh giá với ngưỡng chuẩn >= 0.75 và kiểm tra Precision >= 70%
    metrics = trainer.evaluate(model, X_test, y_test, threshold=0.75)

    # 5. Lưu toàn bộ pipeline ra model.pkl & lgbm_forex_model.pkl
    trainer.save_full_pipeline(
        model=model,
        logreg_model=logreg_model,
        deep_mlp=deep_mlp,
        features=features,
        hmm_detector=hmm_detector,
        ood_filter=ood_filter,
        metrics=metrics,
        total_rows=len(df),
    )


if __name__ == "__main__":
    main()
