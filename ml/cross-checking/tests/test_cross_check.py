"""
Тесты для модуля 3_cross_check.py.
Запуск:  cd python && python3 -m pytest tests/test_cross_check.py -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
from importlib import import_module

cc = import_module("3_cross_check")

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "test_crosscheck.csv")


def _company(name):
    df = pd.read_csv(DATA)
    return df[df["company_id"] == name].sort_values("period")


def test_clean_company_passes_all_mandatory_checks():
    result = cc.run_cross_checks(_company("CLEAN Co"))
    assert result["cross_check_risk_score"] < 10, f"CLEAN компания должна давать риск почти 0, получили {result['cross_check_risk_score']}"
    assert result["level"] == "LOW"
    by_name = {c["name"]: c for c in result["checks"]}
    for rule in ["balance_equation_begin", "balance_equation_end", "cash_rollforward",
                 "retained_earnings_rollforward", "debt_rollforward"]:
        assert by_name[rule]["status"] == "PASS", f"{rule} должен быть PASS на чистых данных, получили {by_name[rule]['status']}"


def test_warning_company_flags_retained_earnings_only():
    result = cc.run_cross_checks(_company("WARNING Co"))
    assert 30 <= result["cross_check_risk_score"] < 60, f"WARNING кейс должен попасть в MEDIUM, получили {result['cross_check_risk_score']}"
    by_name = {c["name"]: c for c in result["checks"]}
    assert by_name["retained_earnings_rollforward"]["status"] in ("WARN", "FAIL")
    # остальные обязательные правила НЕ должны были случайно тоже сломаться
    assert by_name["cash_rollforward"]["status"] == "PASS"
    assert by_name["debt_rollforward"]["status"] == "PASS"


def test_high_mismatch_company_flags_debt():
    result = cc.run_cross_checks(_company("HIGH MISMATCH Co"))
    assert result["cross_check_risk_score"] >= 60, f"HIGH кейс должен быть >= 60, получили {result['cross_check_risk_score']}"
    assert result["level"] == "HIGH"
    by_name = {c["name"]: c for c in result["checks"]}
    assert by_name["debt_rollforward"]["status"] == "FAIL"


def test_balance_checked_on_both_begin_and_end():
    """Ключевая проверка требования проекта: баланс проверяется И на начало, И на конец."""
    result = cc.run_cross_checks(_company("CLEAN Co"))
    names = [c["name"] for c in result["checks"]]
    assert "balance_equation_begin" in names
    assert "balance_equation_end" in names


def test_retained_earnings_is_separate_from_total_equity():
    """Ключевая проверка исправления ошибки GPT: есть отдельное правило именно
    по нераспределённой прибыли, а не только по общему капиталу."""
    result = cc.run_cross_checks(_company("CLEAN Co"))
    names = [c["name"] for c in result["checks"]]
    assert "retained_earnings_rollforward" in names
    assert "equity_rollforward_broad" in names  # широкая проверка тоже есть, но отдельно


def test_single_period_does_not_crash():
    """Если у компании данные только за один период (например, первая
    загрузка), roll-forward правила должны SKIP, а не падать с ошибкой."""
    df = _company("CLEAN Co").iloc[[-1]]
    result = cc.run_cross_checks(df)
    assert "cross_check_risk_score" in result
    assert 0 <= result["cross_check_risk_score"] <= 100
    by_name = {c["name"]: c for c in result["checks"]}
    assert by_name["cash_rollforward"]["status"] == "SKIP"
    assert by_name["balance_equation_end"]["status"] == "PASS"  # это единственное, что доступно без истории


def test_score_bounds():
    for name in ["CLEAN Co", "WARNING Co", "HIGH MISMATCH Co"]:
        result = cc.run_cross_checks(_company(name))
        assert 0 <= result["cross_check_risk_score"] <= 100
        assert 0 <= result["financial_consistency_score"] <= 100
        assert abs(result["cross_check_risk_score"] + result["financial_consistency_score"] - 100) < 0.01
