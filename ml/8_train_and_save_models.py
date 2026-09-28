"""
FinGuard AI — ОБУЧЕНИЕ моделей, запускается ОДИН РАЗ (не при каждом запросе!).

Результат: файлы pd_model.joblib и anomaly_model.joblib в папке models/.
После этого FastAPI просто ЗАГРУЖАЕТ эти файлы (joblib.load) и делает
predict() — без какого-либо переобучения.

Запускать заново нужно только если:
  - вы получили больше реальных данных о дефолтах (для PD-модели);
  - вы хотите пересчитать "нормальный" профиль транзакций (для anomaly-модели).
Для обычной работы сайта — запускать НЕ нужно, файлы .joblib уже готовы.
"""

import pandas as pd
import numpy as np
import joblib
import os
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import IsolationForest

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
MODELS = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODELS, exist_ok=True)

# =====================================================================
# МОДЕЛЬ 1: Probability of Default (PD) — логистическая регрессия
# =====================================================================
def train_pd_model():
    external_path = f"{DATA}/external_credit_dataset.csv"

    if os.path.exists(external_path):
        # -- Вариант А: обучаем на реальном публичном датасете (UCI/Kaggle) --
        df = pd.read_csv(external_path)
        target_col = "default payment next month"   # переименуйте под свой файл
        feature_cols = [c for c in df.columns if c not in (target_col, "ID")]
        X, y = df[feature_cols].fillna(0), df[target_col]
        print(f"Обучаем PD-модель на внешнем датасете: {len(df)} строк")
    else:
        # -- Вариант Б: fallback на собственных синтетических данных --
        fh = pd.read_csv(f"{DATA}/financial_health_scores.csv")
        an = pd.read_csv(f"{DATA}/anomaly_scores.csv")
        merged = fh.merge(an, on="company_id", how="left").fillna({"anomaly_score": 30})
        merged["label_high_risk"] = (merged["financial_score"] > 65).astype(int)
        feature_cols = ["financial_score", "anomaly_score"]
        X, y = merged[feature_cols], merged["label_high_risk"]
        if y.nunique() < 2:
            X = pd.concat([X, pd.DataFrame({"financial_score": [10, 90], "anomaly_score": [10, 90]})])
            y = pd.concat([y, pd.Series([0, 1])])
        print("Внешний датасет не найден — обучаем PD-модель в fallback-режиме")

    model = LogisticRegression(max_iter=1000).fit(X, y)

    # сохраняем МОДЕЛЬ + список фич вместе (важно: joblib.load потом должен знать,
    # в каком порядке подавать признаки на predict)
    joblib.dump({"model": model, "feature_cols": feature_cols}, f"{MODELS}/pd_model.joblib")
    print(f"Сохранено: {MODELS}/pd_model.joblib")


# =====================================================================
# МОДЕЛЬ 2: Anomaly Detection — Isolation Forest,
# обученная на ОБЩЕМ профиле "нормальных" транзакций по всем компаниям.
# Это компромисс: вместо персональной модели под каждую компанию (как было
# раньше) — одна общая модель, обученная на признаках, которые УЖЕ учитывают
# относительное отклонение (zscore, ratio_to_avg) — то есть она всё равно
# ловит "необычное для этой компании", просто веса модели теперь общие
# и не пересчитываются заново при каждом запросе.
# =====================================================================
def train_anomaly_model():
    txn = pd.read_csv(f"{DATA}/transactions.csv")
    txn["txn_timestamp"] = pd.to_datetime(txn["txn_timestamp"])

    feats = []
    for company_id, g in txn.groupby("company_id"):
        g = g.sort_values("txn_timestamp")
        hist_mean = g["amount"].mean()
        hist_std = g["amount"].std() or 1.0
        known_cps = set(g["counterparty_id"].value_counts().head(15).index)
        for _, r in g.iterrows():
            feats.append(dict(
                amount_zscore=(r["amount"] - hist_mean) / hist_std,
                ratio_to_avg=r["amount"] / hist_mean,
                is_new_counterparty=int(r["counterparty_id"] not in known_cps),
                unusual_hour=int(r["txn_timestamp"].hour < 6 or r["txn_timestamp"].hour > 22),
            ))
    features_df = pd.DataFrame(feats)
    feature_cols = ["amount_zscore", "ratio_to_avg", "is_new_counterparty", "unusual_hour"]

    model = IsolationForest(n_estimators=200, contamination=0.05, random_state=42)
    model.fit(features_df[feature_cols])

    joblib.dump({"model": model, "feature_cols": feature_cols}, f"{MODELS}/anomaly_model.joblib")
    print(f"Сохранено: {MODELS}/anomaly_model.joblib (обучено на {len(features_df)} транзакциях)")


if __name__ == "__main__":
    train_pd_model()
    train_anomaly_model()
    print("\nГотово. Теперь FastAPI должен только ЗАГРУЖАТЬ эти .joblib файлы, "
          "а не обучать модели заново.")
