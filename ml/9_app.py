"""
FinGuard AI — FastAPI сервер.
Запуск:  uvicorn 9_app:app --reload

ГЛАВНАЯ ИДЕЯ ЭТОГО ФАЙЛА: он НЕ переписывает логику заново — он ПЕРЕИСПОЛЬЗУЕТ
уже готовые и проверенные функции из файлов 2_financial_health.py и
6_risk_engine.py (импортирует их как модули), плюс загружает уже обученные
модели из models/*.joblib. Свой код здесь есть только там, где нужно
"склеить" всё это вместе и принять файл от пользователя.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
from importlib import import_module
import pandas as pd
import joblib
import os


class FinancialRecord(BaseModel):
    company: str
    year: int
    unit: Optional[str] = None

    revenue: float
    ebitda: float
    net_profit: float
    debt: float
    cash: float
    current_assets: float
    current_liabilities: float
    receivables: float
    payables: float
    equity: float
    assets: float


class AnalyzeRequest(BaseModel):
    filename: Optional[str] = None
    records_count: Optional[int] = None
    data: List[FinancialRecord]
    requested_limit: float = 60_000_000


app = FastAPI(title="FinGuard AI API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

MODELS = os.path.join(os.path.dirname(__file__), "..", "models")

# =====================================================================
# 1. ИМПОРТИРУЕМ УЖЕ ГОТОВЫЕ ФУНКЦИИ из старых файлов (не копируем код!)
# =====================================================================
fh = import_module("2_financial_health")  # даёт compute_ratios(), financial_health_score()
risk_engine = import_module("6_risk_engine")  # даёт risk_level(), monitoring_level(),
# recommended_actions(), recommended_credit_limit()

# =====================================================================
# 2. ЗАГРУЖАЕМ УЖЕ ОБУЧЕННЫЕ МОДЕЛИ — один раз, при старте сервера
# =====================================================================
pd_bundle = joblib.load(f"{MODELS}/pd_model.joblib")
pd_model, pd_features = pd_bundle["model"], pd_bundle["feature_cols"]

anomaly_bundle = joblib.load(f"{MODELS}/anomaly_model.joblib")
anomaly_model, anomaly_features = anomaly_bundle["model"], anomaly_bundle["feature_cols"]

print("Модели загружены. Функции Stage 1 и Stage 4 импортированы из старых файлов.")


def score_transactions(txn_df: pd.DataFrame) -> dict:
    """Stage 2: анализ транзакций ЗАГРУЖЕННОЙ моделью (без переобучения).
    Логика построения признаков — та же, что в 3_anomaly_detection.py,
    просто вызывается на новых данных через уже готовую модель."""
    if txn_df is None or len(txn_df) == 0:
        return {"anomaly_score": 30, "top_factors_anomaly": ["нет данных о транзакциях"]}

    hist_mean = txn_df["amount"].mean()
    hist_std = txn_df["amount"].std() or 1.0
    known_cps = set(txn_df["counterparty_id"].value_counts().head(15).index)

    feats = []
    for _, r in txn_df.iterrows():
        feats.append(dict(
            amount_zscore=(r["amount"] - hist_mean) / hist_std,
            ratio_to_avg=r["amount"] / hist_mean,
            is_new_counterparty=int(r["counterparty_id"] not in known_cps),
            unusual_hour=int(
                pd.to_datetime(r["txn_timestamp"]).hour < 6 or pd.to_datetime(r["txn_timestamp"]).hour > 22),
        ))
    feats_df = pd.DataFrame(feats)
    decision = anomaly_model.decision_function(feats_df[anomaly_features])
    # переводим decision_function в 0..100, как в 3_anomaly_detection.py
    score = ((decision.max() - decision) / (decision.max() - decision.min() + 1e-9) * 100)
    top_idx = score.argsort()[::-1][:3]
    reasons = []
    for i in top_idx:
        if feats[i]["ratio_to_avg"] > 3:
            reasons.append(f"сумма транзакции в {feats[i]['ratio_to_avg']:.1f}x выше среднего")
        if feats[i]["is_new_counterparty"]:
            reasons.append("новый контрагент")
    return {"anomaly_score": round(float(score[top_idx].mean()), 1),
            "top_factors_anomaly": list(dict.fromkeys(reasons))[:3]}


@app.post("/analyze")
async def analyze_company(request: AnalyzeRequest):
    if not request.data:
        return {
            "error": "В запросе отсутствуют финансовые данные"
        }

    # -------------------------------------------------------------
    # JSON -> DataFrame
    # -------------------------------------------------------------
    df = pd.DataFrame([
        record.model_dump()
        for record in request.data
    ])

    required_cols = [
        "revenue",
        "ebitda",
        "net_profit",
        "debt",
        "cash",
        "current_assets",
        "current_liabilities",
        "receivables",
        "payables",
        "equity",
        "assets"
    ]

    missing = [
        col for col in required_cols
        if col not in df.columns
    ]

    if missing:
        return {
            "error": (
                f"В данных отсутствуют обязательные колонки: {missing}. "
                f"Ожидаются: {required_cols}"
            )
        }

    # -------------------------------------------------------------
    # Stage 1: Financial Health
    # -------------------------------------------------------------
    df["company_id"] = 1
    df["period"] = pd.to_datetime(
        df["year"].astype(str) + "-01-01"
    )

    ratios = fh.compute_ratios(df)

    fh_result = fh.financial_health_score(
        ratios.iloc[-1]
    )

    financial_score = fh_result["financial_score"]

    # -------------------------------------------------------------
    # Stage 2: Anomaly Detection
    # -------------------------------------------------------------
    #
    # ExcelService сейчас передаёт только финансовую отчётность.
    # Транзакций в этом JSON нет.
    #
    anomaly_result = {
        "anomaly_score": 30,
        "top_factors_anomaly": [
            "данные о транзакциях не загружены"
        ]
    }

    # -------------------------------------------------------------
    # Stage 3: Forecast
    # -------------------------------------------------------------
    #
    # Если есть несколько периодов одной компании,
    # можно построить настоящий forecast.
    #
    forecast_12m = financial_score

    if len(df) >= 3:
        try:
            forecast_module = import_module("4_forecast")

            forecast_result = forecast_module.forecast_company(
                df
            )

            forecast_12m = forecast_result.get(
                "forecast_12m",
                financial_score
            )

        except Exception:
            forecast_12m = financial_score

    # -------------------------------------------------------------
    # Stage 4: PD
    # -------------------------------------------------------------
    pd_input = pd.DataFrame(
        [[
            financial_score,
            anomaly_result["anomaly_score"]
        ]],
        columns=pd_features
    )

    pd_value = float(
        pd_model.predict_proba(pd_input)[0, 1]
    )

    # -------------------------------------------------------------
    # Final Risk Engine
    # -------------------------------------------------------------
    overall = (
            financial_score *
            risk_engine.OVERALL_WEIGHTS["financial_score"]

            +

            anomaly_result["anomaly_score"] *
            risk_engine.OVERALL_WEIGHTS["anomaly_score"]

            +

            forecast_12m *
            risk_engine.OVERALL_WEIGHTS["forecast_score_12m"]
    )

    level = risk_engine.risk_level(overall)

    limits = risk_engine.recommended_credit_limit(
        request.requested_limit,
        overall,
        pd_value
    )

    # -------------------------------------------------------------
    # Response
    # -------------------------------------------------------------
    return {
        "companies": sorted(
            df["company"].dropna().unique().tolist()
        ),

        "financial_risk": risk_engine.risk_level(
            financial_score
        ),

        "transaction_anomaly_risk": risk_engine.risk_level(
            anomaly_result["anomaly_score"]
        ),

        "overall_risk_score": round(
            overall,
            1
        ),

        "risk_level": level,

        "pd_12m_percent": round(
            pd_value * 100,
            1
        ),

        "requested_credit_limit": request.requested_limit,

        "recommended_credit_limit": limits[
            "recommended_limit"
        ],

        "monitoring_level": risk_engine.monitoring_level(
            level
        ),

        "top_risk_factors": (
                fh_result["top_factors_financial"]
                +
                anomaly_result["top_factors_anomaly"]
        )[:5],

        "recommended_actions": risk_engine.recommended_actions(
            level
        ),

        "forecast_12m": round(
            float(forecast_12m),
            1
        ),

        "records_used": len(df),

        "note": (
            "Анализ выполнен на основе финансовой "
            "отчётности, переданной ExcelService."
        )
    }
