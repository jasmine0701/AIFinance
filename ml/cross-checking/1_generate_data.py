"""
FinGuard AI — Шаг 1: генерация данных.

ЛОГИКА (гибрид, как обсуждали):
  - REAL_KASE_COMPANIES  — сюда вручную вбиваются реальные цифры 2-3 компаний
    из раскрытия информации KASE (kase.kz -> Раскрытие информации -> нужный эмитент
    -> финансовая отчетность за последние кварталы). Это даёт продукту доверие
    ("мы считаем реальные коэффициенты по реальной компании").
  - SYNTHETIC — остальные компании, включая 2-3 "сценарных" (гарантированный
    HIGH RISK для демо) — потому что нужного разброса кейсов в 2-3 реальных
    компаниях гарантированно не будет.
  - Транзакции — 100% синтетика (публичных банковских транзакций не существует).

Итог: таблицы companies / financial_statements / counterparties / transactions
в виде CSV в ./data/ — их же можно напрямую загрузить в Postgres через \copy.
"""

import numpy as np
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
import os

np.random.seed(42)
OUT = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT, exist_ok=True)

PERIODS = [date(2023, 3, 31) + relativedelta(months=3 * i) for i in range(12)]  # 3 года по кварталам

# -------------------------------------------------------------------
# 1. РЕАЛЬНЫЕ КОМПАНИИ (заполняет Person 2 вручную цифрами с kase.kz)
# -------------------------------------------------------------------
# ВАЖНО: это шаблон. Замените числа на реальные из отчётности эмитента.
# Единицы — тыс. KZT. Если по компании нет всех 12 кварталов — оставьте
# сколько есть, код ниже сам подстроится под длину списка.
REAL_KASE_COMPANIES = [
    {
        "name": "<Название эмитента с KASE>",
        "industry": "Energy",           # смотрите ОКЭД эмитента
        "size_category": "Large",
        # каждая запись — один квартал, в хронологическом порядке
        "quarters": [
            # {"revenue": ..., "ebitda": ..., "net_profit": ..., "debt": ...,
            #  "cash": ..., "current_assets": ..., "current_liabilities": ...,
            #  "receivables": ..., "payables": ..., "equity": ..., "assets": ...}
        ],
    },
    # добавьте ещё 1-2 компании по этому же шаблону
]

# -------------------------------------------------------------------
# 2. СИНТЕТИЧЕСКИЕ "ОБЫЧНЫЕ" КОМПАНИИ — стабильный/слегка колеблющийся бизнес
# -------------------------------------------------------------------
INDUSTRIES = ["Trade", "Construction", "Manufacturing", "Logistics", "Agriculture"]

def gen_stable_company(name, industry):
    base_revenue = np.random.uniform(200_000, 900_000)   # тыс. KZT в квартал
    rows = []
    revenue = base_revenue
    debt = base_revenue * np.random.uniform(0.3, 0.6)
    for p in PERIODS:
        revenue *= 1 + np.random.normal(0.01, 0.04)       # лёгкий рост/шум
        ebitda = revenue * np.random.uniform(0.12, 0.22)
        net_profit = ebitda * np.random.uniform(0.4, 0.7)
        debt *= 1 + np.random.normal(0.0, 0.03)
        cash = revenue * np.random.uniform(0.05, 0.15)
        current_assets = revenue * np.random.uniform(0.35, 0.55)
        current_liabilities = revenue * np.random.uniform(0.2, 0.4)
        receivables = revenue * np.random.uniform(0.1, 0.2)
        payables = revenue * np.random.uniform(0.08, 0.18)
        equity = debt * np.random.uniform(0.8, 1.4)
        assets = current_assets + equity * np.random.uniform(1.2, 1.6)
        rows.append(dict(period=p, revenue=revenue, ebitda=ebitda, net_profit=net_profit,
                          debt=debt, cash=cash, current_assets=current_assets,
                          current_liabilities=current_liabilities, receivables=receivables,
                          payables=payables, equity=equity, assets=assets))
    return {"name": name, "industry": industry, "size_category": "SME",
            "data_source": "synthetic_normal", "quarters": rows}

