from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal

from product_api.company_reports.aggregate import CompanyReport, DatasetReportStatus
from product_api.company_reports.models import (
    FinanceFacts,
    FinanceForm,
    FinancialPeriod,
    NormalizationWarning,
)

from .common import canonical_representation
from .models import (
    AllOfExpression,
    ComparisonComparator,
    DecimalComparisonOperator,
    EqualityOperator,
    ExpressionNode,
    FactOperand,
    InequalityOperator,
    LiteralOperand,
    PredicateExpression,
    PresenceOperator,
    Signal,
    SignalCategory,
    SignalConfidence,
    SignalDirection,
    SignalEvaluationBasis,
    SignalEvaluationResult,
    SignalFact,
    SignalFactualBasis,
    SignalPeriodBasis,
    SignalPeriodOperation,
    SignalStrength,
    SignalStrengthDecision,
    SignalStrengthOverride,
    SignalWarning,
    YearPeriod,
    YearRangePeriod,
    evaluate_expression,
    failed_expression_nodes,
)


_DATASET = "finance"
_AVAILABLE = DatasetReportStatus.AVAILABLE.value
_ZERO = Decimal("0")
_CASH_HIGH_FACTOR = Decimal("0.25")

_FIELD_INDICATORS: dict[str, tuple[FinanceForm, str]] = {
    "current_assets": (FinanceForm.BALANCE, "1200"),
    "cash_and_equivalents": (FinanceForm.BALANCE, "1250"),
    "equity": (FinanceForm.BALANCE, "1300"),
    "short_term_liabilities": (FinanceForm.BALANCE, "1500"),
    "accounts_payable": (FinanceForm.BALANCE, "1520"),
    "revenue": (FinanceForm.FINANCIAL_RESULTS, "2110"),
    "net_profit": (FinanceForm.FINANCIAL_RESULTS, "2400"),
}
_FORM_PATHS = {
    FinanceForm.BALANCE: "$.balances",
    FinanceForm.FINANCIAL_RESULTS: "$.fin_results",
    FinanceForm.CASH_FLOW: "$.money_flow",
}
_STRUCTURAL_WARNING_CODES = {
    "decimal_parse_failed",
    "finance_form_invalid",
}


@dataclass(frozen=True)
class _Rule:
    code: str
    fields: tuple[str, ...]
    default_strength: SignalStrength
    prepare: Callable[[CompanyReport, "_Rule", SignalConfidence], "_PreparedRule"]


@dataclass(frozen=True)
class _ResolvedYear:
    year: int
    values: dict[str, Decimal | None]
    conflicts: dict[str, "_FieldConflict"]


@dataclass(frozen=True)
class _FieldConflict:
    form: FinanceForm
    indicator_code: str
    normalized_field: str
    values: tuple[Decimal, ...]
    source_paths: tuple[str, ...]


@dataclass(frozen=True)
class _PreparedRule:
    facts: list[SignalFact]
    eligibility: ExpressionNode
    trigger: ExpressionNode
    strength_decision: SignalStrengthDecision
    years: list[int]
    period: YearPeriod | YearRangePeriod | None
    period_basis: SignalPeriodBasis | None
    conflict: bool
    structural_inputs_usable: bool


def _fact(fact_id: str, normalized_path: str, value: object) -> SignalFact:
    return SignalFact(id=fact_id, normalized_path=normalized_path, exact_value=value)


def _equal(fact_id: str, value: object) -> PredicateExpression:
    return PredicateExpression(
        fact_id=fact_id,
        operator=EqualityOperator(operand=LiteralOperand(value=value)),
    )


def _not_equal(fact_id: str, value: object) -> PredicateExpression:
    return PredicateExpression(
        fact_id=fact_id,
        operator=InequalityOperator(operand=LiteralOperand(value=value)),
    )


def _presence(fact_id: str) -> PredicateExpression:
    return PredicateExpression(fact_id=fact_id, operator=PresenceOperator())


def _decimal_literal(
    fact_id: str,
    comparator: ComparisonComparator,
    value: Decimal,
) -> PredicateExpression:
    return PredicateExpression(
        fact_id=fact_id,
        operator=DecimalComparisonOperator(
            comparator=comparator,
            operand=LiteralOperand(value=value),
        ),
    )


def _decimal_fact(
    fact_id: str,
    comparator: ComparisonComparator,
    other_fact_id: str,
) -> PredicateExpression:
    return PredicateExpression(
        fact_id=fact_id,
        operator=DecimalComparisonOperator(
            comparator=comparator,
            operand=FactOperand(fact_id=other_fact_id),
        ),
    )


