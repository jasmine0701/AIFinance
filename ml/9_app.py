"""
FinGuard AI — FastAPI сервер.
"""
from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
from importlib import import_module
import pandas as pd
import joblib
import os
import io

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
fh = import_module("2_financial_health")
risk_engine = import_module("6_risk_engine")

pd_bundle = joblib.load(f"{MODELS}/pd_model.joblib")
pd_model, pd_features = pd_bundle["model"], pd_bundle["feature_cols"]
anomaly_bundle = joblib.load(f"{MODELS}/anomaly_model.joblib")
anomaly_model, anomaly_features = anomaly_bundle["model"], anomaly_bundle["feature_cols"]

def generate_cross_check(row: pd.Series) -> dict:
    """Выполняет глубокий кросс-чекинг основных финансовых показателей."""
    findings = []
    score = 0

    revenue = float(row.get("revenue", 0))
    net_profit = float(row.get("net_profit", 0))
    cash = float(row.get("cash", 0))
    assets = float(row.get("assets", 0))
    debt = float(row.get("debt", 0))
    equity = float(row.get("equity", 0))

    if net_profit > revenue and revenue > 0:
        findings.append("Критично: Чистая прибыль превышает выручку")
        score += 40

    if cash > assets and assets > 0:
        findings.append("Аномалия: Денежные средства превышают общие активы")
        score += 50

    if debt > assets and assets > 0:
        findings.append("Риск банкротства: Долг превышает валюту баланса (активы)")
        score += 30

    if equity < 0:
        findings.append("Тревога: Отрицательный собственный капитал")
        score += 40

    level = "LOW"
    if score >= 30: level = "MEDIUM"
    if score >= 60: level = "HIGH"

    return {
        "cross_check_risk_score": min(100, score),
        "level": level,
        "top_findings": findings
    }

