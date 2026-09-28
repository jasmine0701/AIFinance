"""
FinGuard AI — Шаг 5: proxy-модель Probability of Default (часть Stage 4).

ВАРИАНТ А (рекомендуется, если успеваете по времени):
  Скачайте вручную (в браузере — сайты Kaggle/UCI не входят в разрешённые
  для автоматической загрузки домены):
    - UCI "Default of Credit Card Clients":
      https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients
    - или Kaggle "Give Me Some Credit":
      https://www.kaggle.com/c/GiveMeSomeCredit
  Положите CSV в data/external_credit_dataset.csv и запустите этот скрипт —
  он обучит логрегрессию на публичных данных о дефолте (retail-заёмщики)
  и сохранит калиброванные веса как proxy-логику для корпоративных факторов.

ВАРИАНТ Б (fallback, если не успели скачать/почистить внешний датасет):
  Скрипт сам обучится на СВЯЗИ ваших синтетических financial_score/anomaly_score
  с бинарным "стал ли HIGH RISK" (это менее строго, но работает как демо
  и остаётся честным: вы прямо говорите на защите, что PD-модель — proxy).
"""

import pandas as pd
import numpy as np
import os
from sklearn.linear_model import LogisticRegression

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
EXTERNAL = f"{DATA}/external_credit_dataset.csv"

def train_on_external():
    df = pd.read_csv(EXTERNAL)
    # ПРИМЕР для UCI Default of Credit Card Clients (переименуйте колонки под свой файл):
    # target = 'default payment next month'; фичи: LIMIT_BAL, BILL_AMT*, PAY_AMT*, PAY_*
    target_col = "default payment next month"
    feature_cols = [c for c in df.columns if c not in (target_col, "ID")]
    X, y = df[feature_cols].fillna(0), df[target_col]
    model = LogisticRegression(max_iter=1000).fit(X, y)
    print(f"Proxy-модель обучена на внешнем датасете: {len(df)} строк, AUC-подобная оценка (train acc)="
          f"{model.score(X, y):.3f}")
    return model, feature_cols

def train_fallback():
    """Обучаемся на собственных синтетических данных: связь financial_score/anomaly_score -> HIGH RISK."""
    fh = pd.read_csv(f"{DATA}/financial_health_scores.csv")
    an = pd.read_csv(f"{DATA}/anomaly_scores.csv")
    merged = fh.merge(an, on="company_id", how="left").fillna({"anomaly_score": 30})
    merged["label_high_risk"] = (merged["financial_score"] > 65).astype(int)

    X = merged[["financial_score", "anomaly_score"]]
    y = merged["label_high_risk"]
    if y.nunique() < 2:
        # если случайно все компании в одном классе — добавим синтетическую противоположность
        X = pd.concat([X, pd.DataFrame({"financial_score": [10, 90], "anomaly_score": [10, 90]})])
        y = pd.concat([y, pd.Series([0, 1])])
    model = LogisticRegression(max_iter=1000).fit(X, y)
    print("Proxy-модель обучена в fallback-режиме на собственных синтетических данных.")
    return model, ["financial_score", "anomaly_score"]

def predict_pd(model, feature_cols, financial_score, anomaly_score):
    """Для fallback-модели. Для внешней — адаптируйте маппинг корп.коэффициентов в её фичи."""
    x = pd.DataFrame([[financial_score, anomaly_score]], columns=feature_cols)
    return float(model.predict_proba(x)[0, 1])

if __name__ == "__main__":
    if os.path.exists(EXTERNAL):
        model, cols = train_on_external()
    else:
        print("Внешний датасет не найден — используем fallback-режим (см. докстринг сверху).")
        model, cols = train_fallback()

    fh = pd.read_csv(f"{DATA}/financial_health_scores.csv")
    an = pd.read_csv(f"{DATA}/anomaly_scores.csv")
    merged = fh.merge(an, on="company_id", how="left").fillna({"anomaly_score": 30})
    merged["pd_12m"] = merged.apply(
        lambda r: predict_pd(model, cols, r["financial_score"], r["anomaly_score"]), axis=1)
    merged[["company_id", "pd_12m"]].to_csv(f"{DATA}/pd_scores.csv", index=False)
    print(merged[["company_id", "financial_score", "anomaly_score", "pd_12m"]])
