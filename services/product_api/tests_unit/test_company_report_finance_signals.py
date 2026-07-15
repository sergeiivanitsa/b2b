from __future__ import annotations

from decimal import Decimal

import pytest

from company_report_test_helpers import finance_result
from company_report_signal_test_helpers import (
    finance_company_report,
    finance_facts,
    finance_indicator,
    report_without_finance_facts,
)
from product_api.company_reports import (
    DatasetReportStatus,
    FinanceForm,
    FinancialPeriod,
    NormalizationWarning,
    normalize_finance,
)
from product_api.company_reports.signals import (
    AllOfExpression,
    ComparisonComparator,
    DecimalComparisonOperator,
    DecimalRatioOperator,
    SignalConfidence,
    SignalStrength,
    YearPeriod,
    YearRangePeriod,
    canonical_representation,
)
from product_api.company_reports.signals import finance as finance_signals


NEGATIVE_EQUITY = "finance.negative_equity"
REVENUE_DECLINE = "finance.revenue_decline"
NET_LOSS = "finance.net_loss"
CASH_SHORTFALL = "finance.cash_shortfall"
HIGH_ACCOUNTS_PAYABLE = "finance.high_accounts_payable"
RULE_CODES = {
    NEGATIVE_EQUITY,
    REVENUE_DECLINE,
    NET_LOSS,
    CASH_SHORTFALL,
    HIGH_ACCOUNTS_PAYABLE,
}
_INDICATOR_BY_FIELD = {
    "current_assets": (FinanceForm.BALANCE, "1200"),
    "cash_and_equivalents": (FinanceForm.BALANCE, "1250"),
    "equity": (FinanceForm.BALANCE, "1300"),
    "short_term_liabilities": (FinanceForm.BALANCE, "1500"),
    "accounts_payable": (FinanceForm.BALANCE, "1520"),
    "revenue": (FinanceForm.FINANCIAL_RESULTS, "2110"),
    "net_profit": (FinanceForm.FINANCIAL_RESULTS, "2400"),
}


def _evaluate(periods=None, *, facts=None, status=DatasetReportStatus.AVAILABLE):
    normalized = facts if facts is not None else finance_facts(periods or [])
    return finance_signals._evaluate_finance_signals(
        finance_company_report(finance=normalized, finance_status=status)
    )


def _signal(result, code):
    return next(signal for signal in result.signals if signal.code == code)


def _warning(result, code):
    return next(warning for warning in result.warnings if warning.rule_code == code)


def _fact(signal_or_warning, fact_id):
    basis = (
        signal_or_warning.factual_basis
        if hasattr(signal_or_warning, "factual_basis")
        else signal_or_warning.evaluation_basis
    )
    return next(fact for fact in basis.facts if fact.id == fact_id)


def _variant_facts(
    periods,
    *,
    field,
    year,
    values,
    names=None,
    shared_values=None,
):
    form, code = _INDICATOR_BY_FIELD[field]
    normalized_names = names or [field] * len(values)
    indicators = [
        finance_indicator(
            form,
            code,
            name=name,
            values_by_year={**(shared_values or {}), year: value},
            source_path=f"$.variants.{field}[{index}]",
        )
        for index, (name, value) in enumerate(zip(normalized_names, values))
    ]
    warning = NormalizationWarning(
        code="finance_duplicate_conflict",
        path=f"$.variants.{field}[0]",
        message="safe duplicate indicator warning",
    )
    return finance_facts(periods, indicators=indicators, warnings=[warning])


def _revenue_variant_facts(variants, period_values):
    indicators = [
        finance_indicator(
            FinanceForm.FINANCIAL_RESULTS,
            "2110",
            name="Выручка",
            values_by_year=values,
            source_path=f"$.variants.revenue[{index}]",
        )
        for index, values in enumerate(variants)
    ]
    warning = NormalizationWarning(
        code="finance_duplicate_conflict",
        path="$.variants.revenue[0]",
        message="safe duplicate indicator warning",
    )
    return finance_facts(
        [
            FinancialPeriod(year=year, revenue=value)
            for year, value in sorted(period_values.items())
        ],
        indicators=indicators,
        warnings=[warning],
    )


def _multi_field_variant_facts(periods, variants_by_field):
    indicators = []
    warnings = []
    for field in sorted(variants_by_field):
        form, code = _INDICATOR_BY_FIELD[field]
        for index, values_by_year in enumerate(variants_by_field[field]):
            indicators.append(
                finance_indicator(
                    form,
                    code,
                    name=field,
                    values_by_year=values_by_year,
                    source_path=f"$.variants.{field}[{index}]",
                )
            )
        warnings.append(
            NormalizationWarning(
                code="finance_duplicate_conflict",
                path=f"$.variants.{field}[0]",
                message="safe duplicate indicator warning",
            )
        )
    return finance_facts(periods, indicators=indicators, warnings=warnings)


