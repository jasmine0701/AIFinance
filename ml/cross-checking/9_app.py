"""
FinGuard AI — FastAPI сервер.
Запуск:  uvicorn 9_app:app --reload

ГЛАВНАЯ ИДЕЯ: файл не переписывает логику заново — он ПЕРЕИСПОЛЬЗУЕТ уже
готовые и проверенные функции из файлов 2_financial_health.py, 3_cross_check.py,
4_forecast.py и 6_risk_engine.py (импортирует их как модули), плюс загружает
обученные модели из models/*.joblib.

ДВА РЕЖИМА ВХОДА (определяются автоматически по составу колонок файла):
  BASIC    — одна строка, 11 привычных показателей. Работает как раньше.
             Прогноз (Stage 3) в этом режиме не считается по-настоящему —
             истории для тренда нет, forecast = текущему баллу.
  ADVANCED — несколько строк ОДНОЙ компании (2023, 2024, 2025 и т.д.),
             расширенный набор полей (баланс + ОПиУ + ОДДС). В этом режиме
             дополнительно считается Cross-Checking Engine (согласованность
             отчётности) И настоящий прогноз тренда по реальной истории.
"""

from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from importlib import import_module
import pandas as pd
import joblib
import os

app = FastAPI(title="FinGuard AI API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

import os

BASE_DIR = "/home/natooa/AIFinance"
MODELS = os.path.join(BASE_DIR, "models", "cross-checking")

print("MODELS =", MODELS)
print("PD MODEL EXISTS =", os.path.exists(os.path.join(MODELS, "pd_model.joblib")))
print("ANOMALY MODEL EXISTS =", os.path.exists(os.path.join(MODELS, "anomaly_model.joblib")))

# =====================================================================
# 1. ИМПОРТИРУЕМ УЖЕ ГОТОВЫЕ ФУНКЦИИ из отдельных файлов (не копируем код!)
# =====================================================================
fh = import_module("2_financial_health")
cross_check = import_module("3_cross_check")
forecast_mod = import_module("4_forecast")
risk_engine = import_module("6_risk_engine")
pdf_parser = import_module("pdf_parser")

# =====================================================================
# 2. ЗАГРУЖАЕМ УЖЕ ОБУЧЕННЫЕ МОДЕЛИ — один раз, при старте сервера
# =====================================================================
pd_bundle = joblib.load(f"{MODELS}/pd_model.joblib")
pd_model, pd_features = pd_bundle["model"], pd_bundle["feature_cols"]

anomaly_bundle = joblib.load(f"{MODELS}/anomaly_model.joblib")
anomaly_model, anomaly_features = anomaly_bundle["model"], anomaly_bundle["feature_cols"]

print("Модели загружены. Функции Stage 1, Cross-Check, Stage 3 и Stage 4 импортированы из отдельных файлов.")

BASIC_REQUIRED = ["revenue", "ebitda", "net_profit", "debt", "cash", "current_assets",
                   "current_liabilities", "receivables", "payables", "equity", "assets"]

# Поля, дополнительно нужные для ADVANCED-режима (cross-checking).
# retained_earnings — обязательно (иначе нельзя проверить именно
# нераспределённую прибыль, а не весь капитал, см. 3_cross_check.py).
ADVANCED_REQUIRED = BASIC_REQUIRED + [
    "company_id", "period", "cogs", "inventory", "short_term_debt", "long_term_debt",
    "total_liabilities", "retained_earnings", "payables", "cash_from_customers",
    "payments_to_suppliers", "operating_cash_flow", "investing_cash_flow",
    "financing_cash_flow", "dividends", "new_borrowings", "debt_repayments",
]


def score_transactions(txn_df: pd.DataFrame) -> dict:
    """Stage 2: анализ транзакций ЗАГРУЖЕННОЙ моделью (без переобучения)."""
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
            unusual_hour=int(pd.to_datetime(r["txn_timestamp"]).hour < 6 or pd.to_datetime(r["txn_timestamp"]).hour > 22),
        ))
    feats_df = pd.DataFrame(feats)
    decision = anomaly_model.decision_function(feats_df[anomaly_features])
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


def read_uploaded_file(file: UploadFile) -> pd.DataFrame:
    filename = (file.filename or "").lower()
    if filename.endswith(".csv"):
        return pd.read_csv(file.file), filename
    if filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(file.file), filename
    if filename.endswith(".pdf"):
        parsed = pdf_parser.parse_pdf_report(file.file)
        missing = [k for k, v in parsed.items() if v is None]
        if missing:
            return {"error": f"Не удалось автоматически распознать в PDF показатели: {missing}. "
                              f"Загрузите Excel/CSV вручную.", "parsed_so_far": parsed}, filename
        return pd.DataFrame([parsed]), filename
    return {"error": "Поддерживаются только CSV, XLSX/XLS или PDF."}, filename