def _eligibility() -> AllOfExpression:
    return AllOfExpression(
        children=[
            _equal("dataset_status", _AVAILABLE),
            _equal("finance_facts_present", True),
            _equal("finance_source_usable", True),
            _presence("finance_unit"),
            _equal("units_comparable", True),
            _equal("required_facts_available", True),
            _equal("required_period_available", True),
            _equal("period_consistent", True),
            _equal("structural_inputs_usable", True),
            _not_equal("signal_confidence", SignalConfidence.LOW.value),
        ]
    )


def _normalization_warnings(finance: FinanceFacts | None) -> list[NormalizationWarning]:
    if finance is None:
        return []
    unique = {
        canonical_representation(warning): warning
        for warning in [*finance.warnings, *finance.source.warnings]
    }
    return [unique[key] for key in sorted(unique)]


def _confidence_for(finance: FinanceFacts | None) -> SignalConfidence:
    return (
        SignalConfidence.MEDIUM
        if _normalization_warnings(finance)
        else SignalConfidence.HIGH
    )


def _group_periods(finance: FinanceFacts | None) -> dict[int, list[FinancialPeriod]]:
    grouped: dict[int, list[FinancialPeriod]] = {}
    if finance is None:
        return grouped
    for period in finance.periods:
        grouped.setdefault(period.year, []).append(period)
    return {year: grouped[year] for year in sorted(grouped)}


def _resolved_years(
    finance: FinanceFacts | None,
    fields: tuple[str, ...],
) -> list[_ResolvedYear]:
    if finance is None:
        return []
    grouped_periods = _group_periods(finance)
    matching_series = {
        field: [
            series
            for series in finance.indicators
            if (series.form, series.code) == _FIELD_INDICATORS[field]
        ]
        for field in fields
    }
    years = set(finance.years) | set(grouped_periods)
    for series_items in matching_series.values():
        for series in series_items:
            years.update(series.values_by_year)
    resolved: list[_ResolvedYear] = []
    for year in sorted(years):
        values: dict[str, Decimal | None] = {}
        conflicts: dict[str, _FieldConflict] = {}
        for field in fields:
            series_items = matching_series[field]
            if series_items:
                exact_values = sorted(
                    {
                        value
                        for series in series_items
                        if (value := series.values_by_year.get(year)) is not None
                    }
                )
            else:
                exact_values = sorted(
                    {
                        value
                        for period in grouped_periods.get(year, [])
                        if (value := getattr(period, field)) is not None
                    }
                )
            if series_items and len(exact_values) > 1:
                form, code = _FIELD_INDICATORS[field]
                conflicts[field] = _FieldConflict(
                    form=form,
                    indicator_code=code,
                    normalized_field=field,
                    values=tuple(exact_values),
                    source_paths=tuple(
                        sorted(
                            {
                                path
                                for series in series_items
                                for path in series.source_paths
                            }
                        )
                    ),
                )
                values[field] = None
            else:
                values[field] = exact_values[0] if exact_values else None
        resolved.append(_ResolvedYear(year=year, values=values, conflicts=conflicts))
    return resolved


def _warning_year(path: str) -> int | None:
    matches = re.findall(r"(?<!\d)(\d{4})(?!\d)", path)
    return int(matches[-1]) if matches else None


def _warning_targets_field(
    warning: NormalizationWarning,
    finance: FinanceFacts,
    field: str,
) -> bool:
    path = warning.path.lower()
    form, code = _FIELD_INDICATORS[field]
    if field in path or re.search(rf"(?:^|[^0-9]){re.escape(code)}(?:[^0-9]|$)", path):
        return True
    if warning.code == "finance_form_invalid":
        return path == _FORM_PATHS[form] or path.startswith(f"{_FORM_PATHS[form]}.")
    for series in finance.indicators:
        if series.form is not form or series.code != code:
            continue
        for source_path in series.source_paths:
            normalized_source = source_path.lower()
            if path == normalized_source or path.startswith(f"{normalized_source}."):
                return True
            if normalized_source.startswith(f"{path}."):
                return True
    return False