@pytest.mark.parametrize(
    ("status", "error_code"),
    [
        (DatasetReportStatus.DISABLED, "dataset_unavailable"),
        (DatasetReportStatus.NOT_FOUND, "dataset_unavailable"),
        (DatasetReportStatus.ACCESS_DENIED, "dataset_unavailable"),
        (DatasetReportStatus.INVALID_RESPONSE, "dataset_unavailable"),
        (DatasetReportStatus.NORMALIZATION_ERROR, "dataset_unavailable"),
    ],
)
def test_unavailable_or_malformed_dataset_suppresses_all_rules(status, error_code):
    result = _evaluate(status=status)

    assert result.signals == []
    assert {warning.rule_code for warning in result.warnings} == RULE_CODES
    assert {warning.code for warning in result.warnings} == {error_code}
    assert all(warning.dataset == "finance" for warning in result.warnings)
    assert all(warning.evaluation_basis.failed_eligibility for warning in result.warnings)
    assert "finance.reporting_absent" not in canonical_representation(result)


def test_available_dataset_without_facts_is_not_interpreted_as_reporting_absence():
    result = finance_signals._evaluate_finance_signals(
        report_without_finance_facts()
    )

    assert result.signals == []
    assert {warning.code for warning in result.warnings} == {
        "required_fact_missing"
    }
    assert {warning.rule_code for warning in result.warnings} == RULE_CODES


def test_empty_periods_create_period_warnings_but_no_reporting_absent():
    result = _evaluate([])

    assert result.signals == []
    assert {warning.code for warning in result.warnings} == {
        "required_period_unavailable"
    }
    assert "reporting_absent" not in canonical_representation(result)


@pytest.mark.parametrize(
    ("value", "triggered"),
    [(Decimal("-0.0000000001"), True), (Decimal("0"), False), (Decimal("1"), False)],
)
def test_negative_equity_exact_boundaries(value, triggered):
    result = _evaluate([FinancialPeriod(year=2025, equity=value)])

    assert (NEGATIVE_EQUITY in {signal.code for signal in result.signals}) is triggered
    assert NEGATIVE_EQUITY not in {warning.rule_code for warning in result.warnings}
    if triggered:
        signal = _signal(result, NEGATIVE_EQUITY)
        assert signal.strength is SignalStrength.HIGH
        assert signal.period == YearPeriod(year=2025)
        assert signal.factual_basis.years == [2025]
        assert _fact(signal, "equity").exact_value == value
        assert isinstance(_fact(signal, "equity").exact_value, Decimal)


def test_negative_equity_uses_latest_eligible_year_and_falls_back_from_missing():
    result = _evaluate(
        [
            FinancialPeriod(year=2023, equity=Decimal("-5")),
            FinancialPeriod(year=2024, equity=Decimal("2")),
            FinancialPeriod(year=2025, equity=None),
        ]
    )

    assert NEGATIVE_EQUITY not in {signal.code for signal in result.signals}
    assert NEGATIVE_EQUITY not in {warning.rule_code for warning in result.warnings}

    fallback = _evaluate(
        [
            FinancialPeriod(year=2024, equity=Decimal("-5")),
            FinancialPeriod(year=2025, equity=None),
        ]
    )
    assert _signal(fallback, NEGATIVE_EQUITY).period == YearPeriod(year=2024)

    missing = _evaluate([FinancialPeriod(year=2025, equity=None)])
    assert _warning(missing, NEGATIVE_EQUITY).code == "required_fact_missing"


def test_identical_duplicate_year_is_deduplicated_but_conflict_is_suppressed():
    identical = _evaluate(
        [
            FinancialPeriod(year=2025, equity=Decimal("-1")),
            FinancialPeriod(year=2025, equity=Decimal("-1")),
        ]
    )
    assert _signal(identical, NEGATIVE_EQUITY).period == YearPeriod(year=2025)

    conflict = _evaluate(
        facts=_variant_facts(
            [FinancialPeriod(year=2025, equity=None)],
            field="equity",
            year=2025,
            values=[Decimal("-1"), Decimal("2")],
        )
    )
    warning = _warning(conflict, NEGATIVE_EQUITY)
    assert warning.code == "finance_period_conflict"
    assert warning.evaluation_basis.years == [2025]
    assert {
        fact.exact_value
        for fact in warning.evaluation_basis.facts
        if fact.id.startswith("conflict_equity_") and "_value_" in fact.id
    } == {Decimal("-1"), Decimal("2")}
    assert _fact(warning, "period_consistent").exact_value is False
    assert "-1" not in warning.message
    assert "2" not in warning.message


def test_single_rule_falls_back_from_newer_indicator_conflict():
    warning = NormalizationWarning(
        code="finance_duplicate_conflict",
        path="$.variants.equity[0]",
        message="safe duplicate indicator warning",
    )
    indicators = [
        finance_indicator(
            FinanceForm.BALANCE,
            "1300",
            values_by_year={2024: Decimal("-1"), 2025: Decimal("1")},
            source_path="$.variants.equity[0]",
        ),
        finance_indicator(
            FinanceForm.BALANCE,
            "1300",
            values_by_year={2024: Decimal("-1"), 2025: Decimal("2")},
            source_path="$.variants.equity[1]",
        ),
    ]
    facts = finance_facts(
        [
            FinancialPeriod(year=2024, equity=Decimal("-1")),
            FinancialPeriod(year=2025, equity=None),
        ],
        indicators=indicators,
        warnings=[warning],
    )
    result = _evaluate(facts=facts)
    signal = _signal(result, NEGATIVE_EQUITY)

    assert signal.period == YearPeriod(year=2024)
    assert signal.confidence is SignalConfidence.MEDIUM
    assert NEGATIVE_EQUITY not in {item.rule_code for item in result.warnings}


