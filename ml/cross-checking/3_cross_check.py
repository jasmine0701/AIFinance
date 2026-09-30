"""
FinGuard AI — Cross-Checking Engine (проверка согласованности отчётности).

ЗАЧЕМ. Прежде чем считать риск по цифрам компании, нужно убедиться, что
цифры сами по себе не противоречат друг другу — иначе риск считается по
"грязным" данным. Это стандартная практика кредитного анализа: аналитик
сначала "сшивает" баланс, ОПиУ и ОДДС между собой, и только потом делает
выводы.

ЧТО ПРОВЕРЯЕМ (5 обязательных правил, требования проекта):
  1. Баланс сходится НА НАЧАЛО периода:  Активы(начало) = Обязательства(начало) + Капитал(начало)
  2. Баланс сходится НА КОНЕЦ периода:   Активы(конец)  = Обязательства(конец)  + Капитал(конец)
  3. Деньги в балансе = деньги по ОДДС:  Cash(конец, баланс) = Cash(начало) + CFO + CFI + CFF (+ FX)
  4. Нераспределённая прибыль:           RE(конец) = RE(начало) + Чистая прибыль(ОПиУ) − Дивиденды(ОДДС)
  5. Остаток займов:                     Долг(конец) = Долг(начало) + Выдача займов(ОДДС) − Погашение(ОДДС)

Плюс несколько дополнительных, менее строгих проверок (расширение от GPT,
проверено и оставлено как полезное, но не обязательное дополнение):
  - структура оборотных активов (cash+receivables+inventory ≤ current_assets)
  - выручка ↔ поступления от покупателей ↔ дебиторка
  - закупки ↔ оплата поставщикам ↔ кредиторка/запасы
  - чистая прибыль ↔ операционный денежный поток (не равенство, а сигнал)
  - изменение чистого оборотного капитала

ВАЖНОЕ ОГРАНИЧЕНИЕ, которое нужно проговаривать на защите: расхождение
не всегда означает ошибку в отчёте — возможны НДС, авансы, курсовые
разницы, неденежные статьи, переклассификации. Cross-checking — это
"требует проверки аналитиком", а не доказательство фальсификации.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd


@dataclass
class CheckResult:
    name: str
    status: str          # PASS / WARN / FAIL / SKIP
    score: float          # 0 = хорошо (сходится), 100 = плохо (крупное расхождение)
    difference: Optional[float]
    difference_pct: Optional[float]
    message: str
    details: Dict[str, Any]


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def _safe_float(x):
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return None
        return float(x)
    except Exception:
        return None


def _relative_gap(actual, expected):
    """Возвращает (абсолютную разницу, относительную разницу) между
    фактическим и ожидаемым значением. Знаменатель — max(|actual|,|expected|,1),
    чтобы не делить на ноль и не давать гигантский % на маленьких суммах."""
    actual = _safe_float(actual)
    expected = _safe_float(expected)
    if actual is None or expected is None:
        return None, None
    diff = actual - expected
    denom = max(abs(actual), abs(expected), 1.0)
    return diff, diff / denom


def _gap_score(diff_pct: Optional[float], warn: float, fail: float) -> float:
    """Переводит относительное расхождение в шкалу 0..100.
    До warn% — почти 0 (PASS). От warn% до fail% — линейный рост (WARN).
    После fail% — максимум, 100 (FAIL)."""
    if diff_pct is None or not np.isfinite(diff_pct):
        return 50.0  # данных недостаточно — нейтральная неопределённость
    x = abs(diff_pct)
    if x <= warn:
        return min(20.0, x / warn * 20.0) if warn > 0 else 0.0
    if x >= fail:
        return 100.0
    return 20.0 + (x - warn) / (fail - warn) * 80.0


def _status(score: float) -> str:
    if score < 20:
        return "PASS"
    if score < 60:
        return "WARN"
    return "FAIL"


# ---------------------------------------------------------------------------
# ОБЯЗАТЕЛЬНОЕ ПРАВИЛО 1 и 2: балансовое равенство, НАЧАЛО и КОНЕЦ периода
# ---------------------------------------------------------------------------
def check_balance_equation(row: pd.Series, when: str) -> CheckResult:
    """when: 'begin' или 'end' — на какую дату проверяем.
    Допуск строже, чем у остальных правил (0.5% / 2%), потому что это
    базовое бухгалтерское тождество, а не оценочное соотношение — оно
    обязано сходиться почти всегда."""
    assets = _safe_float(row.get("assets"))
    liabilities = _safe_float(row.get("total_liabilities"))
    equity = _safe_float(row.get("equity"))
    name = f"balance_equation_{when}"

    if None in (assets, liabilities, equity):
        return CheckResult(name, "SKIP", 50, None, None,
            f"Недостаточно данных для Активы = Обязательства + Капитал ({when})", {})

    expected = liabilities + equity
    diff, pct = _relative_gap(assets, expected)
    score = _gap_score(pct, warn=0.005, fail=0.02)
    label = "начало периода" if when == "begin" else "конец периода"
    return CheckResult(
        name, _status(score), score, diff, pct,
        f"Баланс на {label}: Активы должны быть равны Обязательствам + Капиталу. Расхождение: {diff:,.0f}",
        {"assets": assets, "liabilities_plus_equity": expected, "period": when},
    )


# ---------------------------------------------------------------------------
# ОБЯЗАТЕЛЬНОЕ ПРАВИЛО 3: деньги в балансе = деньги по ОДДС
# ---------------------------------------------------------------------------
def check_cash_rollforward(prev: pd.Series, cur: pd.Series) -> CheckResult:
    cash_begin = _safe_float(prev.get("cash"))
    cash_end = _safe_float(cur.get("cash"))
    cfo = _safe_float(cur.get("operating_cash_flow"))
    cfi = _safe_float(cur.get("investing_cash_flow"))
    cff = _safe_float(cur.get("financing_cash_flow"))
    fx = _safe_float(cur.get("fx_effect")) or 0.0

    if None in (cash_begin, cash_end, cfo, cfi, cff):
        return CheckResult("cash_rollforward", "SKIP", 50, None, None,
            "Недостаточно данных для движения денежных средств (ОДДС)", {})

    expected = cash_begin + cfo + cfi + cff + fx
    diff, pct = _relative_gap(cash_end, expected)
    score = _gap_score(pct, warn=0.01, fail=0.05)
    return CheckResult(
        "cash_rollforward", _status(score), score, diff, pct,
        f"Деньги в балансе на конец периода должны равняться деньгам на начало плюс "
        f"движение по ОДДС (операционная + инвестиционная + финансовая деятельность). "
        f"Расхождение: {diff:,.0f}",
        {"cash_end_balance": cash_end, "expected_cash_end": expected},
    )


# ---------------------------------------------------------------------------
# ОБЯЗАТЕЛЬНОЕ ПРАВИЛО 4: нераспределённая прибыль (НЕ весь капитал!)
# ---------------------------------------------------------------------------
def check_retained_earnings_rollforward(prev: pd.Series, cur: pd.Series) -> CheckResult:
    """RE(конец) = RE(начало) + Чистая прибыль(ОПиУ, отчётный год) − Дивиденды(ОДДС, отчётный год).

    ВАЖНО: используется отдельное поле retained_earnings (нераспределённая
    прибыль), а не equity (весь капитал). Это то самое исправление ошибки
    из предложения GPT — весь капитал включает ещё уставный капитал,
    эмиссионный доход, резервы переоценки и т.д., которые эта формула не
    описывает и которые дадут ложное расхождение."""
    re_begin = _safe_float(prev.get("retained_earnings"))
    re_end = _safe_float(cur.get("retained_earnings"))
    net_profit = _safe_float(cur.get("net_profit"))
    dividends = _safe_float(cur.get("dividends")) or 0.0

    if None in (re_begin, re_end, net_profit):
        return CheckResult("retained_earnings_rollforward", "SKIP", 50, None, None,
            "Недостаточно данных для движения нераспределённой прибыли "
            "(нужно поле retained_earnings за оба периода)", {})

    expected = re_begin + net_profit - dividends
    diff, pct = _relative_gap(re_end, expected)
    score = _gap_score(pct, warn=0.02, fail=0.10)
    return CheckResult(
        "retained_earnings_rollforward", _status(score), score, diff, pct,
        f"Нераспределённая прибыль на конец периода должна равняться нераспределённой "
        f"прибыли на начало плюс чистая прибыль за год (ОПиУ) минус дивиденды за год (ОДДС). "
        f"Расхождение: {diff:,.0f}",
        {"retained_earnings_end": re_end, "expected_retained_earnings_end": expected,
         "net_profit": net_profit, "dividends": dividends},
    )


def check_equity_rollforward_broad(prev: pd.Series, cur: pd.Series) -> CheckResult:
    """Дополнительная, более мягкая проверка ВСЕГО капитала той же формулой.
    Оставлена как вторичный сигнал (низкий вес): если она не сходится, а
    retained_earnings_rollforward сходится — это нормально, значит было
    движение по другим статьям капитала (допэмиссия, переоценка), а не
    ошибка. Если не сходятся ОБЕ — это более серьёзный сигнал."""
    eq_begin = _safe_float(prev.get("equity"))
    eq_end = _safe_float(cur.get("equity"))
    net_profit = _safe_float(cur.get("net_profit"))
    dividends = _safe_float(cur.get("dividends")) or 0.0

    if None in (eq_begin, eq_end, net_profit):
        return CheckResult("equity_rollforward_broad", "SKIP", 50, None, None,
            "Недостаточно данных для движения капитала", {})

    expected = eq_begin + net_profit - dividends
    diff, pct = _relative_gap(eq_end, expected)
    score = _gap_score(pct, warn=0.05, fail=0.25)  # допуск шире: капитал законно меняется и от других причин
    return CheckResult(
        "equity_rollforward_broad", _status(score), score, diff, pct,
        f"Справочно: капитал на конец vs капитал на начало + прибыль − дивиденды "
        f"(без учёта допэмиссий/переоценки). Расхождение: {diff:,.0f}",
        {"equity_end": eq_end, "expected_equity_end": expected},
    )


# ---------------------------------------------------------------------------
# ОБЯЗАТЕЛЬНОЕ ПРАВИЛО 5: остаток займов (кратко- + долгосрочные вместе)
# ---------------------------------------------------------------------------
def check_debt_rollforward(prev: pd.Series, cur: pd.Series) -> CheckResult:
    debt_begin = (_safe_float(prev.get("short_term_debt")) or 0) + (_safe_float(prev.get("long_term_debt")) or 0)
    debt_end = (_safe_float(cur.get("short_term_debt")) or 0) + (_safe_float(cur.get("long_term_debt")) or 0)
    new_borrowings = _safe_float(cur.get("new_borrowings"))
    repayments = _safe_float(cur.get("debt_repayments"))

    if new_borrowings is None or repayments is None:
        return CheckResult("debt_rollforward", "SKIP", 50, None, None,
            "Недостаточно данных по выдаче/погашению займов (ОДДС)", {})

    expected = debt_begin + new_borrowings - repayments
    diff, pct = _relative_gap(debt_end, expected)
    score = _gap_score(pct, warn=0.03, fail=0.15)
    return CheckResult(
        "debt_rollforward", _status(score), score, diff, pct,
        f"Остаток займов (кратко- + долгосрочных) на конец периода должен равняться остатку "
        f"на начало плюс выдача займов минус погашение займов за период (по ОДДС). "
        f"Расхождение: {diff:,.0f}",
        {"debt_end": debt_end, "expected_debt_end": expected},
    )


# ---------------------------------------------------------------------------
# ДОПОЛНИТЕЛЬНЫЕ, НЕОБЯЗАТЕЛЬНЫЕ проверки (полезные, но не бухгалтерские тождества)
# ---------------------------------------------------------------------------
def check_current_assets_components(row: pd.Series) -> CheckResult:
    ca = _safe_float(row.get("current_assets"))
    components = [_safe_float(row.get("cash")), _safe_float(row.get("receivables")), _safe_float(row.get("inventory"))]
    if ca is None or any(c is None for c in components):
        return CheckResult("current_assets_components", "SKIP", 50, None, None,
            "Недостаточно данных для структуры оборотных активов", {})
    comp_sum = sum(components)
    if comp_sum <= ca:
        return CheckResult("current_assets_components", "PASS", 0, ca - comp_sum, 0,
            "Cash + Receivables + Inventory не превышают итог оборотных активов", {})
    diff = comp_sum - ca
    pct = diff / max(abs(ca), 1.0)
    score = _gap_score(pct, warn=0.01, fail=0.10)
    return CheckResult("current_assets_components", _status(score), score, diff, pct,
        "Сумма Cash + Receivables + Inventory превышает итог оборотных активов — проверьте состав статей",
        {"current_assets": ca, "known_components": comp_sum})


def check_revenue_receivables_cash(prev: pd.Series, cur: pd.Series) -> CheckResult:
    revenue = _safe_float(cur.get("revenue"))
    ar_begin = _safe_float(prev.get("receivables"))
    ar_end = _safe_float(cur.get("receivables"))
    customer_cash = _safe_float(cur.get("cash_from_customers"))
    if None in (revenue, ar_begin, ar_end, customer_cash):
        return CheckResult("revenue_receivables_cash", "SKIP", 50, None, None,
            "Недостаточно данных для Выручка ↔ Дебиторка ↔ Поступления", {})
    expected_cash = revenue + ar_begin - ar_end
    diff, pct = _relative_gap(customer_cash, expected_cash)
    score = _gap_score(pct, warn=0.05, fail=0.20)
    return CheckResult("revenue_receivables_cash", _status(score), score, diff, pct,
        f"Поступления от покупателей ожидаются как Выручка + Дебиторка(начало) − Дебиторка(конец). Расхождение: {diff:,.0f}",
        {"customer_cash": customer_cash, "expected_customer_cash": expected_cash})


def check_purchases_payables_cash(prev: pd.Series, cur: pd.Series) -> CheckResult:
    cogs = _safe_float(cur.get("cogs"))
    inv_begin = _safe_float(prev.get("inventory")); inv_end = _safe_float(cur.get("inventory"))
    ap_begin = _safe_float(prev.get("payables")); ap_end = _safe_float(cur.get("payables"))
    paid = _safe_float(cur.get("payments_to_suppliers"))
    if None in (cogs, inv_begin, inv_end, ap_begin, ap_end, paid):
        return CheckResult("purchases_payables_cash", "SKIP", 50, None, None,
            "Недостаточно данных для Себестоимость ↔ Запасы ↔ Кредиторка", {})
    purchases = cogs + inv_end - inv_begin
    expected_paid = purchases + ap_begin - ap_end
    diff, pct = _relative_gap(paid, expected_paid)
    score = _gap_score(pct, warn=0.05, fail=0.20)
    return CheckResult("purchases_payables_cash", _status(score), score, diff, pct,
        f"Оплата поставщикам ожидается как Закупки + Кредиторка(начало) − Кредиторка(конец). Расхождение: {diff:,.0f}",
        {"payments_to_suppliers": paid, "expected_payments": expected_paid})


def check_profit_vs_cfo(cur: pd.Series) -> CheckResult:
    profit = _safe_float(cur.get("net_profit"))
    cfo = _safe_float(cur.get("operating_cash_flow"))
    if profit is None or cfo is None:
        return CheckResult("profit_vs_cfo", "SKIP", 50, None, None,
            "Недостаточно данных для Чистая прибыль ↔ Операционный денежный поток", {})
    denom = max(abs(profit), abs(cfo), 1.0)
    pct = abs(cfo - profit) / denom
    score = min(100.0, pct * 100.0)
    status = "PASS" if pct < 0.30 else ("WARN" if pct < 0.70 else "FAIL")
    return CheckResult("profit_vs_cfo", status, score, cfo - profit, pct,
        "Сильное расхождение прибыли и операционного денежного потока не является ошибкой "
        "само по себе, но требует объяснения оборотным капиталом и неденежными статьями",
        {"net_profit": profit, "operating_cash_flow": cfo})


def check_working_capital(prev: pd.Series, cur: pd.Series) -> CheckResult:
    ca0 = _safe_float(prev.get("current_assets")); cl0 = _safe_float(prev.get("current_liabilities"))
    ca1 = _safe_float(cur.get("current_assets")); cl1 = _safe_float(cur.get("current_liabilities"))
    if None in (ca0, cl0, ca1, cl1):
        return CheckResult("working_capital", "SKIP", 50, None, None,
            "Недостаточно данных для чистого оборотного капитала", {})
    wc0, wc1 = ca0 - cl0, ca1 - cl1
    change = wc1 - wc0
    pct = change / max(abs(wc0), 1.0)
    if pct >= -0.10:
        score = 0.0
    elif pct <= -0.50:
        score = 100.0
    else:
        score = (-pct - 0.10) / 0.40 * 100.0
    return CheckResult("working_capital", _status(score), score, change, pct,
        f"Изменение чистого оборотного капитала: {change:,.0f}",
        {"wc_begin": wc0, "wc_end": wc1})


# ---------------------------------------------------------------------------
# Веса при агрегации в единый Cross-Check Risk Score (0..100, выше = хуже)
# Пять обязательных правил формируют основной вес (70%), дополнительные —
# оставшиеся 30%. Внутри обязательных правил больше веса — балансовому
# равенству и деньгам, это самые жёсткие бухгалтерские тождества.
# ---------------------------------------------------------------------------
CHECK_WEIGHTS = {
    "balance_equation_end": 0.16,
    "balance_equation_begin": 0.10,
    "cash_rollforward": 0.16,
    "retained_earnings_rollforward": 0.14,
    "debt_rollforward": 0.14,
    "equity_rollforward_broad": 0.04,
    "current_assets_components": 0.04,
    "revenue_receivables_cash": 0.08,
    "purchases_payables_cash": 0.06,
    "profit_vs_cfo": 0.04,
    "working_capital": 0.04,
}


def run_cross_checks(company_df: pd.DataFrame) -> Dict[str, Any]:
    """company_df: строки одной компании, отсортированные по периодам
    (минимум 1 строка — тогда доступна только проверка баланса на конец
    периода; минимум 2 строки — доступны все правила roll-forward)."""
    df = company_df.copy()
    if "period" in df.columns:
        df["period"] = pd.to_datetime(df["period"])
        df = df.sort_values("period")
    if len(df) == 0:
        raise ValueError("Пустой набор данных для cross-check")

    cur = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else None

    results: List[CheckResult] = [
        check_balance_equation(cur, "end"),
        check_current_assets_components(cur),
        check_profit_vs_cfo(cur),
    ]
    if prev is not None:
        results.append(check_balance_equation(prev, "begin"))
        results.append(check_cash_rollforward(prev, cur))
        results.append(check_retained_earnings_rollforward(prev, cur))
        results.append(check_equity_rollforward_broad(prev, cur))
        results.append(check_debt_rollforward(prev, cur))
        results.append(check_revenue_receivables_cash(prev, cur))
        results.append(check_purchases_payables_cash(prev, cur))
        results.append(check_working_capital(prev, cur))
    else:
        # Нет предыдущего периода — явно фиксируем SKIP для каждого правила
        # roll-forward, чтобы список проверок был одинаковым по составу
        # независимо от того, сколько периодов загружено (это важно для
        # сайта и тестов: они всегда могут найти правило по имени).
        skip_names = ["balance_equation_begin", "cash_rollforward", "retained_earnings_rollforward",
                      "equity_rollforward_broad", "debt_rollforward", "revenue_receivables_cash",
                      "purchases_payables_cash", "working_capital"]
        for name in skip_names:
            results.append(CheckResult(name, "SKIP", 50, None, None,
                "Недостаточно данных: нужен предыдущий период для этого правила", {}))

    usable = [r for r in results if r.status != "SKIP"]
    if usable:
        weight_sum = sum(CHECK_WEIGHTS.get(r.name, 0.0) for r in usable)
        if weight_sum == 0:
            weighted_avg = float(np.mean([r.score for r in usable]))
        else:
            weighted_avg = sum(r.score * CHECK_WEIGHTS.get(r.name, 0.0) for r in usable) / weight_sum
    else:
        weighted_avg = 50.0

    # Обязательные правила (5 требований проекта): если хотя бы одно из них
    # сходится плохо, это не должно "тонуть" в общем взвешенном среднем из-за
    # того, что остальные 6 дополнительных правил в порядке. Поэтому берём
    # смесь взвешенного среднего (60%) и худшего результата среди обязательных
    # правил (40%) — единичное серьёзное расхождение по-прежнему заметно
    # поднимает итоговый риск, но не полностью его определяет.
    mandatory_names = {"balance_equation_begin", "balance_equation_end", "cash_rollforward",
                        "retained_earnings_rollforward", "debt_rollforward"}
    mandatory_scores = [r.score for r in usable if r.name in mandatory_names]
    worst_mandatory = max(mandatory_scores) if mandatory_scores else weighted_avg

    consistency_risk = 0.4 * weighted_avg + 0.6 * worst_mandatory

    consistency_health = 100.0 - consistency_risk
    ranked = sorted(usable, key=lambda r: r.score, reverse=True)
    top_findings = [r.message for r in ranked[:3] if r.score >= 20]  # только реальные WARN/FAIL, не молчаливые PASS

    return {
        "cross_check_risk_score": round(float(consistency_risk), 2),
        "financial_consistency_score": round(float(consistency_health), 2),
        "level": "LOW" if consistency_risk < 30 else ("MEDIUM" if consistency_risk < 60 else "HIGH"),
        "checks": [asdict(r) for r in results],
        "top_findings": top_findings,
        "periods_used": 2 if prev is not None else 1,
    }


if __name__ == "__main__":
    # Самопроверка: см. python/tests/test_cross_check.py для полного набора тестов
    print("Модуль cross-check загружен. Запустите tests/test_cross_check.py для проверки.")
