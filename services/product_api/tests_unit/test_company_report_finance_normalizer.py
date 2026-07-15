from decimal import Decimal

from company_report_test_helpers import finance_result, load_fixture
from company_report_signal_test_helpers import finance_company_report
from product_api.company_reports import (
    CompanyReport,
    FinanceFacts,
    FinanceForm,
    normalize_finance,
)
from product_api.company_reports.persistence import (
    calculate_company_report_snapshot_hash,
    company_report_to_snapshot,
)


def _indicator(facts, form, code):
    return next(item for item in facts.indicators if item.form is form and item.code == code)


def _period(facts, year):
    return next(item for item in facts.periods if item.year == year)


def _balance_payload(*indicators, years=(2024, 2025)):
    return {
        "balances": {
            "years": list(years),
            "okud": "SYNTH_BALANCE_OKUD",
            "indicators": list(indicators),
        }
    }


def _series(facts, form, code):
    return [
        item
        for item in facts.indicators
        if item.form is form and item.code == code
    ]


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
    cash = _series(facts, FinanceForm.BALANCE, "1250")

    assert {item.values_by_year[2022] for item in cash} == {
        Decimal("60"),
        Decimal("61"),
    }
    assert all(len(item.source_paths) == 2 for item in cash)
    assert _period(facts, 2022).cash_and_equivalents is None
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


def test_identical_duplicate_indicators_merge_paths_and_keep_exact_consensus():
    indicator = {
        "name": "Капитал",
        "code": "1300",
        "sum": {"2025": "12.50"},
    }
    facts = normalize_finance(
        finance_result(_balance_payload(indicator, dict(indicator)))
    )
    variants = _series(facts, FinanceForm.BALANCE, "1300")

    assert len(variants) == 1
    assert variants[0].source_paths == [
        "$.balances.indicators[0]",
        "$.balances.indicators[1]",
    ]
    assert _period(facts, 2025).equity == Decimal("12.50")
    assert "finance_duplicate_conflict" not in {
        item.code for item in facts.warnings
    }


def test_metadata_only_conflict_preserves_variants_and_exact_period_value():
    payload = _balance_payload(
        {"name": "Капитал A", "code": "1300", "sum": {"2025": "12.50"}},
        {"name": "Капитал B", "code": "1300", "sum": {"2025": "12.50"}},
    )
    facts = normalize_finance(finance_result(payload))
    variants = _series(facts, FinanceForm.BALANCE, "1300")

    assert len(variants) == 2
    assert {item.name for item in variants} == {"Капитал A", "Капитал B"}
    assert _period(facts, 2025).equity == Decimal("12.50")
    assert "finance_duplicate_conflict" in {item.code for item in facts.warnings}


def test_none_plus_exact_value_is_consensus_not_value_conflict():
    payload = _balance_payload(
        {"name": "Капитал", "code": "1300", "sum": {"2025": None}},
        {"name": "Капитал", "code": "1300", "sum": {"2025": "7"}},
    )
    facts = normalize_finance(finance_result(payload))

    assert len(_series(facts, FinanceForm.BALANCE, "1300")) == 2
    assert _period(facts, 2025).equity == Decimal("7")
    assert "finance_duplicate_conflict" in {item.code for item in facts.warnings}


def test_distinct_exact_values_are_preserved_and_period_is_ambiguous():
    payload = _balance_payload(
        {"name": "Капитал", "code": "1300", "sum": {"2025": "7"}},
        {"name": "Капитал", "code": "1300", "sum": {"2025": "8"}},
    )
    facts = normalize_finance(finance_result(payload))

    assert {
        item.values_by_year[2025]
        for item in _series(facts, FinanceForm.BALANCE, "1300")
    } == {Decimal("7"), Decimal("8")}
    assert _period(facts, 2025).equity is None
    assert "finance_duplicate_conflict" in {item.code for item in facts.warnings}


def test_conflicts_in_multiple_years_make_each_period_ambiguous():
    payload = _balance_payload(
        {
            "name": "Капитал",
            "code": "1300",
            "sum": {"2024": "7", "2025": "9"},
        },
        {
            "name": "Капитал",
            "code": "1300",
            "sum": {"2024": "8", "2025": "10"},
        },
    )
    facts = normalize_finance(finance_result(payload))

    assert len(_series(facts, FinanceForm.BALANCE, "1300")) == 2
    assert _period(facts, 2024).equity is None
    assert _period(facts, 2025).equity is None


def test_duplicate_block_permutation_has_identical_normalized_json():
    first = {"name": "Капитал A", "code": "1300", "sum": {"2025": "7"}}
    second = {"name": "Капитал B", "code": "1300", "sum": {"2025": "8"}}
    left_result = finance_result(_balance_payload(first, second))
    right_result = finance_result(_balance_payload(second, first)).model_copy(
        update={"response_hash": left_result.response_hash}
    )

    left = normalize_finance(left_result)
    right = normalize_finance(right_result)

    assert left.model_dump(mode="json") == right.model_dump(mode="json")


def test_no_conflict_payload_preserves_existing_financefacts_contract():
    payload = _balance_payload(
        {"name": "Капитал", "code": "1300", "sum": {"2025": "7.25"}},
        years=(2025,),
    )
    result = finance_result(payload)
    actual = normalize_finance(result)
    expected = FinanceFacts(
        source=actual.source,
        years=[2025],
        latest_year=2025,
        balance_okud="SYNTH_BALANCE_OKUD",
        indicators=[
            {
                "form": "balance",
                "code": "1300",
                "name": "Капитал",
                "values_by_year": {2025: Decimal("7.25")},
                "source_paths": ["$.balances.indicators[0]"],
            }
        ],
        periods=[{"year": 2025, "equity": Decimal("7.25")}],
        warnings=[],
    )

    assert actual.model_dump(mode="json") == expected.model_dump(mode="json")
    actual_report = finance_company_report(finance=actual)
    expected_report = finance_company_report(finance=expected)
    assert company_report_to_snapshot(actual_report) == company_report_to_snapshot(
        expected_report
    )
    assert calculate_company_report_snapshot_hash(
        actual_report
    ) == calculate_company_report_snapshot_hash(expected_report)
    assert set(FinanceFacts.model_fields) == {
        "source",
        "years",
        "latest_year",
        "balance_okud",
        "financial_results_okud",
        "cash_flow_okud",
        "indicators",
        "periods",
        "unit",
        "warnings",
    }
    assert "signals" not in CompanyReport.model_fields