@pytest.mark.parametrize(
    ("previous", "later", "triggered"),
    [
        (Decimal("100"), Decimal("99.999999999"), True),
        (Decimal("100"), Decimal("100"), False),
        (Decimal("100"), Decimal("101"), False),
    ],
)
def test_revenue_decline_exact_boundaries(previous, later, triggered):
    result = _evaluate(
        [
            FinancialPeriod(year=2024, revenue=previous),
            FinancialPeriod(year=2025, revenue=later),
        ]
    )

    assert (REVENUE_DECLINE in {signal.code for signal in result.signals}) is triggered
    assert REVENUE_DECLINE not in {warning.rule_code for warning in result.warnings}
    if triggered:
        signal = _signal(result, REVENUE_DECLINE)
        assert signal.period == YearRangePeriod(start_year=2024, end_year=2025)
        assert signal.factual_basis.years == [2024, 2025]
        assert signal.strength is SignalStrength.MEDIUM


def test_revenue_uses_latest_clean_consecutive_pair():
    selected = _evaluate(
        [
            FinancialPeriod(year=2022, revenue=Decimal("500")),
            FinancialPeriod(year=2023, revenue=None),
            FinancialPeriod(year=2024, revenue=Decimal("200")),
            FinancialPeriod(year=2025, revenue=Decimal("100")),
        ]
    )
    assert _signal(selected, REVENUE_DECLINE).period == YearRangePeriod(
        start_year=2024, end_year=2025
    )

    pure_missing_gap = _evaluate(
        [
            FinancialPeriod(year=2022, revenue=Decimal("300")),
            FinancialPeriod(year=2024, revenue=Decimal("100")),
        ]
    )
    assert REVENUE_DECLINE not in {
        signal.code for signal in pure_missing_gap.signals
    }
    assert _warning(pure_missing_gap, REVENUE_DECLINE).code == (
        "required_period_unavailable"
    )

    older_pair_but_newer_gap = _evaluate(
        [
            FinancialPeriod(year=2022, revenue=Decimal("200")),
            FinancialPeriod(year=2023, revenue=Decimal("100")),
            FinancialPeriod(year=2025, revenue=Decimal("50")),
        ]
    )
    assert _signal(
        older_pair_but_newer_gap,
        REVENUE_DECLINE,
    ).period == YearRangePeriod(
        start_year=2022,
        end_year=2023,
    )

    missing = _evaluate(
        [
            FinancialPeriod(year=2024, revenue=Decimal("100")),
            FinancialPeriod(year=2025, revenue=None),
        ]
    )
    assert _warning(missing, REVENUE_DECLINE).code == (
        "required_period_unavailable"
    )

    latest_pair = _evaluate(
        [
            FinancialPeriod(year=2021, revenue=Decimal("400")),
            FinancialPeriod(year=2022, revenue=Decimal("300")),
            FinancialPeriod(year=2023, revenue=Decimal("200")),
            FinancialPeriod(year=2024, revenue=Decimal("100")),
        ]
    )
    assert _signal(latest_pair, REVENUE_DECLINE).period == YearRangePeriod(
        start_year=2023,
        end_year=2024,
    )


def test_revenue_conflict_in_comparison_basis_is_rule_specific():
    periods = [
            FinancialPeriod(year=2024, revenue=Decimal("200"), equity=Decimal("-1")),
            FinancialPeriod(year=2025, revenue=None),
    ]
    result = _evaluate(
        facts=_variant_facts(
            periods,
            field="revenue",
            year=2025,
            values=[Decimal("100"), Decimal("101")],
            shared_values={2024: Decimal("200")},
        )
    )

    assert _warning(result, REVENUE_DECLINE).code == "finance_period_conflict"
    assert _signal(result, NEGATIVE_EQUITY).period == YearPeriod(year=2024)


def test_revenue_falls_back_to_older_clean_pair_and_ignores_unused_conflict():
    warning = NormalizationWarning(
        code="finance_duplicate_conflict",
        path="$.variants.revenue[0]",
        message="safe duplicate indicator warning",
    )
    indicators = [
        finance_indicator(
            FinanceForm.FINANCIAL_RESULTS,
            "2110",
            values_by_year={
                2022: Decimal("200"),
                2023: Decimal("100"),
                2024: Decimal("90"),
            },
            source_path="$.variants.revenue[0]",
        ),
        finance_indicator(
            FinanceForm.FINANCIAL_RESULTS,
            "2110",
            values_by_year={
                2022: Decimal("200"),
                2023: Decimal("100"),
                2024: Decimal("95"),
            },
            source_path="$.variants.revenue[1]",
        ),
    ]
    facts = finance_facts(
        [
            FinancialPeriod(year=2022, revenue=Decimal("200")),
            FinancialPeriod(year=2023, revenue=Decimal("100")),
            FinancialPeriod(year=2024, revenue=None),
        ],
        indicators=indicators,
        warnings=[warning],
    )
    signal = _signal(_evaluate(facts=facts), REVENUE_DECLINE)

    assert signal.period == YearRangePeriod(start_year=2022, end_year=2023)
    assert signal.confidence is SignalConfidence.MEDIUM


