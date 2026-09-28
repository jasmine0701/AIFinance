"""
FinGuard AI — Шаг 6: Risk Engine (Stage 4, финал).

Собирает вместе:
  financial_score (Stage 1) + anomaly_score (Stage 2) + forecast (Stage 3) + pd_12m (Stage 4-PD)
и выдаёт итоговую карточку компании — ровно то, что видно на дашборде и в демо.
"""

import pandas as pd
import numpy as np
import os
import json

DATA = os.path.join(os.path.dirname(__file__), "..", "data")

# Веса агрегации — тоже зона ответственности Person 2 (бизнес-логика)
OVERALL_WEIGHTS = {"financial_score": 0.5, "anomaly_score": 0.2, "forecast_score_12m": 0.3}

def risk_level(score: float) -> str:
    if score < 40:
        return "LOW"
    elif score < 70:
        return "MEDIUM"
    return "HIGH"

def monitoring_level(level: str) -> str:
    return {"LOW": "STANDARD", "MEDIUM": "ENHANCED", "HIGH": "INTENSIVE"}[level]

def recommended_actions(level: str) -> list:
    if level == "LOW":
        return ["стандартный мониторинг", "плановая переоценка через 12 мес."]
    if level == "MEDIUM":
        return ["усиленный анализ аналитиком", "запросить обновлённую отчётность", "мониторинг раз в квартал"]
    return ["интенсивный мониторинг", "запросить обновлённую отчётность", "пересмотр кредитного лимита",
            "дополнительная проверка контрагентов", "ручной анализ риск-офицером"]

def recommended_credit_limit(requested_limit: float, overall_score: float, pd_12m: float) -> dict:
    # простая, прозрачная формула для MVP — не "чёрный ящик"
    capacity_factor = np.clip(1 - overall_score / 100 - pd_12m * 0.5, 0.1, 1.0)
    recommended = requested_limit * capacity_factor
    max_exposure = recommended * 1.15
    return {"recommended_limit": round(recommended, -3), "max_exposure": round(max_exposure, -3)}

def build_company_report(company_id, financial_row, anomaly_row, forecast_row, pd_row,
                          requested_limit=60_000) -> dict:
    overall = (financial_row["financial_score"] * OVERALL_WEIGHTS["financial_score"] +
               anomaly_row["anomaly_score"] * OVERALL_WEIGHTS["anomaly_score"] +
               forecast_row["forecast_12m"] * OVERALL_WEIGHTS["forecast_score_12m"])
    level = risk_level(overall)
    limits = recommended_credit_limit(requested_limit, overall, pd_row["pd_12m"])

    top_factors = (eval(financial_row["top_factors_financial"]) if isinstance(financial_row["top_factors_financial"], str)
                   else financial_row["top_factors_financial"])
    anomaly_factors = (eval(anomaly_row["top_factors_anomaly"]) if isinstance(anomaly_row["top_factors_anomaly"], str)
                        else anomaly_row["top_factors_anomaly"])

    return {
        "company_id": int(company_id),
        "financial_risk": risk_level(financial_row["financial_score"]),
        "transaction_anomaly_risk": risk_level(anomaly_row["anomaly_score"]),
        "forecast_risk": risk_level(forecast_row["forecast_12m"]),
        "overall_risk_score": round(overall, 1),
        "risk_level": level,
        "pd_12m_pct": round(pd_row["pd_12m"] * 100, 1),
        "requested_credit_limit": requested_limit,
        "recommended_credit_limit": limits["recommended_limit"],
        "max_acceptable_exposure": limits["max_exposure"],
        "monitoring_level": monitoring_level(level),
        "forecast_trend": {"3m": round(forecast_row["forecast_3m"], 1),
                            "6m": round(forecast_row["forecast_6m"], 1),
                            "12m": round(forecast_row["forecast_12m"], 1)},
        "top_risk_factors": (top_factors + anomaly_factors)[:5],
        "recommended_actions": recommended_actions(level),
    }

if __name__ == "__main__":
    fin = pd.read_csv(f"{DATA}/financial_health_scores.csv").set_index("company_id")
    an = pd.read_csv(f"{DATA}/anomaly_scores.csv").set_index("company_id")
    fc = pd.read_csv(f"{DATA}/forecast_scores.csv").set_index("company_id")
    pd_ = pd.read_csv(f"{DATA}/pd_scores.csv").set_index("company_id")
    companies = pd.read_csv(f"{DATA}/companies.csv").set_index("company_id")

    reports = []
    for cid in fin.index:
        if cid not in an.index or cid not in fc.index or cid not in pd_.index:
            continue
        report = build_company_report(cid, fin.loc[cid], an.loc[cid], fc.loc[cid], pd_.loc[cid])
        report["name"] = companies.loc[cid, "name"]
        reports.append(report)

    with open(f"{DATA}/final_reports.json", "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)

    for r in reports:
        print(f"{r['name']:20s} | {r['risk_level']:6s} | score={r['overall_risk_score']:5.1f} | "
              f"PD={r['pd_12m_pct']}% | лимит: {r['requested_credit_limit']:,} -> {r['recommended_credit_limit']:,}")
