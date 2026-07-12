from decimal import Decimal

from company_report_test_helpers import finance_result, load_fixture
from product_api.company_reports import FinanceForm, normalize_finance


def _indicator(facts, form, code):
    return next(item for item in facts.indicators if item.form is form and item.code == code)


def _period(facts, year):
    return next(item for item in facts.periods if item.year == year)


def test_finance_sorts_union_of_years_and_preserves_unknown_units():
    facts = normalize_finance(finance_result())

    assert facts.years == [2020, 2021, 2022, 2023]
    assert facts.latest_year == 2023
    assert facts.unit == "provider_units_unknown"
    assert facts.balance_okud == "SYNTH_BALANCE_OKUD"
    assert facts.financial_results_okud == "SYNTH_RESULTS_OKUD"
    assert facts.cash_flow_okud is None


def test_finance_flattens_indicators_and_children_map_and_merges_duplicates():
    facts = normalize_finance(finance_result())
    total_assets = _indicator(facts, FinanceForm.BALANCE, "1600")
    revenue = _indicator(facts, FinanceForm.FINANCIAL_RESULTS, "2110")

    assert total_assets.values_by_year[2021] == Decimal("1000.10")
    assert total_assets.values_by_year[2023] == Decimal("1400.5")
    assert len(total_assets.source_paths) == 2
    assert len(revenue.source_paths) == 2


def test_finance_conflict_is_deterministic_and_warned():
    facts = normalize_finance(finance_result())
    cash = _indicator(facts, FinanceForm.BALANCE, "1250")

    assert cash.values_by_year[2022] == Decimal("60")
    assert len(cash.source_paths) == 2
    assert "finance_duplicate_conflict" in {item.code for item in facts.warnings}


def test_finance_invalid_number_and_missing_period_are_none_not_zero():
    facts = normalize_finance(finance_result())
    period_2022 = _period(facts, 2022)
    period_2021 = _period(facts, 2021)

    assert period_2022.accounts_payable is None
    assert period_2022.accounts_receivable is None
    assert period_2021.net_cash_flow is None
    assert "decimal_parse_failed" in {item.code for item in facts.warnings}


def test_finance_populates_all_key_metric_fields():
    period = _period(normalize_finance(finance_result()), 2023)

    expected = {
        "total_assets": "1400.5",
        "non_current_assets": "500",
        "current_assets": "900",
        "inventories": "120",
        "accounts_receivable": "250",
        "cash_and_equivalents": "70",
        "equity": "400",
        "long_term_liabilities": "240",
        "short_term_liabilities": "760",
        "short_term_borrowings": "190",
        "accounts_payable": "300",
        "revenue": "900",
        "cost_of_sales": "550",
        "gross_profit": "350",
        "operating_profit": "210",
        "profit_before_tax": "190",
        "net_profit": "145",
        "net_cash_flow": "15",
        "cash_at_start": "30",
        "cash_at_end": "45",
    }
    assert {name: str(getattr(period, name)) for name in expected} == expected


def test_finance_indicator_without_code_is_skipped_with_warning():
    payload = load_fixture("finance_success.json")
    payload["balances"]["indicators"].append(
        {"name": "Синтетический показатель без кода", "code": "", "sum": {"2023": 1}}
    )

    facts = normalize_finance(finance_result(payload))

    assert "finance_indicator_missing_code" in {item.code for item in facts.warnings}
    assert all(item.code for item in facts.indicators)