# -------------------------------------------------------------------
# 3. СИНТЕТИЧЕСКИЕ "СЦЕНАРНЫЕ" КОМПАНИИ — управляемое ухудшение для демо
# -------------------------------------------------------------------
def gen_deteriorating_company(name, industry):
    """Ровно тот кейс из ТЗ: revenue -24%, debt +31%, AR +42% и т.д."""
    base_revenue = np.random.uniform(300_000, 700_000)
    rows = []
    revenue = base_revenue
    debt = base_revenue * 0.35
    receivables = revenue * 0.12
    n = len(PERIODS)
    for i, p in enumerate(PERIODS):
        # последние 4 квартала — явная деградация
        stress = i >= n - 4
        revenue *= (1 - np.random.uniform(0.05, 0.08)) if stress else (1 + np.random.normal(0.01, 0.03))
        debt *= (1 + np.random.uniform(0.06, 0.1)) if stress else (1 + np.random.normal(0.0, 0.02))
        receivables *= (1 + np.random.uniform(0.08, 0.13)) if stress else (1 + np.random.normal(0.01, 0.03))
        ebitda = revenue * (np.random.uniform(0.02, 0.08) if stress else np.random.uniform(0.12, 0.2))
        net_profit = ebitda * 0.5 if not stress else ebitda * 0.1
        cash = revenue * (0.03 if stress else 0.1)
        current_assets = revenue * 0.4
        current_liabilities = revenue * (0.45 if stress else 0.25)  # current ratio падает
        payables = revenue * (0.2 if stress else 0.1)
        equity = debt * 0.9
        assets = current_assets + equity * 1.3
        rows.append(dict(period=p, revenue=revenue, ebitda=ebitda, net_profit=net_profit,
                          debt=debt, cash=cash, current_assets=current_assets,
                          current_liabilities=current_liabilities, receivables=receivables,
                          payables=payables, equity=equity, assets=assets))
    return {"name": name, "industry": industry, "size_category": "SME",
            "data_source": "synthetic_scenario", "quarters": rows}

def build_companies():
    companies = []
    for c in REAL_KASE_COMPANIES:
        if c["quarters"]:  # только если данные реально вбиты
            c["data_source"] = "real_kase"
            companies.append(c)
    for i in range(6):
        companies.append(gen_stable_company(f"LLP Stable-{i+1}", np.random.choice(INDUSTRIES)))
    for i in range(3):
        companies.append(gen_deteriorating_company(f"LLP HighRisk-{i+1}", np.random.choice(INDUSTRIES)))
    return companies

def companies_to_frames(companies):
    comp_rows, fin_rows = [], []
    for cid, c in enumerate(companies, start=1):
        comp_rows.append(dict(company_id=cid, name=c["name"], industry=c["industry"],
                               size_category=c["size_category"], data_source=c.get("data_source", "synthetic")))
        for q in c["quarters"]:
            row = dict(q)
            row["company_id"] = cid
            fin_rows.append(row)
    return pd.DataFrame(comp_rows), pd.DataFrame(fin_rows)

# -------------------------------------------------------------------
# 4. ТРАНЗАКЦИИ — синтетика поверх всех компаний, с инъекцией аномалий
# -------------------------------------------------------------------
def gen_transactions(companies_df):
    counterparties = []
    for i in range(40):
        counterparties.append(dict(counterparty_id=i + 1,
                                    name=f"Counterparty-{i+1}",
                                    industry=np.random.choice(INDUSTRIES),
                                    country="KZ" if np.random.rand() > 0.15 else "Other",
                                    first_seen_date=date(2022, 1, 1)))
    cp_df = pd.DataFrame(counterparties)

    txns = []
    txn_id = 1
    for _, comp in companies_df.iterrows():
        regular_cps = np.random.choice(cp_df["counterparty_id"], size=8, replace=False)
        base_amount = np.random.uniform(500, 5000)  # тыс. KZT, типичная транзакция
        n_txn = np.random.randint(60, 120)
        timestamps = pd.date_range("2025-01-01", "2025-09-01", periods=n_txn)
        for ts in timestamps:
            amount = np.random.lognormal(mean=np.log(base_amount), sigma=0.4)
            cp_id = np.random.choice(regular_cps)
            txns.append(dict(txn_id=txn_id, company_id=comp["company_id"], counterparty_id=cp_id,
                              txn_timestamp=ts, amount=amount,
                              direction=np.random.choice(["in", "out"]),
                              channel=np.random.choice(["bank_transfer", "card"], p=[0.85, 0.15])))
            txn_id += 1

        # --- инъекция аномалий: 3-5 подозрительных транзакций на компанию ---
        for _ in range(np.random.randint(3, 6)):
            new_cp = np.random.choice(cp_df["counterparty_id"])   # часто "новый" контрагент
            odd_ts = pd.Timestamp("2025-08-15") + pd.Timedelta(hours=int(np.random.uniform(0, 400)))
            amount = base_amount * np.random.uniform(6, 12)        # аномально крупная сумма
            txns.append(dict(txn_id=txn_id, company_id=comp["company_id"], counterparty_id=new_cp,
                              txn_timestamp=odd_ts, amount=amount,
                              direction="out", channel="bank_transfer"))
            txn_id += 1
    return cp_df, pd.DataFrame(txns)

if __name__ == "__main__":
    companies = build_companies()
    comp_df, fin_df = companies_to_frames(companies)
    cp_df, txn_df = gen_transactions(comp_df)

    comp_df.to_csv(f"{OUT}/companies.csv", index=False)
    fin_df.to_csv(f"{OUT}/financial_statements.csv", index=False)
    cp_df.to_csv(f"{OUT}/counterparties.csv", index=False)
    txn_df.to_csv(f"{OUT}/transactions.csv", index=False)

    print(f"Готово: {len(comp_df)} компаний, {len(fin_df)} финансовых записей, "
          f"{len(txn_df)} транзакций. Файлы сохранены в {OUT}/")