def _blocking_warning(
    warning: NormalizationWarning,
    finance: FinanceFacts,
    fields: tuple[str, ...],
    years: Iterable[int],
) -> bool:
    if warning.code not in _STRUCTURAL_WARNING_CODES:
        return False
    if not any(_warning_targets_field(warning, finance, field) for field in fields):
        return False
    warning_year = _warning_year(warning.path)
    selected_years = set(years)
    return warning_year is None or warning_year in selected_years


def _common_facts(
    report: CompanyReport,
    confidence: SignalConfidence,
    *,
    required_facts_available: bool,
    required_period_available: bool,
    period_consistent: bool,
    structural_inputs_usable: bool,
) -> list[SignalFact]:
    finance = report.finance
    dataset = report.datasets.get(_DATASET)
    return [
        _fact(
            "dataset_status",
            "datasets.finance.status",
            dataset.status.value if dataset is not None else None,
        ),
        _fact("finance_facts_present", "finance", finance is not None),
        _fact(
            "finance_source_usable",
            "finance.source",
            finance is not None and finance.source.received_at is not None,
        ),
        _fact("finance_unit", "finance.unit", finance.unit if finance is not None else None),
        _fact(
            "units_comparable",
            "derived.finance.units_comparable",
            finance is not None and finance.unit == "provider_units_unknown",
        ),
        _fact(
            "required_facts_available",
            "derived.finance.required_facts_available",
            required_facts_available,
        ),
        _fact(
            "required_period_available",
            "derived.finance.required_period_available",
            required_period_available,
        ),
        _fact(
            "period_consistent",
            "derived.finance.period_consistent",
            period_consistent,
        ),
        _fact(
            "structural_inputs_usable",
            "derived.finance.structural_inputs_usable",
            structural_inputs_usable,
        ),
        _fact(
            "normalization_warning_count",
            "derived.finance.normalization_warning_count",
            len(_normalization_warnings(finance)),
        ),
        _fact("signal_confidence", "derived.signals.confidence", confidence.value),
    ]


def _conflict_facts(conflicts: Iterable[_ResolvedYear]) -> list[SignalFact]:
    result: list[SignalFact] = []
    for resolved in conflicts:
        result.append(
            _fact(
                f"conflict_year_{resolved.year}",
                "finance.periods.year",
                resolved.year,
            )
        )
        for field in sorted(resolved.conflicts):
            conflict = resolved.conflicts[field]
            prefix = f"conflict_{field}_{resolved.year}"
            result.extend(
                [
                    _fact(
                        f"{prefix}_form",
                        "finance.indicators.form",
                        conflict.form.value,
                    ),
                    _fact(
                        f"{prefix}_indicator_code",
                        "finance.indicators.code",
                        conflict.indicator_code,
                    ),
                    _fact(
                        f"{prefix}_normalized_field",
                        "derived.finance.conflict.normalized_field",
                        conflict.normalized_field,
                    ),
                ]
            )
            for index, value in enumerate(conflict.values):
                result.append(
                    _fact(
                        f"{prefix}_value_{index}",
                        "finance.indicators.values_by_year",
                        value,
                    )
                )
            for index, path in enumerate(conflict.source_paths):
                result.append(
                    _fact(
                        f"{prefix}_source_path_{index}",
                        "finance.indicators.source_paths",
                        path,
                    )
                )
    return result


def _single_year_preparation(
    report: CompanyReport,
    rule: _Rule,
    confidence: SignalConfidence,
) -> tuple[
    list[SignalFact],
    _ResolvedYear | None,
    list[_ResolvedYear],
    bool,
]:
    finance = report.finance
    resolved = _resolved_years(finance, rule.fields)
    candidates = [
        item
        for item in resolved
        if not item.conflicts and all(item.values[field] is not None for field in rule.fields)
    ]
    selected = candidates[-1] if candidates else None
    potentially_eligible_conflicts = [
        item
        for item in resolved
        if all(
            item.values[field] is not None or field in item.conflicts
            for field in rule.fields
        )
        and any(field in item.conflicts for field in rule.fields)
    ]
    blocking_conflict = (
        potentially_eligible_conflicts[-1]
        if selected is None and potentially_eligible_conflicts
        else None
    )
    basis_years = (
        [selected.year] if selected is not None else [item.year for item in resolved]
    )
    structural_usable = selected is not None or not (
        finance is not None
        and any(
            _blocking_warning(warning, finance, rule.fields, basis_years)
            for warning in _normalization_warnings(finance)
        )
    )
    conflict_blocks = blocking_conflict is not None
    common = _common_facts(
        report,
        confidence,
        required_facts_available=selected is not None or conflict_blocks,
        required_period_available=bool(resolved),
        period_consistent=not conflict_blocks,
        structural_inputs_usable=structural_usable,
    )
    return (
        common,
        selected,
        [blocking_conflict] if blocking_conflict is not None else [],
        structural_usable,
    )