def test_revenue_older_pair_survives_conflict_and_later_clean_year():
    facts = _revenue_variant_facts(
        [
            {
                2021: Decimal("300"),
                2022: Decimal("200"),
                2023: Decimal("150"),
                2024: Decimal("100"),
            },
            {
                2021: Decimal("300"),
                2022: Decimal("200"),
                2023: Decimal("160"),
                2024: Decimal("100"),
            },
        ],
        {
            2021: Decimal("300"),
            2022: Decimal("200"),
            2023: None,
            2024: Decimal("100"),
        },
    )
    result = _evaluate(facts=facts)
    signal = _signal(result, REVENUE_DECLINE)

    assert signal.period == YearRangePeriod(start_year=2021, end_year=2022)
    assert signal.confidence is SignalConfidence.MEDIUM
    assert REVENUE_DECLINE not in {item.rule_code for item in result.warnings}


def test_revenue_conflict_fills_only_gap_and_basis_excludes_clean_years():
    facts = _revenue_variant_facts(
        [
            {2022: Decimal("300"), 2023: Decimal("200"), 2024: Decimal("100")},
            {2022: Decimal("300"), 2023: Decimal("210"), 2024: Decimal("100")},
        ],
        {2022: Decimal("300"), 2023: None, 2024: Decimal("100")},
    )
    result = _evaluate(facts=facts)
    warning = _warning(result, REVENUE_DECLINE)

    assert REVENUE_DECLINE not in {signal.code for signal in result.signals}
    assert warning.code == "finance_period_conflict"
    assert warning.evaluation_basis.years == [2023]
    assert {
        fact.exact_value
        for fact in warning.evaluation_basis.facts
        if fact.id.startswith("conflict_revenue_2023_value_")
    } == {Decimal("200"), Decimal("210")}
    assert _fact(warning, "period_consistent").exact_value is False


def test_revenue_old_conflict_does_not_suppress_newer_clean_pair():
    facts = _revenue_variant_facts(
        [
            {2021: Decimal("400"), 2022: Decimal("300"), 2023: Decimal("200")},
            {2021: Decimal("410"), 2022: Decimal("300"), 2023: Decimal("200")},
        ],
        {2021: None, 2022: Decimal("300"), 2023: Decimal("200")},
    )
    result = _evaluate(facts=facts)
    signal = _signal(result, REVENUE_DECLINE)

    assert signal.period == YearRangePeriod(start_year=2022, end_year=2023)
    assert signal.confidence is SignalConfidence.MEDIUM
    assert REVENUE_DECLINE not in {item.rule_code for item in result.warnings}


@pytest.mark.parametrize(
    ("value", "triggered"),
    [(Decimal("-1"), True), (Decimal("0"), False), (Decimal("1"), False)],
)
def test_net_loss_is_strict_and_always_medium(value, triggered):
    result = _evaluate([FinancialPeriod(year=2025, net_profit=value)])

    assert (NET_LOSS in {signal.code for signal in result.signals}) is triggered
    if triggered:
        signal = _signal(result, NET_LOSS)
        assert signal.strength is SignalStrength.MEDIUM
        assert signal.period == YearPeriod(year=2025)


def test_net_loss_falls_back_and_duplicate_conflict_is_not_zero():
    fallback = _evaluate(
        [
            FinancialPeriod(year=2024, net_profit=Decimal("-1")),
            FinancialPeriod(year=2025, net_profit=None),
        ]
    )
    assert _signal(fallback, NET_LOSS).period == YearPeriod(year=2024)

    conflict = _evaluate(
        facts=_variant_facts(
            [FinancialPeriod(year=2025, net_profit=None)],
            field="net_profit",
            year=2025,
            values=[Decimal("-1"), Decimal("1")],
        )
    )
    assert _warning(conflict, NET_LOSS).code == "finance_period_conflict"


@pytest.mark.parametrize(
    ("cash", "liabilities", "triggered", "strength"),
    [
        (Decimal("100"), Decimal("100"), False, None),
        (Decimal("30"), Decimal("100"), True, SignalStrength.MEDIUM),
        (Decimal("25"), Decimal("100"), True, SignalStrength.MEDIUM),
        (Decimal("24.999999999"), Decimal("100"), True, SignalStrength.HIGH),
        (Decimal("0"), Decimal("0"), False, None),
        (Decimal("-2"), Decimal("-1"), True, SignalStrength.HIGH),
    ],
)
def test_cash_shortfall_strict_boundaries_without_division(
    cash, liabilities, triggered, strength
):
    result = _evaluate(
        [
            FinancialPeriod(
                year=2025,
                cash_and_equivalents=cash,
                short_term_liabilities=liabilities,
            )
        ]
    )

    assert (CASH_SHORTFALL in {signal.code for signal in result.signals}) is triggered
    assert CASH_SHORTFALL not in {warning.rule_code for warning in result.warnings}
    if triggered:
        signal = _signal(result, CASH_SHORTFALL)
        assert signal.strength is strength
        assert _fact(signal, "short_term_liabilities_25_percent").exact_value == (
            liabilities * Decimal("0.25")
        )
        assert _fact(signal, "cash_shortfall_high_factor").exact_value == Decimal(
            "0.25"
        )
        assert isinstance(signal.factual_basis.trigger.operator, DecimalComparisonOperator)
        assert signal.factual_basis.trigger.operator.comparator is (
            ComparisonComparator.LESS_THAN
        )
        override = signal.factual_basis.strength_decision.overrides[0]
        assert isinstance(override.when, AllOfExpression)
        assert not any(
            isinstance(child.operator, DecimalRatioOperator)
            for child in override.when.children
        )