@app.post("/analyze")
async def analyze_company(request: AnalyzeRequest):
    if not request.data:
        return {"error": "В запросе отсутствуют финансовые данные"}

    df = pd.DataFrame([record.model_dump() for record in request.data])
    required_cols = ["revenue", "ebitda", "net_profit", "debt", "cash", "current_assets",
                     "current_liabilities", "receivables", "payables", "equity", "assets"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        return {"error": f"В данных отсутствуют обязательные колонки: {missing}. Ожидаются: {required_cols}"}

    df["company_id"] = 1
    df["period"] = pd.to_datetime(df["year"].astype(str) + "-01-01")

    ratios = fh.compute_ratios(df)
    fh_result = fh.financial_health_score(ratios.iloc[-1])
    financial_score = fh_result["financial_score"]

    anomaly_result = {"anomaly_score": 30, "top_factors_anomaly": ["данные о транзакциях не загружены"]}

    forecast_12m = financial_score
    if len(df) >= 3:
        try:
            forecast_module = import_module("4_forecast")
            forecast_12m = forecast_module.forecast_company(df).get("forecast_12m", financial_score)
        except Exception:
            pass

    pd_input = pd.DataFrame([[financial_score, anomaly_result["anomaly_score"]]], columns=pd_features)
    pd_value = float(pd_model.predict_proba(pd_input)[0, 1])

    # --- ДИНАМИЧЕСКИЙ ПЕНАЛЬТИ ЗА СУММУ КРЕДИТА (с учетом размерности) ---
    latest_revenue = float(df["revenue"].iloc[-1]) if not df.empty else 0.0

    unit_str = str(df["unit"].iloc[-1]).lower() if "unit" in df.columns else ""
    multiplier = 1.0
    if "тыс" in unit_str or "thousand" in unit_str:
        multiplier = 1_000.0
    elif "млн" in unit_str or "mln" in unit_str or "million" in unit_str:
        multiplier = 1_000_000.0

    real_revenue_kzt = latest_revenue * multiplier

    limit_penalty = 0.0
    ratio = 0.0
    if real_revenue_kzt > 0:
        ratio = request.requested_limit / real_revenue_kzt
        if ratio > 0.5:  # Начинаем штрафовать, если просят больше 50% от выручки
            limit_penalty = min(35.0, (ratio - 0.5) * 20.0)

    overall = (
            financial_score * risk_engine.OVERALL_WEIGHTS["financial_score"] +
            anomaly_result["anomaly_score"] * risk_engine.OVERALL_WEIGHTS["anomaly_score"] +
            forecast_12m * risk_engine.OVERALL_WEIGHTS["forecast_score_12m"]
    ) + limit_penalty
    overall = min(100.0, overall)

    level = risk_engine.risk_level(overall)
    limits = risk_engine.recommended_credit_limit(request.requested_limit, overall, pd_value)

    # ==========================================
    # ДЕБАГ: ВЫВОД В КОНСОЛЬ (для Excel / PDF)
    # ==========================================
    company_name = df["company"].iloc[0] if not df.empty and "company" in df.columns else "Unknown"
    print(f"\n{'='*10} ДЕБАГ: {company_name} (PDF/Excel) {'='*10}")
    print(f"1. Запрошенный лимит с фронтенда: {request.requested_limit:,.0f}")
    print(f"2. Оригинальная выручка из таблицы: {latest_revenue}")
    print(f"3. Распознанный множитель (unit_str='{unit_str}'): {multiplier}")
    print(f"4. Итоговая выручка в тенге для расчетов: {real_revenue_kzt:,.0f}")
    if real_revenue_kzt > 0:
        print(f"5. Отношение (Запрос / Выручка): {ratio:.3f} (если > 0.5 будет штраф)")
    print(f"6. Начисленный штраф за лимит: +{limit_penalty:.1f} баллов")
    print(f"7. Базовый фин. скоринг: {financial_score:.1f}")
    print(f"8. ИТОГОВЫЙ СКОРИНГ (overall): {overall:.1f} -> {level}")
    print(f"9. Выданный лимит: {limits['recommended_limit']:,.0f}")
    print("="*40 + "\n")
    # ==========================================

    # --- КРОСС-ЧЕКИНГ ---
    cross_check_result = generate_cross_check(df.iloc[-1])

    top_factors = (fh_result["top_factors_financial"] + anomaly_result["top_factors_anomaly"])
    if cross_check_result["top_findings"]:
        top_factors.extend(cross_check_result["top_findings"])

    return {
        "companies": sorted(df["company"].dropna().unique().tolist()),
        "financial_risk": risk_engine.risk_level(financial_score),
        "transaction_anomaly_risk": risk_engine.risk_level(anomaly_result["anomaly_score"]),
        "overall_risk_score": round(overall, 1),
        "risk_level": level,
        "pd_12m_percent": round(pd_value * 100, 1),
        "requested_credit_limit": request.requested_limit,
        "recommended_credit_limit": limits["recommended_limit"],
        "monitoring_level": risk_engine.monitoring_level(level),
        "top_risk_factors": top_factors[:5],
        "recommended_actions": risk_engine.recommended_actions(level),
        "forecast_12m": round(float(forecast_12m), 1),
        "cross_check": cross_check_result,
        "records_used": len(df),
        "note": "Анализ выполнен на основе финансовой отчётности, переданной ExcelService."
    }

@app.post("/analyze-batch")
async def analyze_batch(file: UploadFile = File(...), requested_limit: float = Form(60_000_000)):
    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        return {"error": f"Ошибка чтения CSV: {str(e)}"}

    COLUMN_MAPPING = {
        "Компания": "company", "Год": "year", "Выручка": "revenue", "EBITDA / операционная прибыль": "ebitda",
        "Чистая прибыль": "net_profit", "Долг": "debt", "Деньги": "cash", "Краткосрочные активы": "current_assets",
        "Краткосрочные обязательства": "current_liabilities", "Дебиторская задолженность": "receivables",
        "Кредиторская задолженность": "payables", "Капитал": "equity", "Активы всего": "assets",
    }
    df = df.rename(columns=COLUMN_MAPPING)

    if "company" not in df.columns:
        df["company"] = "Unknown Company"
    if "year" not in df.columns:
        df["year"] = 2025

    required_cols = ["revenue", "ebitda", "net_profit", "debt", "cash", "current_assets",
                     "current_liabilities", "receivables", "payables", "equity", "assets"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = 0.0

    df[required_cols] = df[required_cols].fillna(0)

    results = []
    summary = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}

    for company_name, group in df.groupby("company"):
        group = group.sort_values("year")

        group_copy = group.copy()
        group_copy["company_id"] = 1
        group_copy["period"] = pd.to_datetime(group_copy["year"].astype(str) + "-01-01")

        ratios = fh.compute_ratios(group_copy)
        fh_result = fh.financial_health_score(ratios.iloc[-1])
        financial_score = fh_result["financial_score"]

        anomaly_result = {"anomaly_score": 30, "top_factors_anomaly": ["транзакции не загружены"]}

        forecast_12m = financial_score
        if len(group) >= 3:
            try:
                forecast_module = import_module("4_forecast")
                forecast_12m = forecast_module.forecast_company(group_copy).get("forecast_12m", financial_score)
            except Exception:
                pass

        pd_input = pd.DataFrame([[financial_score, anomaly_result["anomaly_score"]]], columns=pd_features)
        pd_value = float(pd_model.predict_proba(pd_input)[0, 1])

        # --- ДИНАМИЧЕСКИЙ ПЕНАЛЬТИ ЗА СУММУ КРЕДИТА (с учетом размерности) ---
        latest_revenue = float(group["revenue"].iloc[-1]) if not group.empty else 0.0

        unit_str = str(group["unit"].iloc[-1]).lower() if "unit" in group.columns else ""
        multiplier = 1.0
        if "тыс" in unit_str or "thousand" in unit_str:
            multiplier = 1_000.0
        elif "млн" in unit_str or "mln" in unit_str or "million" in unit_str:
            multiplier = 1_000_000.0

        real_revenue_kzt = latest_revenue * multiplier

        limit_penalty = 0.0
        ratio = 0.0
        if real_revenue_kzt > 0:
            ratio = requested_limit / real_revenue_kzt
            if ratio > 0.5:
                limit_penalty = min(35.0, (ratio - 0.5) * 20.0)

        overall = (
            financial_score * risk_engine.OVERALL_WEIGHTS["financial_score"] +
            anomaly_result["anomaly_score"] * risk_engine.OVERALL_WEIGHTS["anomaly_score"] +
            forecast_12m * risk_engine.OVERALL_WEIGHTS["forecast_score_12m"]
        ) + limit_penalty
        overall = min(100.0, overall)

        level = risk_engine.risk_level(overall)
        limits = risk_engine.recommended_credit_limit(requested_limit, overall, pd_value)

        # ==========================================
        # ДЕБАГ: ВЫВОД В КОНСОЛЬ (для CSV)
        # ==========================================
        print(f"\n{'='*10} ДЕБАГ: {company_name} (CSV) {'='*10}")
        print(f"1. Запрошенный лимит с фронтенда: {requested_limit:,.0f}")
        print(f"2. Оригинальная выручка из таблицы: {latest_revenue}")
        print(f"3. Распознанный множитель (unit_str='{unit_str}'): {multiplier}")
        print(f"4. Итоговая выручка в тенге для расчетов: {real_revenue_kzt:,.0f}")
        if real_revenue_kzt > 0:
            print(f"5. Отношение (Запрос / Выручка): {ratio:.3f} (если > 0.5 будет штраф)")
        print(f"6. Начисленный штраф за лимит: +{limit_penalty:.1f} баллов")
        print(f"7. Базовый фин. скоринг: {financial_score:.1f}")
        print(f"8. ИТОГОВЫЙ СКОРИНГ (overall): {overall:.1f} -> {level}")
        print(f"9. Выданный лимит: {limits['recommended_limit']:,.0f}")
        print("="*40 + "\n")
        # ==========================================

        # --- КРОСС-ЧЕКИНГ ---
        cross_check_result = generate_cross_check(group.iloc[-1])

        top_factors = (fh_result["top_factors_financial"] + anomaly_result["top_factors_anomaly"])
        if cross_check_result["top_findings"]:
            top_factors.extend(cross_check_result["top_findings"])

        summary[level] = summary.get(level, 0) + 1

        results.append({
            "company_name": str(company_name),
            "financial_risk": risk_engine.risk_level(financial_score),
            "transaction_anomaly_risk": risk_engine.risk_level(anomaly_result["anomaly_score"]),
            "overall_risk_score": round(overall, 1),
            "risk_level": level,
            "pd_12m_percent": round(pd_value * 100, 1),
            "requested_credit_limit": requested_limit,
            "recommended_credit_limit": limits["recommended_limit"],
            "monitoring_level": risk_engine.monitoring_level(level),
            "top_risk_factors": top_factors[:5],
            "recommended_actions": risk_engine.recommended_actions(level),
            "forecast_12m": round(float(forecast_12m), 1),
            "cross_check": cross_check_result,
            "records_used": len(group)
        })

    return {
        "companies_count": len(results),
        "summary": summary,
        "results": results
    }