def _prepare_single(
    report: CompanyReport,
    rule: _Rule,
    confidence: SignalConfidence,
) -> _PreparedRule:
    common, selected, conflicts, structural_usable = _single_year_preparation(
        report, rule, confidence
    )
    selected_year = selected.year if selected is not None else None
    value_facts = [
        _fact(
            field,
            f"finance.periods.{field}",
            selected.values[field] if selected is not None else None,
        )
        for field in rule.fields
    ]
    facts = [
        *common,
        _fact("selected_year", "finance.periods.year", selected_year),
        *value_facts,
        *_conflict_facts(conflicts),
    ]
    if rule.code == "finance.negative_equity":
        trigger = _decimal_literal(
            "equity", ComparisonComparator.LESS_THAN, _ZERO
        )
    elif rule.code == "finance.net_loss":
        trigger = _decimal_literal(
            "net_profit", ComparisonComparator.LESS_THAN, _ZERO
        )
    elif rule.code == "finance.high_accounts_payable":
        trigger = _decimal_fact(
            "accounts_payable", ComparisonComparator.GREATER_THAN, "current_assets"
        )
    else:
        raise AssertionError(f"unsupported single-year rule: {rule.code}")
    return _PreparedRule(
        facts=facts,
        eligibility=_eligibility(),
        trigger=trigger,
        strength_decision=SignalStrengthDecision(
            default_strength=rule.default_strength
        ),
        years=[selected_year] if selected_year is not None else [item.year for item in conflicts],
        period=YearPeriod(year=selected_year) if selected_year is not None else None,
        period_basis=(
            SignalPeriodBasis(
                fact_ids=["selected_year"],
                operation=SignalPeriodOperation.YEAR,
            )
            if selected_year is not None
            else None
        ),
        conflict=bool(conflicts),
        structural_inputs_usable=structural_usable,
    )


def _prepare_revenue(
    report: CompanyReport,
    rule: _Rule,
    confidence: SignalConfidence,
) -> _PreparedRule:
    finance = report.finance
    resolved = _resolved_years(finance, rule.fields)
    conflicts = [item for item in resolved if item.conflicts]
    candidates = [
        item
        for item in resolved
        if not item.conflicts and item.values["revenue"] is not None
    ]
    candidates_by_year = {item.year: item for item in candidates}
    clean_pairs = [
        (candidates_by_year[later_year - 1], candidates_by_year[later_year])
        for later_year in sorted(candidates_by_year)
        if later_year - 1 in candidates_by_year
    ]
    selected = list(clean_pairs[-1]) if clean_pairs else []
    two_years = len(selected) == 2
    consecutive = two_years
    selected_years = [item.year for item in selected]
    basis_years = selected_years if two_years else [item.year for item in resolved]
    structural_usable = two_years or not (
        finance is not None
        and any(
            _blocking_warning(warning, finance, rule.fields, basis_years)
            for warning in _normalization_warnings(finance)
        )
    )
    potential_by_year = {
        item.year: item
        for item in [*candidates, *conflicts]
    }
    blocking_pairs = [
        (potential_by_year[later_year - 1], potential_by_year[later_year])
        for later_year in sorted(potential_by_year)
        if later_year - 1 in potential_by_year
        and (
            potential_by_year[later_year - 1].conflicts
            or potential_by_year[later_year].conflicts
        )
    ]
    blocking_pair = blocking_pairs[-1] if not two_years and blocking_pairs else None
    blocking_conflicts = (
        [item for item in blocking_pair if item.conflicts]
        if blocking_pair is not None
        else []
    )
    conflict_blocks = bool(blocking_conflicts)
    facts = [
        *_common_facts(
            report,
            confidence,
            required_facts_available=two_years or conflict_blocks,
            required_period_available=two_years and consecutive,
            period_consistent=not conflict_blocks,
            structural_inputs_usable=structural_usable,
        ),
        _fact(
            "previous_year",
            "finance.periods.year",
            selected[0].year if two_years else None,
        ),
        _fact(
            "later_year",
            "finance.periods.year",
            selected[1].year if two_years else None,
        ),
        _fact(
            "previous_revenue",
            "finance.periods.revenue",
            selected[0].values["revenue"] if two_years else None,
        ),
        _fact(
            "later_revenue",
            "finance.periods.revenue",
            selected[1].values["revenue"] if two_years else None,
        ),
        *_conflict_facts(blocking_conflicts),
    ]
    trigger = _decimal_fact(
        "later_revenue", ComparisonComparator.LESS_THAN, "previous_revenue"
    )
    return _PreparedRule(
        facts=facts,
        eligibility=_eligibility(),
        trigger=trigger,
        strength_decision=SignalStrengthDecision(
            default_strength=rule.default_strength
        ),
        years=(
            selected_years
            if two_years
            else [item.year for item in blocking_conflicts]
        ),
        period=(
            YearRangePeriod(
                start_year=selected[0].year,
                end_year=selected[1].year,
            )
            if two_years and consecutive
            else None
        ),
        period_basis=(
            SignalPeriodBasis(
                fact_ids=["previous_year", "later_year"],
                operation=SignalPeriodOperation.YEAR_RANGE,
            )
            if two_years and consecutive
            else None
        ),
        conflict=conflict_blocks,
        structural_inputs_usable=structural_usable,
    )