@pytest.mark.parametrize("missing_field", ["cash_and_equivalents", "short_term_liabilities"])
def test_cash_missing_fact_is_not_zero(missing_field):
    values = {
        "cash_and_equivalents": Decimal("1"),
        "short_term_liabilities": Decimal("100"),
    }
    values[missing_field] = None
    result = _evaluate([FinancialPeriod(year=2025, **values)])

    assert CASH_SHORTFALL not in {signal.code for signal in result.signals}
    assert _warning(result, CASH_SHORTFALL).code == "required_fact_missing"


@pytest.mark.parametrize("conflict_field", ["cash_and_equivalents", "short_term_liabilities"])
def test_cash_duplicate_conflict_suppresses_only_cash_rule(conflict_field):
    first = {
        "cash_and_equivalents": Decimal("10"),
        "short_term_liabilities": Decimal("100"),
        "equity": Decimal("-1"),
    }
    conflict_values = (
        [Decimal("10"), Decimal("20")]
        if conflict_field == "cash_and_equivalents"
        else [Decimal("100"), Decimal("200")]
    )
    result = _evaluate(
        facts=_variant_facts(
            [FinancialPeriod(year=2025, **{**first, conflict_field: None})],
            field=conflict_field,
            year=2025,
            values=conflict_values,
        )
    )

    assert _warning(result, CASH_SHORTFALL).code == "finance_period_conflict"
    assert _signal(result, NEGATIVE_EQUITY).period == YearPeriod(year=2025)


@pytest.mark.parametrize(
    ("conflict_field", "missing_field", "values"),
    [
        (
            "cash_and_equivalents",
            "short_term_liabilities",
            [Decimal("10"), Decimal("20")],
        ),
        (
            "short_term_liabilities",
            "cash_and_equivalents",
            [Decimal("100"), Decimal("200")],
        ),
    ],
)
def test_cash_mixed_conflict_and_missing_is_required_fact_missing(
    conflict_field, missing_field, values
):
    period_values = {
        "cash_and_equivalents": None,
        "short_term_liabilities": None,
    }
    result = _evaluate(
        facts=_variant_facts(
            [FinancialPeriod(year=2025, **period_values)],
            field=conflict_field,
            year=2025,
            values=values,
        )
    )

    warning = _warning(result, CASH_SHORTFALL)
    assert warning.code == "required_fact_missing"
    assert CASH_SHORTFALL not in {
        item.rule_code
        for item in result.warnings
        if item.code == "finance_period_conflict"
    }
    assert _fact(warning, missing_field).exact_value is None


def test_cash_conflicts_in_both_required_fields_are_period_conflict():
    facts = _multi_field_variant_facts(
        [
            FinancialPeriod(
                year=2025,
                cash_and_equivalents=None,
                short_term_liabilities=None,
            )
        ],
        {
            "cash_and_equivalents": [
                {2025: Decimal("10")},
                {2025: Decimal("20")},
            ],
            "short_term_liabilities": [
                {2025: Decimal("100")},
                {2025: Decimal("200")},
            ],
        },
    )
    warning = _warning(_evaluate(facts=facts), CASH_SHORTFALL)

    assert warning.code == "finance_period_conflict"
    assert {
        fact.exact_value
        for fact in warning.evaluation_basis.facts
        if fact.id.startswith("conflict_cash_and_equivalents_2025_value_")
    } == {Decimal("10"), Decimal("20")}
    assert {
        fact.exact_value
        for fact in warning.evaluation_basis.facts
        if fact.id.startswith("conflict_short_term_liabilities_2025_value_")
    } == {Decimal("100"), Decimal("200")}


def test_cash_clean_fallback_ignores_newer_mixed_conflict_and_missing():
    facts = _multi_field_variant_facts(
        [
            FinancialPeriod(
                year=2024,
                cash_and_equivalents=Decimal("10"),
                short_term_liabilities=Decimal("100"),
            ),
            FinancialPeriod(year=2025),
        ],
        {
            "cash_and_equivalents": [
                {2024: Decimal("10"), 2025: Decimal("20")},
                {2024: Decimal("10"), 2025: Decimal("30")},
            ]
        },
    )
    result = _evaluate(facts=facts)
    signal = _signal(result, CASH_SHORTFALL)

    assert signal.period == YearPeriod(year=2024)
    assert signal.confidence is SignalConfidence.MEDIUM
    assert CASH_SHORTFALL not in {item.rule_code for item in result.warnings}


def test_cash_uses_latest_year_where_both_values_are_known():
    result = _evaluate(
        [
            FinancialPeriod(
                year=2024,
                cash_and_equivalents=Decimal("10"),
                short_term_liabilities=Decimal("100"),
            ),
            FinancialPeriod(
                year=2025,
                cash_and_equivalents=Decimal("1"),
                short_term_liabilities=None,
            ),
        ]
    )
    assert _signal(result, CASH_SHORTFALL).period == YearPeriod(year=2024)


