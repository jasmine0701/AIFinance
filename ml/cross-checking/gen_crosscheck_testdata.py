"""
Генератор тестовых данных для cross-check: строит 3 компании (CLEAN,
WARNING, HIGH_MISMATCH) по 3 периода (2023, 2024, 2025), где все цифры
математически согласованы между собой (либо намеренно "сломаны" для
демонстрации). Используется для проверки модуля 3_cross_check.py и как
готовые демо-файлы для защиты (раздел 18 плана: 3 обязательных демо-кейса).
"""
import pandas as pd
import numpy as np

np.random.seed(7)


def build_period(prev, revenue, cogs, net_profit, dividends, new_borrowings,
                  debt_repayments, capex, ar_growth, inv_growth, ap_growth,
                  cfo_override=None, break_rule=None, break_amount=0):
    """Строит ОДНУ следующую строку (конец периода) из состояния prev (начало
    периода), гарантируя, что все 5 обязательных тождеств выполняются точно
    — если только break_rule не просит специально что-то испортить."""
    ar_end = prev["receivables"] * (1 + ar_growth)
    customer_cash = revenue + prev["receivables"] - ar_end   # ⇒ revenue_receivables_cash сходится точно

    inv_end = prev["inventory"] * (1 + inv_growth)
    purchases = cogs + inv_end - prev["inventory"]
    ap_end = prev["payables"] * (1 + ap_growth)
    payments_to_suppliers = purchases + prev["payables"] - ap_end  # ⇒ purchases_payables_cash сходится точно

    cfo = cfo_override if cfo_override is not None else net_profit * 1.05  # небольшая неденежная поправка
    cfi = -capex
    cff = new_borrowings - debt_repayments - dividends
    cash_end = prev["cash"] + cfo + cfi + cff                 # ⇒ cash_rollforward сходится точно

    debt_begin = prev["short_term_debt"] + prev["long_term_debt"]
    debt_end = debt_begin + new_borrowings - debt_repayments  # ⇒ debt_rollforward сходится точно
    short_term_debt = debt_end * 0.3
    long_term_debt = debt_end * 0.7

    retained_earnings = prev["retained_earnings"] + net_profit - dividends  # ⇒ RE rollforward сходится точно
    equity = prev["equity"] + net_profit - dividends                        # ⇒ equity_broad тоже сходится (CLEAN)

    payables = ap_end
    current_liabilities = short_term_debt + payables
    total_liabilities = current_liabilities + long_term_debt

    assets = total_liabilities + equity                        # ⇒ balance_equation сходится точно
    current_assets = cash_end + ar_end + inv_end                # ⇒ current_assets_components сходится точно (сумма == итог)

    operating_profit = revenue - cogs - revenue * 0.12
    ebitda = operating_profit + revenue * 0.02

    row = dict(
        revenue=revenue, cogs=cogs, operating_profit=operating_profit, ebitda=ebitda,
        net_profit=net_profit, cash=cash_end, receivables=ar_end, inventory=inv_end,
        current_assets=current_assets, assets=assets, payables=payables,
        short_term_debt=short_term_debt, long_term_debt=long_term_debt,
        current_liabilities=current_liabilities, total_liabilities=total_liabilities,
        equity=equity, retained_earnings=retained_earnings,
        cash_from_customers=customer_cash, payments_to_suppliers=payments_to_suppliers,
        operating_cash_flow=cfo, investing_cash_flow=cfi, financing_cash_flow=cff,
        capex=capex, dividends=dividends, new_borrowings=new_borrowings,
        debt_repayments=debt_repayments, fx_effect=0.0,
    )

    # --- намеренная порча одного показателя для демо WARNING / HIGH ---
    if break_rule == "cash":       # "деньги" разъезжаются с ОДДС
        row["cash"] += break_amount
        row["current_assets"] += break_amount
        row["assets"] += break_amount
    elif break_rule == "debt":     # долг на конец не объясняется выдачей/погашением
        row["long_term_debt"] += break_amount
        row["total_liabilities"] += break_amount
        row["assets"] += break_amount
    elif break_rule == "retained_earnings":  # нераспределённая прибыль не сходится
        row["retained_earnings"] += break_amount
        row["equity"] += break_amount
        row["assets"] += break_amount

    return row


def base_period():
    return dict(cash=60_000, receivables=90_000, inventory=70_000, payables=44_000,
                short_term_debt=75_000, long_term_debt=175_000, equity=500_000,
                retained_earnings=220_000)


def build_company(name, industry, break_schedule):
    """break_schedule: {2024: (rule, amount), 2025: (rule, amount)} — что
    сломать в конкретном периоде, либо None/0 если не ломать (CLEAN)."""
    rows = []
    state = base_period()
    periods = [("2023-12-31", 700_000, 470_000, 55_000, 10_000, 40_000, 25_000, 30_000),
               ("2024-12-31", 760_000, 505_000, 60_000, 12_000, 45_000, 30_000, 32_000),
               ("2025-12-31", 820_000, 545_000, 65_000, 13_000, 50_000, 35_000, 35_000)]
    for period, revenue, cogs, net_profit, dividends, new_borrowings, debt_repayments, capex in periods:
        year = int(period[:4])
        break_rule, break_amount = break_schedule.get(year, (None, 0))
        row = build_period(state, revenue, cogs, net_profit, dividends, new_borrowings,
                            debt_repayments, capex, ar_growth=0.06, inv_growth=0.05, ap_growth=0.04,
                            break_rule=break_rule, break_amount=break_amount)
        row["company_id"] = name
        row["industry"] = industry
        row["period"] = period
        rows.append(row)
        # state на следующий период = "конец" текущего периода, БЕЗ порчи —
        # иначе ошибка накопится на все последующие периоды искусственно
        clean_row = build_period(state, revenue, cogs, net_profit, dividends, new_borrowings,
                                  debt_repayments, capex, ar_growth=0.06, inv_growth=0.05, ap_growth=0.04)
        state = clean_row
    return pd.DataFrame(rows)


if __name__ == "__main__":
    clean = build_company("CLEAN Co", "Trade", {})
    warning = build_company("WARNING Co", "Manufacturing", {2025: ("retained_earnings", 35_000)})
    high = build_company("HIGH MISMATCH Co", "Construction", {2025: ("debt", 310_000)})

    all_df = pd.concat([clean, warning, high], ignore_index=True)
    cols = ["company_id", "industry", "period", "revenue", "cogs", "operating_profit", "ebitda",
            "net_profit", "cash", "receivables", "inventory", "current_assets", "assets",
            "payables", "short_term_debt", "long_term_debt", "current_liabilities",
            "total_liabilities", "equity", "retained_earnings", "cash_from_customers",
            "payments_to_suppliers", "operating_cash_flow", "investing_cash_flow",
            "financing_cash_flow", "capex", "dividends", "new_borrowings", "debt_repayments", "fx_effect"]
    all_df = all_df[cols]
    all_df.to_csv("../data/test_crosscheck.csv", index=False)
    print(f"Сохранено data/test_crosscheck.csv: {len(all_df)} строк, {all_df['company_id'].nunique()} компании")
    print(all_df[["company_id", "period", "assets", "total_liabilities", "equity"]])
