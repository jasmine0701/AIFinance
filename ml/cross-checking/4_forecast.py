"""
FinGuard AI — Шаг 4: модуль Risk Forecast (Stage 3).

Простейший, но честный подход: линейная экстраполяция тренда исторического
финансового риска на 3 / 6 / 12 месяцев. Явно помечаем, что это "если текущий
тренд продолжится" — а не гарантированный прогноз.
"""

import pandas as pd
import numpy as np
import os
from sklearn.linear_model import LinearRegression

DATA = os.path.join(os.path.dirname(__file__), "..", "data")

def forecast_company(history: pd.DataFrame) -> dict:
    """history: DataFrame с колонками period (datetime) и financial_score, отсортирован по period."""
    history = history.sort_values("period").reset_index(drop=True)
    if len(history) < 3:
        # недостаточно истории — просто держим текущее значение (без экстраполяции)
        current = history["financial_score"].iloc[-1]
        return {"forecast_3m": current, "forecast_6m": current, "forecast_12m": current}

    x = np.arange(len(history)).reshape(-1, 1)   # номер квартала
    y = history["financial_score"].values
    model = LinearRegression().fit(x, y)

    current_idx = len(history) - 1
    preds = {}
    for months, label in [(3, "forecast_3m"), (6, "forecast_6m"), (12, "forecast_12m")]:
        step = current_idx + months / 3.0   # 1 квартал = 3 месяца
        pred = model.predict([[step]])[0]
        preds[label] = float(np.clip(pred, 0, 100))
    return preds

if __name__ == "__main__":
    fin_scores = pd.read_csv(f"{DATA}/financial_health_scores.csv", parse_dates=["period"])
    # для честного тренда в MVP нужна история score по кварталам, а не только последняя точка;
    # если Stage 1 считался только для latest-квартала, для forecast нужно прогнать
    # 2_financial_health.py по ВСЕЙ истории (без .tail(1)) — см. README.
    all_history = pd.read_csv(f"{DATA}/financial_health_scores_history.csv", parse_dates=["period"]) \
        if os.path.exists(f"{DATA}/financial_health_scores_history.csv") else fin_scores

    results = []
    for company_id, g in all_history.groupby("company_id"):
        f = forecast_company(g)
        f["company_id"] = company_id
        results.append(f)

    out = pd.DataFrame(results)
    out.to_csv(f"{DATA}/forecast_scores.csv", index=False)
    print(out)