@pytest.mark.parametrize(
    ("payable", "assets", "triggered"),
    [
        (Decimal("101"), Decimal("100"), True),
        (Decimal("100"), Decimal("100"), False),
        (Decimal("99"), Decimal("100"), False),
    ],
)
def test_high_accounts_payable_strict_boundaries(payable, assets, triggered):
    result = _evaluate(
        [
            FinancialPeriod(
                year=2025,
                accounts_payable=payable,
                current_assets=assets,
            )
        ]
    )

    assert (HIGH_ACCOUNTS_PAYABLE in {signal.code for signal in result.signals}) is triggered
    if triggered:
        signal = _signal(result, HIGH_ACCOUNTS_PAYABLE)
        assert signal.strength is SignalStrength.HIGH
        assert signal.period == YearPeriod(year=2025)


@pytest.mark.parametrize("missing_field", ["accounts_payable", "current_assets"])
def test_high_accounts_payable_missing_fact_is_safely_suppressed(missing_field):
    values = {"accounts_payable": Decimal("200"), "current_assets": Decimal("100")}
    values[missing_field] = None
    result = _evaluate([FinancialPeriod(year=2025, **values)])

    assert _warning(result, HIGH_ACCOUNTS_PAYABLE).code == "required_fact_missing"


@pytest.mark.parametrize("conflict_field", ["accounts_payable", "current_assets"])
def test_high_accounts_payable_latest_year_and_duplicate_conflict(conflict_field):
    fallback = _evaluate(
        [
            FinancialPeriod(
                year=2024,
                accounts_payable=Decimal("200"),
                current_assets=Decimal("100"),
            ),
            FinancialPeriod(year=2025, accounts_payable=Decimal("300")),
        ]
    )
    assert _signal(fallback, HIGH_ACCOUNTS_PAYABLE).period == YearPeriod(year=2024)

    first = {"accounts_payable": Decimal("200"), "current_assets": Decimal("100")}
    conflict_values = [first[conflict_field], first[conflict_field] + Decimal("1")]
    conflict = _evaluate(
        facts=_variant_facts(
            [FinancialPeriod(year=2025, **{**first, conflict_field: None})],
            field=conflict_field,
            year=2025,
            values=conflict_values,
        )
    )
    assert _warning(conflict, HIGH_ACCOUNTS_PAYABLE).code == "finance_period_conflict"


@pytest.mark.parametrize(
    ("conflict_field", "missing_field", "values"),
    [
        (
            "accounts_payable",
            "current_assets",
            [Decimal("200"), Decimal("300")],
        ),
        (
            "current_assets",
            "accounts_payable",
            [Decimal("100"), Decimal("150")],
        ),
    ],
)
def test_accounts_payable_mixed_conflict_and_missing_is_required_fact_missing(
    conflict_field, missing_field, values
):
    result = _evaluate(
        facts=_variant_facts(
            [FinancialPeriod(year=2025)],
            field=conflict_field,
            year=2025,
            values=values,
        )
    )

    warning = _warning(result, HIGH_ACCOUNTS_PAYABLE)
    assert warning.code == "required_fact_missing"
    assert HIGH_ACCOUNTS_PAYABLE not in {
        item.rule_code
        for item in result.warnings
        if item.code == "finance_period_conflict"
    }
    assert _fact(warning, missing_field).exact_value is None


def test_accounts_payable_clean_fallback_ignores_newer_mixed_conflict():
    facts = _multi_field_variant_facts(
        [
            FinancialPeriod(
                year=2024,
                accounts_payable=Decimal("200"),
                current_assets=Decimal("100"),
            ),
            FinancialPeriod(year=2025),
        ],
        {
            "accounts_payable": [
                {2024: Decimal("200"), 2025: Decimal("250")},
                {2024: Decimal("200"), 2025: Decimal("300")},
            ]
        },
    )
    result = _evaluate(facts=facts)
    signal = _signal(result, HIGH_ACCOUNTS_PAYABLE)

    assert signal.period == YearPeriod(year=2024)
    assert signal.confidence is SignalConfidence.MEDIUM
    assert HIGH_ACCOUNTS_PAYABLE not in {
        item.rule_code for item in result.warnings
    }