def _prepare_cash(
    report: CompanyReport,
    rule: _Rule,
    confidence: SignalConfidence,
) -> _PreparedRule:
    common, selected, conflicts, structural_usable = _single_year_preparation(
        report, rule, confidence
    )
    selected_year = selected.year if selected is not None else None
    cash = selected.values["cash_and_equivalents"] if selected is not None else None
    liabilities = (
        selected.values["short_term_liabilities"] if selected is not None else None
    )
    threshold = (
        liabilities * _CASH_HIGH_FACTOR
        if isinstance(liabilities, Decimal)
        else None
    )
    facts = [
        *common,
        _fact("selected_year", "finance.periods.year", selected_year),
        _fact("cash_and_equivalents", "finance.periods.cash_and_equivalents", cash),
        _fact(
            "short_term_liabilities",
            "finance.periods.short_term_liabilities",
            liabilities,
        ),
        _fact(
            "cash_shortfall_high_factor",
            "derived.finance.cash_shortfall_high_factor",
            _CASH_HIGH_FACTOR,
        ),
        _fact(
            "short_term_liabilities_25_percent",
            "derived.finance.short_term_liabilities_25_percent",
            threshold,
        ),
        *_conflict_facts(conflicts),
    ]
    high_override = AllOfExpression(
        children=[
            _decimal_fact(
                "cash_and_equivalents",
                ComparisonComparator.LESS_THAN,
                "short_term_liabilities_25_percent",
            ),
            _decimal_literal(
                "cash_shortfall_high_factor",
                ComparisonComparator.EQUALITY,
                _CASH_HIGH_FACTOR,
            ),
        ]
    )
    return _PreparedRule(
        facts=facts,
        eligibility=_eligibility(),
        trigger=_decimal_fact(
            "cash_and_equivalents",
            ComparisonComparator.LESS_THAN,
            "short_term_liabilities",
        ),
        strength_decision=SignalStrengthDecision(
            default_strength=SignalStrength.MEDIUM,
            overrides=[
                SignalStrengthOverride(
                    when=high_override,
                    strength=SignalStrength.HIGH,
                )
            ],
        ),
        years=[selected_year] if selected_year is not None else [item.year for item in conflicts],
        period=YearPeriod(year=selected_year) if selected_year is not None else None,
        period_basis=(
            SignalPeriodBasis(
                fact_ids=["selected_year"],
                operation=SignalPeriodOperation.YEAR,
            )
            if selected_year is not None
            else None
        ),
        conflict=bool(conflicts),
        structural_inputs_usable=structural_usable,
    )


_RULES = (
    _Rule(
        code="finance.negative_equity",
        fields=("equity",),
        default_strength=SignalStrength.HIGH,
        prepare=_prepare_single,
    ),
    _Rule(
        code="finance.revenue_decline",
        fields=("revenue",),
        default_strength=SignalStrength.MEDIUM,
        prepare=_prepare_revenue,
    ),
    _Rule(
        code="finance.net_loss",
        fields=("net_profit",),
        default_strength=SignalStrength.MEDIUM,
        prepare=_prepare_single,
    ),
    _Rule(
        code="finance.cash_shortfall",
        fields=("cash_and_equivalents", "short_term_liabilities"),
        default_strength=SignalStrength.MEDIUM,
        prepare=_prepare_cash,
    ),
    _Rule(
        code="finance.high_accounts_payable",
        fields=("accounts_payable", "current_assets"),
        default_strength=SignalStrength.HIGH,
        prepare=_prepare_single,
    ),
)