def analyze_company_df(df: pd.DataFrame, company_name: str, requested_limit: float,
                        txn_df: pd.DataFrame = None, source_type: str = "table") -> dict:
    """Считает полный риск-отчёт по ОДНОЙ компании (df — её строки/периоды).
    Общая логика для /analyze (один файл = одна компания) и /analyze-batch
    (один файл = много компаний, эта функция вызывается по одной на группу)."""
    # В ADVANCED-файлах долг обычно разбит на краткосрочный и долгосрочный —
    # выводим единое поле "debt" автоматически для Stage 1.
    if "debt" not in df.columns and {"short_term_debt", "long_term_debt"} <= set(df.columns):
        df["debt"] = df["short_term_debt"] + df["long_term_debt"]

    missing_basic = [c for c in BASIC_REQUIRED if c not in df.columns]
    if missing_basic:
        return {"error": f"В файле отсутствуют обязательные колонки: {missing_basic}. "
                          f"Ожидаются ровно такие названия: {BASIC_REQUIRED}"}

    is_advanced = all(c in df.columns for c in ADVANCED_REQUIRED) and len(df) >= 1
    resolved_name = company_name or (str(df["company_id"].iloc[-1]) if "company_id" in df.columns else "Компания")

    if "company_id" not in df.columns:
        df["company_id"] = 1
    if "period" not in df.columns:
        df["period"] = pd.Timestamp.now()

    ratios = fh.compute_ratios(df)
    fh_result = fh.financial_health_score(ratios.iloc[-1])
    financial_score = fh_result["financial_score"]

    anomaly_result = score_transactions(txn_df) if txn_df is not None else \
        {"anomaly_score": 30, "top_factors_anomaly": ["файл транзакций не загружен"]}

    cross_result = None
    if is_advanced:
        cross_result = cross_check.run_cross_checks(df)
        history_scores = ratios.apply(fh.financial_health_score, axis=1, result_type="expand")
        history_df = pd.concat([ratios[["period"]], history_scores], axis=1)
        forecast_row = forecast_mod.forecast_company(history_df)
    else:
        forecast_row = {"forecast_3m": financial_score, "forecast_6m": financial_score,
                         "forecast_12m": financial_score}

    pd_input = pd.DataFrame([[financial_score, anomaly_result["anomaly_score"]]], columns=pd_features)
    pd_value = float(pd_model.predict_proba(pd_input)[0, 1])

    report = risk_engine.build_company_report(
        company_id=resolved_name, financial_row=fh_result, anomaly_row=anomaly_result,
        forecast_row=forecast_row, pd_row={"pd_12m": pd_value},
        requested_limit=requested_limit, cross_check_result=cross_result,
    )
    report["company_name"] = resolved_name
    report["source_type"] = source_type
    report["periods_loaded"] = len(df)
    if not is_advanced:
        report["note"] = ("Загружен BASIC-режим (один период, 11 показателей). Прогноз и "
                           "cross-check недоступны без истории и расширенных полей — см. "
                           "report_template_advanced.xlsx для полного режима.")
    return report


@app.post("/analyze")
async def analyze_company(file: UploadFile, company_name: str = Form(None),
                           transactions_file: UploadFile = None,
                           requested_limit: float = Form(60_000_000)):
    df, filename = read_uploaded_file(file)
    if isinstance(df, dict):  # ошибка чтения файла (см. read_uploaded_file)
        return df

    # /analyze — строго одна компания. Если в файле несколько company_id,
    # просим воспользоваться /analyze-batch вместо того, чтобы гадать,
    # какую компанию анализировать.
    if "company_id" in df.columns and df["company_id"].nunique() > 1:
        return {"error": f"Файл содержит {df['company_id'].nunique()} разных компаний "
                          f"({sorted(df['company_id'].unique().tolist())}). Для одновременного "
                          f"анализа нескольких компаний используйте /analyze-batch — он принимает "
                          f"файл со всеми компаниями сразу и возвращает список отчётов."}

    txn_df = pd.read_csv(transactions_file.file) if transactions_file is not None else None
    source_type = "pdf" if filename.endswith(".pdf") else "table"
    return analyze_company_df(df, company_name, requested_limit, txn_df, source_type)


@app.post("/analyze-batch")
async def analyze_batch(file: UploadFile, requested_limit: float = Form(60_000_000)):
    """Принимает ОДИН файл сразу с несколькими компаниями (например, все 20
    компаний с KASE, каждая по 2-3 периода — ровно так, как удобно вести
    данные в report_template_advanced.xlsx). Колонка company_id обязательна:
    по ней файл делится на группы, и каждая компания анализируется отдельно
    той же самой функцией, что и обычный /analyze — результат идентичен
    построчной загрузке по одной, просто за один запрос.
    PDF здесь не поддерживается — только CSV/Excel с company_id."""
    df, filename = read_uploaded_file(file)
    if isinstance(df, dict):
        return df
    if filename.endswith(".pdf"):
        return {"error": "/analyze-batch не поддерживает PDF — нужен CSV или Excel с колонкой company_id."}
    if "company_id" not in df.columns:
        return {"error": "Для пакетного анализа обязательна колонка company_id — по ней файл "
                          "делится на компании."}

    results = []
    for company_id, group in df.groupby("company_id", sort=False):
        group = group.sort_values("period") if "period" in group.columns else group
        report = analyze_company_df(group.copy(), company_name=str(company_id),
                                     requested_limit=requested_limit, txn_df=None,
                                     source_type="table")
        results.append(report)

    return {
        "companies_count": len(results),
        "results": results,
        "summary": {
            "LOW": sum(1 for r in results if r.get("risk_level") == "LOW"),
            "MEDIUM": sum(1 for r in results if r.get("risk_level") == "MEDIUM"),
            "HIGH": sum(1 for r in results if r.get("risk_level") == "HIGH"),
            "errors": sum(1 for r in results if "error" in r),
        },
    }