@pytest.mark.parametrize(
    ("field", "rule_code", "period", "shared_values"),
    [
        ("equity", NEGATIVE_EQUITY, FinancialPeriod(year=2025), None),
        ("net_profit", NET_LOSS, FinancialPeriod(year=2025), None),
        (
            "cash_and_equivalents",
            CASH_SHORTFALL,
            FinancialPeriod(year=2025, short_term_liabilities=Decimal("100")),
            None,
        ),
        (
            "short_term_liabilities",
            CASH_SHORTFALL,
            FinancialPeriod(year=2025, cash_and_equivalents=Decimal("10")),
            None,
        ),
        (
            "accounts_payable",
            HIGH_ACCOUNTS_PAYABLE,
            FinancialPeriod(year=2025, current_assets=Decimal("100")),
            None,
        ),
        (
            "current_assets",
            HIGH_ACCOUNTS_PAYABLE,
            FinancialPeriod(year=2025, accounts_payable=Decimal("200")),
            None,
        ),
        (
            "revenue",
            REVENUE_DECLINE,
            FinancialPeriod(year=2025),
            {2024: Decimal("200")},
        ),
    ],
)
def test_value_conflict_basis_is_exact_and_never_required_fact_missing(
    field, rule_code, period, shared_values
):
    periods = [period]
    if shared_values:
        periods.insert(0, FinancialPeriod(year=2024, revenue=Decimal("200")))
    result = _evaluate(
        facts=_variant_facts(
            periods,
            field=field,
            year=2025,
            values=[Decimal("7.125"), Decimal("8.875")],
            shared_values=shared_values,
        )
    )
    warning = _warning(result, rule_code)
    prefix = f"conflict_{field}_2025"

    assert warning.code == "finance_period_conflict"
    assert warning.evaluation_basis.years == [2025]
    assert _fact(warning, "period_consistent").exact_value is False
    assert {
        fact.exact_value
        for fact in warning.evaluation_basis.facts
        if fact.id.startswith(prefix) and "_value_" in fact.id
    } == {Decimal("7.125"), Decimal("8.875")}
    assert _fact(warning, f"{prefix}_normalized_field").exact_value == field
    assert _fact(warning, f"{prefix}_indicator_code").exact_value == (
        _INDICATOR_BY_FIELD[field][1]
    )
    assert "7.125" not in warning.message
    assert "8.875" not in warning.message


def test_nonblocking_warning_downgrades_sufficient_signals_to_medium():
    warning = NormalizationWarning(
        code="finance_years_invalid",
        path="$.balances.years",
        message="safe warning",
    )
    result = _evaluate(
        facts=finance_facts(
            [FinancialPeriod(year=2025, equity=Decimal("-1"))],
            warnings=[warning],
        )
    )
    signal = _signal(result, NEGATIVE_EQUITY)

    assert signal.confidence is SignalConfidence.MEDIUM
    assert [item.code for item in signal.warnings] == [
        "normalization_warning_present"
    ]
    assert signal.warnings[0].evaluation_basis.failed_eligibility == []


@pytest.mark.parametrize(
    ("values", "names"),
    [
        ([Decimal("-1"), Decimal("-1")], ["Капитал A", "Капитал B"]),
        ([None, Decimal("-1")], ["Капитал", "Капитал"]),
    ],
)
def test_metadata_only_or_none_plus_exact_duplicate_is_nonblocking(values, names):
    facts = _variant_facts(
        [
            FinancialPeriod(
                year=2025,
                equity=Decimal("-1"),
                net_profit=Decimal("-2"),
            )
        ],
        field="equity",
        year=2025,
        values=values,
        names=names,
    )
    result = _evaluate(facts=facts)

    equity = _signal(result, NEGATIVE_EQUITY)
    assert equity.confidence is SignalConfidence.MEDIUM
    assert [item.code for item in equity.warnings] == [
        "normalization_warning_present"
    ]
    net_loss = _signal(result, NET_LOSS)
    assert net_loss.confidence is SignalConfidence.MEDIUM
    assert [item.code for item in net_loss.warnings] == [
        "normalization_warning_present"
    ]


def test_normalized_malformed_none_plus_exact_consensus_is_nonblocking():
    payload = {
        "balances": {
            "years": [2025],
            "indicators": [
                {"name": "Капитал", "code": "1300", "sum": {"2025": "bad"}},
                {"name": "Капитал", "code": "1300", "sum": {"2025": "-1"}},
            ],
        }
    }
    facts = normalize_finance(finance_result(payload))
    result = _evaluate(facts=facts)
    signal = _signal(result, NEGATIVE_EQUITY)

    assert facts.periods[0].equity == Decimal("-1")
    assert signal.confidence is SignalConfidence.MEDIUM
    assert [item.code for item in signal.warnings] == [
        "normalization_warning_present"
    ]
    assert NEGATIVE_EQUITY not in {item.rule_code for item in result.warnings}


@pytest.mark.parametrize(
    ("form", "code", "path", "suppressed", "unaffected"),
    [
        (
            FinanceForm.BALANCE,
            "1300",
            "$.balances.indicators[0].sum.2025",
            NEGATIVE_EQUITY,
            NET_LOSS,
        ),
        (
            FinanceForm.FINANCIAL_RESULTS,
            "2110",
            "$.fin_results.indicators[0].sum.2025",
            REVENUE_DECLINE,
            CASH_SHORTFALL,
        ),
        (
            FinanceForm.BALANCE,
            "1250",
            "$.balances.indicators[0].sum.2025",
            CASH_SHORTFALL,
            HIGH_ACCOUNTS_PAYABLE,
        ),
    ],
)
def test_malformed_field_does_not_suppress_unaffected_rule(
    form, code, path, suppressed, unaffected
):
    warning = NormalizationWarning(
        code="decimal_parse_failed",
        path=path,
        message="safe parse failure",
    )
    periods = [
        FinancialPeriod(
            year=2024,
            revenue=Decimal("200"),
        ),
        FinancialPeriod(
            year=2025,
            equity=None if suppressed == NEGATIVE_EQUITY else Decimal("-1"),
            revenue=None if suppressed == REVENUE_DECLINE else Decimal("100"),
            net_profit=Decimal("-1"),
            cash_and_equivalents=(
                None if suppressed == CASH_SHORTFALL else Decimal("10")
            ),
            short_term_liabilities=Decimal("100"),
            accounts_payable=Decimal("200"),
            current_assets=Decimal("100"),
        ),
    ]
    facts = finance_facts(
        periods,
        indicators=[
            finance_indicator(form, code, source_path=path.rsplit(".sum", 1)[0])
        ],
        warnings=[warning],
    )
    result = _evaluate(facts=facts)

    assert suppressed in {item.rule_code for item in result.warnings}
    signal = _signal(result, unaffected)
    assert signal.confidence is SignalConfidence.MEDIUM


