#!/usr/bin/env python3
"""
train_signal_meta_model.py
Huấn luyện Mô hình AI Meta-Evaluator từ dữ liệu MQL5 MT5 Signals
(được tạo từ mql5_signal_crawler.py tại data/mql5_signals/).

Mô hình học máy này đảm nhận vai trò:
1. Meta-Strategy Classifier: Đánh giá xác suất một chiến lược/tín hiệu có chất lượng cao (Pro Grade)
   dựa trên các chỉ số rủi ro/lợi nhuận (PF, Drawdown, Calmar, Recovery, Win Rate).
2. Profit Factor Regressor: Dự báo hệ số sinh lời kỳ vọng (Expected Profit Factor).
3. Feature Importance Analysis: Phân tích các đặc trưng quan trọng nhất dẫn đến thành công dài hạn.
4. Xuất mô hình vào models/mql5_signal_meta_model.pkl để tích hợp vào AI Trading Engine.
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from config import BASE_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("train_signal_meta_model")

DATASET_PARQUET = BASE_DIR / "data" / "mql5_signals" / "mql5_signals_ai_features.parquet"
DATASET_CSV = BASE_DIR / "data" / "mql5_signals" / "mql5_signals_ai_features.csv"
MODELS_DIR = BASE_DIR / "models"
MODEL_OUTPUT_PATH = MODELS_DIR / "mql5_signal_meta_model.pkl"

FEATURE_COLUMNS: List[str] = [
    "growth_pct",
    "algo_trading_pct",
    "weeks",
    "trading_days",
    "trades_per_week",
    "avg_holding_time_hours",
    "leverage_ratio",
    "trades_count",
    "profit_trades_pct",
    "loss_trades_pct",
    "sharpe_ratio",
    "trading_activity_pct",
    "max_deposit_load_pct",
    "recovery_factor",
    "long_trades_pct",
    "short_trades_pct",
    "expected_payoff_usd",
    "monthly_growth_pct",
    "annual_forecast_pct",
    "drawdown_maximal_pct",
    "drawdown_rel_balance_pct",
    "drawdown_rel_equity_pct",
    "payoff_ratio",
    "win_loss_ratio",
    "calmar_ratio",
    "long_dominance_ratio",
    "consecutive_resilience",
    "market_exposure_ratio",
    "growth_per_week",
]


class MQL5SignalMetaTrainer:
    def __init__(self, data_path: Path = DATASET_PARQUET):
        self.data_path = data_path
        self.models_dir = MODELS_DIR
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def load_dataset(self) -> pd.DataFrame:
        if self.data_path.exists():
            logger.info("Đang nạp tập dữ liệu đặc trưng từ %s...", self.data_path)
            if str(self.data_path).endswith(".parquet"):
                df = pd.read_parquet(self.data_path)
            else:
                df = pd.read_csv(self.data_path)
        elif DATASET_CSV.exists():
            logger.info("Nạp từ CSV thay thế: %s...", DATASET_CSV)
            df = pd.read_csv(DATASET_CSV)
        else:
            raise FileNotFoundError(
                f"Không tìm thấy tập dữ liệu tại {self.data_path} hoặc {DATASET_CSV}. "
                f"Vui lòng chạy 'python mql5_signal_crawler.py' trước!"
            )
        logger.info("Tập dữ liệu đã nạp: %d mẫu, %d cột.", len(df), len(df.columns))
        return df

    def train_models(self, df: pd.DataFrame) -> Dict[str, Any]:
        # Lọc các cột đặc trưng khả dụng
        available_features = [c for c in FEATURE_COLUMNS if c in df.columns]
        X = df[available_features].fillna(0.0)
        y_cls = df["is_high_quality"].astype(int)
        y_reg = df["target_profit_factor"].fillna(1.0)

        logger.info("Số đặc trưng đầu vào (Features X): %d", len(available_features))
        logger.info("Phân phối nhãn phân loại is_high_quality: %s", dict(y_cls.value_counts()))

        # Chia dữ liệu Train / Test (80% / 20%)
        X_train, X_test, y_train_cls, y_test_cls, y_train_reg, y_test_reg = train_test_split(
            X, y_cls, y_reg, test_size=0.20, random_state=42, stratify=y_cls if y_cls.nunique() > 1 else None
        )

        logger.info("Tập huấn luyện: %d mẫu | Tập kiểm thử (Test): %d mẫu.", len(X_train), len(X_test))

        # 1. Huấn luyện Meta-Classifier (LightGBM)
        logger.info("Đang huấn luyện LightGBM Meta-Classifier...")
        clf = lgb.LGBMClassifier(
            objective="binary",
            n_estimators=100,
            learning_rate=0.05,
            num_leaves=15,
            random_state=42,
            verbose=-1,
        )
        clf.fit(X_train, y_train_cls)

        # Đánh giá phân loại
        y_pred_cls = clf.predict(X_test)
        y_prob_cls = clf.predict_proba(X_test)[:, 1] if hasattr(clf, "predict_proba") else y_pred_cls

        acc = accuracy_score(y_test_cls, y_pred_cls)
        prec = precision_score(y_test_cls, y_pred_cls, zero_division=0)
        rec = recall_score(y_test_cls, y_pred_cls, zero_division=0)
        f1 = f1_score(y_test_cls, y_pred_cls, zero_division=0)
        try:
            auc = roc_auc_score(y_test_cls, y_prob_cls)
        except Exception:
            auc = 0.5

        logger.info(
            "--- KẾT QUẢ ĐÁNH GIÁ PHÂN LOẠI (CLASSIFIER) ---\n"
            "  * Accuracy : %.2f%%\n"
            "  * Precision: %.2f%%\n"
            "  * Recall   : %.2f%%\n"
            "  * F1-Score : %.4f\n"
            "  * ROC-AUC  : %.4f",
            acc * 100, prec * 100, rec * 100, f1, auc
        )

        # 2. Huấn luyện Profit Factor Regressor (RandomForest)
        logger.info("Đang huấn luyện Random Forest Profit Factor Regressor...")
        reg = RandomForestRegressor(n_estimators=100, max_depth=6, random_state=42)
        reg.fit(X_train, y_train_reg)
        y_pred_reg = reg.predict(X_test)

        mse = mean_squared_error(y_test_reg, y_pred_reg)
        r2 = r2_score(y_test_reg, y_pred_reg)
        logger.info(
            "--- KẾT QUẢ DỰ BÁO LỢI NHUẬN (REGRESSOR) ---\n"
            "  * MSE: %.4f | R2 Score: %.4f",
            mse, r2
        )

        # 3. Phân tích Độ quan trọng của các Đặc trưng (Feature Importance)
        importances = clf.feature_importances_
        feat_imp = sorted(zip(available_features, importances), key=lambda x: x[1], reverse=True)
        logger.info("Top 7 Đặc trưng quyết định chất lượng chiến lược MT5:")
        for feat, imp in feat_imp[:7]:
            logger.info("  - %-25s : %d", feat, imp)

        # 4. Đóng gói mô hình
        model_package = {
            "classifier": clf,
            "regressor": reg,
            "features": available_features,
            "metrics": {
                "accuracy": acc,
                "precision": prec,
                "recall": rec,
                "f1_score": f1,
                "roc_auc": auc,
                "regressor_r2": r2,
            },
            "top_features": feat_imp[:10],
            "trained_at": datetime.now().isoformat(),
            "samples_count": len(df),
        }

        joblib.dump(model_package, MODEL_OUTPUT_PATH)
        logger.info("Đã lưu gói mô hình Meta-AI vào: %s (Kích thước: %.1f KB)", MODEL_OUTPUT_PATH, MODEL_OUTPUT_PATH.stat().st_size / 1024.0)
        return model_package


def main():
    parser = argparse.ArgumentParser(description="Train MQL5 Signal Meta-Evaluator AI Model")
    parser.add_argument(
        "--data-path",
        type=str,
        default=str(DATASET_PARQUET),
        help=f"Đường dẫn đến file dataset (mặc định: {DATASET_PARQUET})",
    )
    args = parser.parse_args()

    trainer = MQL5SignalMetaTrainer(data_path=Path(args.data_path))
    df = trainer.load_dataset()
    trainer.train_models(df)


if __name__ == "__main__":
    main()

