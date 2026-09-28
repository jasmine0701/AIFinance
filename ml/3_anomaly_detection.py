"""
FinGuard AI — Шаг 3: модуль Transaction Anomaly Detection (Stage 2).
Isolation Forest поверх транзакционных признаков, посчитанных ПО КАЖДОЙ компании.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
import os

DATA = os.path.join(os.path.dirname(__file__), "..", "data")

def build_features(txn_df: pd.DataFrame) -> pd.DataFrame:
    txn_df = txn_df.copy()
    txn_df["txn_timestamp"] = pd.to_datetime(txn_df["txn_timestamp"])

    feats = []
    for company_id, g in txn_df.groupby("company_id"):
        g = g.sort_values("txn_timestamp")
        hist_mean = g["amount"].mean()
        hist_std = g["amount"].std() or 1.0
        known_cps = set(g["counterparty_id"].value_counts().head(15).index)  # "обычные" контрагенты

        for _, r in g.iterrows():
            amount_zscore = (r["amount"] - hist_mean) / hist_std
            ratio_to_avg = r["amount"] / hist_mean
            is_new_counterparty = int(r["counterparty_id"] not in known_cps)
            unusual_hour = int(r["txn_timestamp"].hour < 6 or r["txn_timestamp"].hour > 22)
            feats.append(dict(
                company_id=company_id, txn_id=r["txn_id"],
                amount_zscore=amount_zscore, ratio_to_avg=ratio_to_avg,
                is_new_counterparty=is_new_counterparty, unusual_hour=unusual_hour,
                amount=r["amount"],
            ))
    return pd.DataFrame(feats)

def detect_anomalies(features: pd.DataFrame) -> pd.DataFrame:
    X_cols = ["amount_zscore", "ratio_to_avg", "is_new_counterparty", "unusual_hour"]
    model = IsolationForest(n_estimators=200, contamination=0.05, random_state=42)
    features = features.copy()
    features["anomaly_raw"] = model.fit_predict(features[X_cols])          # -1 = аномалия
    features["anomaly_decision"] = model.decision_function(features[X_cols])  # чем ниже — тем аномальнее

    # переводим decision_function в понятный score 0..100 (100 = максимально подозрительно)
    d = features["anomaly_decision"]
    features["anomaly_score_txn"] = ((d.max() - d) / (d.max() - d.min()) * 100).round(1)
    return features

def company_level_summary(features: pd.DataFrame, txn_df: pd.DataFrame) -> pd.DataFrame:
    """Агрегируем до уровня компании: берём максимально подозрительные транзакции как 'причины'."""
    rows = []
    for company_id, g in features.groupby("company_id"):
        g_sorted = g.sort_values("anomaly_score_txn", ascending=False)
        top_txn = g_sorted.head(3)
        reasons = []
        for _, t in top_txn.iterrows():
            if t["ratio_to_avg"] > 3:
                reasons.append(f"сумма транзакции в {t['ratio_to_avg']:.1f}x выше исторического среднего")
            if t["is_new_counterparty"]:
                reasons.append("новый контрагент")
            if t["unusual_hour"]:
                reasons.append("нетипичное время транзакции")
        company_score = g_sorted["anomaly_score_txn"].head(5).mean()  # среднее по топ-5 подозрительных
        rows.append(dict(company_id=company_id,
                          anomaly_score=round(company_score, 1),
                          top_factors_anomaly=list(dict.fromkeys(reasons))[:3]))  # без дублей
    return pd.DataFrame(rows)

if __name__ == "__main__":
    txn = pd.read_csv(f"{DATA}/transactions.csv")
    feats = build_features(txn)
    feats = detect_anomalies(feats)
    summary = company_level_summary(feats, txn)
    summary.to_csv(f"{DATA}/anomaly_scores.csv", index=False)
    print(summary)