def test_warning_for_another_year_does_not_suppress_selected_year():
    warning = NormalizationWarning(
        code="decimal_parse_failed",
        path="$.balances.indicators[0].sum.2024",
        message="safe parse failure",
    )
    facts = finance_facts(
        [
            FinancialPeriod(year=2024, equity=None),
            FinancialPeriod(year=2025, equity=Decimal("-1")),
        ],
        indicators=[
            finance_indicator(
                FinanceForm.BALANCE,
                "1300",
                source_path="$.balances.indicators[0]",
                values_by_year={2024: None, 2025: Decimal("-1")},
            )
        ],
        warnings=[warning],
    )
    signal = _signal(_evaluate(facts=facts), NEGATIVE_EQUITY)

    assert signal.period == YearPeriod(year=2025)
    assert signal.confidence is SignalConfidence.MEDIUM


def test_low_confidence_suppresses_only_triggered_rules(monkeypatch):
    monkeypatch.setattr(
        finance_signals,
        "_confidence_for",
        lambda _facts: SignalConfidence.LOW,
    )
    result = _evaluate(
        [
            FinancialPeriod(
                year=2024,
                revenue=Decimal("100"),
                equity=Decimal("1"),
            ),
            FinancialPeriod(
                year=2025,
                revenue=Decimal("90"),
                net_profit=Decimal("-1"),
            ),
        ]
    )

    assert result.signals == []
    insufficient = {
        warning.rule_code
        for warning in result.warnings
        if warning.code == "signal_confidence_insufficient"
    }
    assert insufficient == {REVENUE_DECLINE, NET_LOSS}


def test_period_indicator_and_warning_permutations_are_canonical():
    first_warning = NormalizationWarning(
        code="finance_years_invalid",
        path="$.balances.years",
        message="safe first",
    )
    second_warning = NormalizationWarning(
        code="finance_invalid_year",
        path="$.fin_results.years",
        message="safe second",
    )
    periods = [
        FinancialPeriod(
            year=2024,
            revenue=Decimal("100"),
            equity=Decimal("-1"),
            net_profit=Decimal("-2"),
            cash_and_equivalents=Decimal("10"),
            short_term_liabilities=Decimal("100"),
            accounts_payable=Decimal("200"),
            current_assets=Decimal("100"),
        ),
        FinancialPeriod(
            year=2025,
            revenue=Decimal("90"),
            equity=Decimal("-1"),
            net_profit=Decimal("-2"),
            cash_and_equivalents=Decimal("10"),
            short_term_liabilities=Decimal("100"),
            accounts_payable=Decimal("200"),
            current_assets=Decimal("100"),
        ),
        FinancialPeriod(
            year=2025,
            revenue=Decimal("90"),
            equity=Decimal("-1"),
            net_profit=Decimal("-2"),
            cash_and_equivalents=Decimal("10"),
            short_term_liabilities=Decimal("100"),
            accounts_payable=Decimal("200"),
            current_assets=Decimal("100"),
        ),
    ]
    indicators = [
        finance_indicator(
            FinanceForm.BALANCE,
            "1300",
            source_path="$.balances.indicators[0]",
            values_by_year={2024: Decimal("-1"), 2025: Decimal("-1")},
        ),
        finance_indicator(
            FinanceForm.FINANCIAL_RESULTS,
            "2110",
            source_path="$.fin_results.indicators[0]",
            values_by_year={2024: Decimal("100"), 2025: Decimal("90")},
        ),
    ]
    left = _evaluate(
        facts=finance_facts(
            periods,
            indicators=indicators,
            warnings=[first_warning, second_warning],
        )
    )
    right = _evaluate(
        facts=finance_facts(
            list(reversed(periods)),
            indicators=list(reversed(indicators)),
            warnings=[second_warning, first_warning],
        )
    )

    assert left.model_dump(mode="json") == right.model_dump(mode="json")
    assert canonical_representation(left) == canonical_representation(right)
    assert len({signal.code for signal in left.signals}) == len(left.signals)
    assert all("reporting_absent" not in signal.code for signal in left.signals)
    assert all(signal.period.kind != "no_period" for signal in left.signals)
    assert all(len(signal.source) == 1 for signal in left.signals)
    assert all(signal.source[0].dataset == "finance" for signal in left.signals)


def test_internal_evaluator_has_no_public_export_or_report_mutation():
    report = finance_company_report(
        finance=finance_facts(
            [FinancialPeriod(year=2025, equity=Decimal("-1"))]
        )
    )
    before = report.model_dump(mode="json")

    finance_signals._evaluate_finance_signals(report)

    assert report.model_dump(mode="json") == before
    assert not hasattr(finance_signals, "evaluate_signals")
    assert finance_signals.__all__ == []