_WARNING_MESSAGES = {
    "dataset_unavailable": "Finance dataset is unavailable for signal evaluation.",
    "required_fact_missing": "A required normalized finance fact is unavailable.",
    "required_period_unavailable": "The required finance period cannot be constructed.",
    "normalization_warning_present": "Finance normalization warnings reduce signal confidence.",
    "finance_period_conflict": "Financial periods conflict for this rule.",
    "signal_confidence_insufficient": "Finance signal confidence is insufficient.",
}


def _warning(
    code: str,
    rule: _Rule,
    prepared: _PreparedRule,
    *,
    failed_eligibility: list[ExpressionNode] | None = None,
) -> SignalWarning:
    failed = (
        failed_expression_nodes(prepared.eligibility, prepared.facts)
        if failed_eligibility is None
        else failed_eligibility
    )
    return SignalWarning(
        code=code,
        rule_code=rule.code,
        dataset=_DATASET,
        message=_WARNING_MESSAGES[code],
        evaluation_basis=SignalEvaluationBasis(
            facts=prepared.facts,
            eligibility=prepared.eligibility,
            failed_eligibility=failed,
            years=prepared.years,
            case_ids=[],
        ),
    )


def _suppression_code(prepared: _PreparedRule) -> str:
    values = {fact.id: fact.exact_value for fact in prepared.facts}
    if values["dataset_status"] != _AVAILABLE:
        return "dataset_unavailable"
    if values["finance_facts_present"] is not True:
        return "required_fact_missing"
    if prepared.conflict:
        return "finance_period_conflict"
    if values["required_period_available"] is not True:
        return "required_period_unavailable"
    if values["required_facts_available"] is not True:
        return "required_fact_missing"
    if prepared.structural_inputs_usable is not True:
        return "required_fact_missing"
    return "signal_confidence_insufficient"


def _evaluate_rule(
    report: CompanyReport,
    rule: _Rule,
    confidence: SignalConfidence,
) -> tuple[Signal | None, SignalWarning | None]:
    prepared = rule.prepare(report, rule, confidence)
    eligible = evaluate_expression(prepared.eligibility, prepared.facts)
    triggered = evaluate_expression(prepared.trigger, prepared.facts)
    if not eligible:
        code = _suppression_code(prepared)
        if code == "signal_confidence_insufficient" and not triggered:
            return None, None
        return None, _warning(code, rule, prepared)
    if not triggered:
        return None, None
    if prepared.period is None or prepared.period_basis is None:
        raise AssertionError("eligible triggered finance rule requires a period")
    finance = report.finance
    if finance is None:
        raise AssertionError("eligible finance rule requires normalized facts")
    strength = prepared.strength_decision.default_strength
    for override in prepared.strength_decision.overrides:
        if evaluate_expression(override.when, prepared.facts):
            strength = override.strength
            break
    signal_warnings = (
        [
            _warning(
                "normalization_warning_present",
                rule,
                prepared,
                failed_eligibility=[],
            )
        ]
        if confidence is SignalConfidence.MEDIUM
        else []
    )
    return (
        Signal(
            code=rule.code,
            category=SignalCategory.FINANCIAL,
            direction=SignalDirection.NEGATIVE,
            strength=strength,
            factual_basis=SignalFactualBasis(
                facts=prepared.facts,
                eligibility=prepared.eligibility,
                trigger=prepared.trigger,
                strength_decision=prepared.strength_decision,
                period_basis=prepared.period_basis,
                years=prepared.years,
                case_ids=[],
            ),
            source=[finance.source],
            period=prepared.period,
            confidence=confidence,
            warnings=signal_warnings,
        ),
        None,
    )


def _evaluate_finance_signals(report: CompanyReport) -> SignalEvaluationResult:
    """Evaluate Stage 3 finance rules without composing other categories."""

    confidence = _confidence_for(report.finance)
    signals: list[Signal] = []
    warnings: list[SignalWarning] = []
    for rule in _RULES:
        signal, warning = _evaluate_rule(report, rule, confidence)
        if signal is not None:
            signals.append(signal)
        if warning is not None:
            warnings.append(warning)
    return SignalEvaluationResult(signals=signals, warnings=warnings)


__all__: list[str] = []
