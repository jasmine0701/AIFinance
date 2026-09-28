"""
FinGuard AI — Шаг 2: модуль Financial Health (Stage 1).

Rule-based скоринговая карта: без обучающей выборки, полностью объяснимо.
Person 2 (бизнес-аналитик) отвечает за веса и пороги ниже — это ЕГО/ЕЁ основная
"не техническая" работа: подобрать реалистичные банковские пороги.
"""

import pandas as pd
import numpy as np
import os

DATA = os.path.join(os.path.dirname(__file__), "..", "data")

def compute_ratios(fin_df: pd.DataFrame) -> pd.DataFrame:
    df = fin_df.sort_values(["company_id", "period"]).copy()
    df["debt_to_ebitda"] = df["debt"] / df["ebitda"].replace(0, np.nan)
    df["debt_to_revenue"] = df["debt"] / df["revenue"]
    df["current_ratio"] = df["current_assets"] / df["current_liabilities"]
    df["quick_ratio"] = (df["current_assets"] - df["receivables"] * 0.3) / df["current_liabilities"]
    df["profit_margin"] = df["net_profit"] / df["revenue"]
    df["cash_flow_margin"] = df["ebitda"] / df["revenue"]
    df["equity_ratio"] = df["equity"] / df["assets"]

    # рост показателей квартал-к-кварталу, по каждой компании отдельно
    for col in ["revenue", "debt", "receivables"]:
        df[f"{col}_growth"] = df.groupby("company_id")[col].pct_change()

    return df

# ---- ПОРОГИ И ВЕСА (задаёт Person 2, исходя из типичной банковской практики) ----
WEIGHTS = {
    "debt_to_ebitda":    0.25,   # выше 4-5x — тревожно
    "current_ratio":     0.20,   # ниже 1.0 — тревожно (инвертируем ниже)
    "revenue_growth":    0.20,   # отрицательный рост — тревожно
    "debt_growth":       0.15,   # быстрый рост долга — тревожно
    "receivables_growth":0.10,   # быстрый рост дебиторки — тревожно
    "profit_margin":     0.10,   # низкая/отрицательная маржа — тревожно
}

def score_component(value, low, high, invert=False):
    """Линейно переводит значение в 0..100 (100 = максимально плохо)."""
    if pd.isna(value):
        return 50  # нейтрально при отсутствии данных
    score = (value - low) / (high - low) * 100
    score = np.clip(score, 0, 100)
    return 100 - score if invert else score

def financial_health_score(row) -> dict:
    s_debt_ebitda   = score_component(row["debt_to_ebitda"], 1, 6)
    s_current_ratio = score_component(row["current_ratio"], 0.6, 2.0, invert=True)
    s_rev_growth    = score_component(row["revenue_growth"], -0.25, 0.10, invert=True)
    s_debt_growth   = score_component(row["debt_growth"], -0.05, 0.30)
    s_ar_growth     = score_component(row["receivables_growth"], -0.05, 0.40)
    s_margin        = score_component(row["profit_margin"], -0.05, 0.15, invert=True)

    components = {
        "debt_to_ebitda": s_debt_ebitda, "current_ratio": s_current_ratio,
        "revenue_growth": s_rev_growth, "debt_growth": s_debt_growth,
        "receivables_growth": s_ar_growth, "profit_margin": s_margin,
    }
    overall = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)

    # топ-3 фактора риска — то, что покажем в "Main factors"
    top = sorted(components.items(), key=lambda x: -x[1])[:3]
    factors = [f"{name}={val:.0f}" for name, val in top if val > 50]

    return {"financial_score": round(overall, 1), "top_factors_financial": factors}

def risk_level(score: float) -> str:
    if score < 40:
        return "LOW"
    elif score < 70:
        return "MEDIUM"
    return "HIGH"

if __name__ == "__main__":
    fin = pd.read_csv(f"{DATA}/financial_statements.csv", parse_dates=["period"])
    ratios = compute_ratios(fin)
    latest = ratios.sort_values("period").groupby("company_id").tail(1).copy()

    # считаем score по КАЖДОМУ кварталу (нужно для forecast/тренда)
    hist_results = ratios.apply(financial_health_score, axis=1, result_type="expand")
    history = pd.concat([ratios[["company_id", "period"]], hist_results], axis=1)
    history.to_csv(f"{DATA}/financial_health_scores_history.csv", index=False)

    results = latest.apply(financial_health_score, axis=1, result_type="expand")
    latest = pd.concat([latest[["company_id", "period"]], results], axis=1)
    latest["risk_level"] = latest["financial_score"].apply(risk_level)

    latest.to_csv(f"{DATA}/financial_health_scores.csv", index=False)
    print(latest[["company_id", "financial_score", "risk_level", "top_factors_financial"]])
