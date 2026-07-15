from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from product_api.company_reports.aggregate import CompanyReport, DatasetReportStatus
from product_api.company_reports.models import (
    ArbitrationCaseFacts,
    ArbitrationFacts,
    ArbitrationRole,
    ArbitrationStatus,
    NormalizationWarning,
)

from .common import canonical_representation
from .models import (
    AllOfExpression,
    ComparisonComparator,
    CountOperator,
    EqualityOperator,
    ExpressionNode,
    FactOperand,
    GreaterThanOperator,
    InequalityOperator,
    LiteralOperand,
    PredicateExpression,
    Signal,
    SignalCategory,
    SignalConfidence,
    SignalDirection,
    SignalEvaluationBasis,
    SignalEvaluationResult,
    SignalFact,
    SignalFactualBasis,
    SignalPeriod,
    SignalPeriodBasis,
    SignalPeriodOperation,
    SignalStrength,
    SignalStrengthDecision,
    SignalWarning,
    YearPeriod,
    YearRangePeriod,
    evaluate_expression,
    failed_expression_nodes,
)


_DATASET = "arbitration"
_AVAILABLE = DatasetReportStatus.AVAILABLE.value


@dataclass(frozen=True)
class _PreparedRule:
    facts: list[SignalFact]
    eligibility: ExpressionNode
    trigger: ExpressionNode
    years: list[int]
    case_ids: list[str]
    period: SignalPeriod | None
    period_basis: SignalPeriodBasis | None


@dataclass(frozen=True)
class _Rule:
    code: str
    direction: SignalDirection
    strength: SignalStrength
    prepare: Callable[[CompanyReport, SignalConfidence], _PreparedRule]


def _fact(fact_id: str, normalized_path: str, value: object) -> SignalFact:
    return SignalFact(
        id=fact_id,
        normalized_path=normalized_path,
        exact_value=value,
    )


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


def _count_at_least(fact_id: str, value: int) -> PredicateExpression:
    return PredicateExpression(
        fact_id=fact_id,
        operator=CountOperator(
            comparator=ComparisonComparator.GREATER_OR_EQUAL,
            value=value,
        ),
    )


def _greater_than_fact(
    fact_id: str,
    other_fact_id: str,
) -> PredicateExpression:
    return PredicateExpression(
        fact_id=fact_id,
        operator=GreaterThanOperator(operand=FactOperand(fact_id=other_fact_id)),
    )


def _common_eligibility() -> AllOfExpression:
    return AllOfExpression(
        children=[
            _equal("dataset_status", _AVAILABLE),
            _equal("arbitration_facts_present", True),
            _equal("arbitration_is_complete", True),
            _equal("structural_inputs_usable", True),
            _equal("summary_consistent", True),
            _equal("period_available", True),
            _equal("case_ids_available", True),
            _not_equal("signal_confidence", SignalConfidence.LOW.value),
        ]
    )


def _normalization_warnings(
    arbitration: ArbitrationFacts | None,
) -> list[NormalizationWarning]:
    if arbitration is None:
        return []
    warnings = [*arbitration.warnings, *arbitration.source.warnings]
    unique = {
        canonical_representation(warning): warning
        for warning in warnings
    }
    return [unique[key] for key in sorted(unique)]


def _confidence_for(arbitration: ArbitrationFacts | None) -> SignalConfidence:
    return (
        SignalConfidence.MEDIUM
        if _normalization_warnings(arbitration)
        else SignalConfidence.HIGH
    )


def _warning_is_case_collection_structural(
    warning: NormalizationWarning,
) -> bool:
    if warning.code == "arbitration_case_invalid":
        return True
    return warning.code == "integer_parse_failed" and warning.path in {
        "$.total_cases",
        "$.offset",
    }


_ROLE_CONTAINER_MARKERS = {
    ".plaintiffs": ArbitrationRole.PLAINTIFF,
    ".respondents": ArbitrationRole.RESPONDENT,
    ".applicants": ArbitrationRole.APPLICANT,
    ".creditors": ArbitrationRole.CREDITOR,
    ".debtors": ArbitrationRole.DEBTOR,
    ".interested_persons": ArbitrationRole.INTERESTED_PERSON,
    ".third_parties": ArbitrationRole.THIRD_PARTY,
    ".others": ArbitrationRole.OTHER,
}


def _warning_is_role_structural(
    warning: NormalizationWarning,
    *,
    used_roles: frozenset[ArbitrationRole],
) -> bool:
    code = warning.code.lower()
    path = warning.path.lower()
    affected_roles = {
        role
        for marker, role in _ROLE_CONTAINER_MARKERS.items()
        if marker in path
    }
    if affected_roles:
        return bool(affected_roles.intersection(used_roles))
    return (
        "arbitration_parties" in code
        or "arbitration_party" in code
        or "role" in code
        or ".company_roles" in path
    )


def _warning_is_status_structural(warning: NormalizationWarning) -> bool:
    return "status" in warning.code.lower() or ".status" in warning.path.lower()


def _roles_are_usable(cases: Iterable[ArbitrationCaseFacts]) -> bool:
    return all(
        bool(set(case.company_roles) - {ArbitrationRole.UNKNOWN})
        for case in cases
    )


def _statuses_are_usable(cases: Iterable[ArbitrationCaseFacts]) -> bool:
    return all(
        case.normalized_status is not ArbitrationStatus.UNKNOWN
        for case in cases
    )


def _case_has_role(case: ArbitrationCaseFacts, role: ArbitrationRole) -> bool:
    return role in set(case.company_roles)


def _case_identifier(case: ArbitrationCaseFacts) -> str | None:
    if case.case_number:
        return case.case_number
    if case.internal_id:
        return case.internal_id
    return None


def _case_identifiers(
    cases: Iterable[ArbitrationCaseFacts],
) -> tuple[list[str], bool]:
    identifiers: list[str] = []
    available = True
    for case in cases:
        identifier = _case_identifier(case)
        if identifier is None:
            available = False
        else:
            identifiers.append(identifier)
    return sorted(set(identifiers)), available


def _period_from_years(
    years: Iterable[int],
) -> tuple[SignalPeriod | None, SignalPeriodBasis | None]:
    ordered = sorted(set(years))
    if not ordered:
        return None, None
    if len(ordered) == 1:
        return (
            YearPeriod(year=ordered[0]),
            SignalPeriodBasis(
                fact_ids=["period_start_year"],
                operation=SignalPeriodOperation.YEAR,
            ),
        )
    return (
        YearRangePeriod(start_year=ordered[0], end_year=ordered[-1]),
        SignalPeriodBasis(
            fact_ids=["period_start_year", "period_end_year"],
            operation=SignalPeriodOperation.YEAR_RANGE,
        ),
    )


def _common_facts(
    report: CompanyReport,
    confidence: SignalConfidence,
    *,
    structural_inputs_usable: bool,
    summary_consistent: bool,
    period_available: bool,
    case_ids_available: bool,
) -> list[SignalFact]:
    arbitration = report.arbitration
    dataset = report.datasets.get(_DATASET)
    warnings = _normalization_warnings(arbitration)
    return [
        _fact(
            "dataset_status",
            "datasets.arbitration.status",
            dataset.status.value if dataset is not None else None,
        ),
        _fact(
            "arbitration_facts_present",
            "arbitration",
            arbitration is not None,
        ),
        _fact(
            "arbitration_is_complete",
            "arbitration.is_complete",
            arbitration.is_complete if arbitration is not None else None,
        ),
        _fact(
            "structural_inputs_usable",
            "derived.arbitration.structural_inputs_usable",
            structural_inputs_usable,
        ),
        _fact(
            "summary_consistent",
            "derived.arbitration.summary_consistent",
            summary_consistent,
        ),
        _fact(
            "period_available",
            "derived.arbitration.period_available",
            period_available,
        ),
        _fact(
            "case_ids_available",
            "derived.arbitration.case_ids_available",
            case_ids_available,
        ),
        _fact(
            "normalization_warning_count",
            "derived.arbitration.normalization_warning_count",
            len(warnings),
        ),
        _fact(
            "signal_confidence",
            "derived.signals.confidence",
            confidence.value,
        ),
    ]


def _full_dataset_context(
    report: CompanyReport,
) -> tuple[
    ArbitrationFacts | None,
    list[ArbitrationCaseFacts],
    list[int],
    list[str],
    bool,
    bool,
]:
    arbitration = report.arbitration
    cases = list(arbitration.cases) if arbitration is not None else []
    years = [case.year for case in cases if case.year is not None]
    period_available = not cases or len(years) == len(cases)
    case_ids, case_ids_available = _case_identifiers(cases)
    return (
        arbitration,
        cases,
        sorted(set(years)),
        case_ids,
        period_available,
        case_ids_available,
    )


def _role_structural_inputs_usable(
    arbitration: ArbitrationFacts | None,
    cases: list[ArbitrationCaseFacts],
    *,
    used_roles: frozenset[ArbitrationRole],
) -> bool:
    warnings = _normalization_warnings(arbitration)
    return (
        _roles_are_usable(cases)
        and not any(_warning_is_case_collection_structural(item) for item in warnings)
        and not any(
            _warning_is_role_structural(item, used_roles=used_roles)
            for item in warnings
        )
    )


def _period_year_facts(years: list[int]) -> list[SignalFact]:
    return [
        _fact(
            "period_start_year",
            "derived.arbitration.period.start_year",
            years[0] if years else None,
        ),
        _fact(
            "period_end_year",
            "derived.arbitration.period.end_year",
            years[-1] if years else None,
        ),
    ]


def _prepare_high_respondent(
    report: CompanyReport,
    confidence: SignalConfidence,
) -> _PreparedRule:
    (
        arbitration,
        cases,
        years,
        case_ids,
        period_available,
        case_ids_available,
    ) = _full_dataset_context(report)
    respondent_count = sum(
        _case_has_role(case, ArbitrationRole.RESPONDENT) for case in cases
    )
    summary_count = (
        arbitration.role_summary.respondent_count
        if arbitration is not None
        else None
    )
    structural_inputs_usable = _role_structural_inputs_usable(
        arbitration,
        cases,
        used_roles=frozenset({ArbitrationRole.RESPONDENT}),
    )
    summary_consistent = summary_count == respondent_count
    facts = [
        *_common_facts(
            report,
            confidence,
            structural_inputs_usable=structural_inputs_usable,
            summary_consistent=summary_consistent,
            period_available=period_available,
            case_ids_available=case_ids_available,
        ),
        _fact(
            "case_count",
            "derived.arbitration.cases.count",
            len(cases),
        ),
        _fact(
            "respondent_case_count",
            "derived.arbitration.cases.respondent_count",
            respondent_count,
        ),
        _fact(
            "summary_respondent_count",
            "arbitration.role_summary.respondent_count",
            summary_count,
        ),
        *_period_year_facts(years),
    ]
    period, period_basis = _period_from_years(years)
    return _PreparedRule(
        facts=facts,
        eligibility=_common_eligibility(),
        trigger=_count_at_least("respondent_case_count", 10),
        years=years,
        case_ids=case_ids,
        period=period,
        period_basis=period_basis,
    )


def _prepare_growth(
    report: CompanyReport,
    confidence: SignalConfidence,
) -> _PreparedRule:
    arbitration = report.arbitration
    cases = list(arbitration.cases) if arbitration is not None else []
    respondent_cases = [
        case
        for case in cases
        if _case_has_role(case, ArbitrationRole.RESPONDENT)
    ]
    known_years = sorted(
        {case.year for case in respondent_cases if case.year is not None}
    )
    selected_years = known_years[-2:]
    years_known = all(case.year is not None for case in respondent_cases)
    two_years_available = len(selected_years) == 2
    years_consecutive = (
        two_years_available and selected_years[1] == selected_years[0] + 1
    )
    period_available = years_known and two_years_available and years_consecutive
    selected_cases = [
        case for case in respondent_cases if case.year in selected_years
    ]
    basis_cases = selected_cases if years_known else respondent_cases
    case_ids, case_ids_available = _case_identifiers(basis_cases)
    previous_year = selected_years[0] if two_years_available else None
    later_year = selected_years[1] if two_years_available else None
    previous_count = (
        sum(case.year == previous_year for case in selected_cases)
        if previous_year is not None
        else 0
    )
    later_count = (
        sum(case.year == later_year for case in selected_cases)
        if later_year is not None
        else 0
    )
    delta = later_count - previous_count
    summary_count = (
        arbitration.role_summary.respondent_count
        if arbitration is not None
        else None
    )
    structural_inputs_usable = _role_structural_inputs_usable(
        arbitration,
        cases,
        used_roles=frozenset({ArbitrationRole.RESPONDENT}),
    )
    summary_consistent = summary_count == len(respondent_cases)
    facts = [
        *_common_facts(
            report,
            confidence,
            structural_inputs_usable=structural_inputs_usable,
            summary_consistent=summary_consistent,
            period_available=period_available,
            case_ids_available=case_ids_available,
        ),
        _fact(
            "respondent_case_count",
            "derived.arbitration.cases.respondent_count",
            len(respondent_cases),
        ),
        _fact(
            "summary_respondent_count",
            "arbitration.role_summary.respondent_count",
            summary_count,
        ),
        _fact(
            "respondent_years_known",
            "derived.arbitration.respondent_years_known",
            years_known,
        ),
        _fact(
            "comparison_years_available",
            "derived.arbitration.growth.comparison_years_available",
            two_years_available,
        ),
        _fact(
            "comparison_years_consecutive",
            "derived.arbitration.growth.comparison_years_consecutive",
            years_consecutive,
        ),
        _fact(
            "previous_year",
            "derived.arbitration.growth.previous_year",
            previous_year,
        ),
        _fact(
            "later_year",
            "derived.arbitration.growth.later_year",
            later_year,
        ),
        _fact(
            "previous_respondent_count",
            "derived.arbitration.growth.previous_respondent_count",
            previous_count,
        ),
        _fact(
            "later_respondent_count",
            "derived.arbitration.growth.later_respondent_count",
            later_count,
        ),
        _fact(
            "respondent_count_delta",
            "derived.arbitration.growth.respondent_count_delta",
            delta,
        ),
    ]
    period = (
        YearRangePeriod(
            start_year=selected_years[0],
            end_year=selected_years[1],
        )
        if period_available
        else None
    )
    period_basis = (
        SignalPeriodBasis(
            fact_ids=["previous_year", "later_year"],
            operation=SignalPeriodOperation.YEAR_RANGE,
        )
        if period_available
        else None
    )
    trigger = AllOfExpression(
        children=[
            _greater_than_fact(
                "later_respondent_count",
                "previous_respondent_count",
            ),
            _count_at_least("respondent_count_delta", 3),
        ]
    )
    return _PreparedRule(
        facts=facts,
        eligibility=_common_eligibility(),
        trigger=trigger,
        years=selected_years,
        case_ids=case_ids,
        period=period,
        period_basis=period_basis,
    )


def _prepare_open_cases(
    report: CompanyReport,
    confidence: SignalConfidence,
) -> _PreparedRule:
    arbitration = report.arbitration
    cases = list(arbitration.cases) if arbitration is not None else []
    open_cases = [
        case
        for case in cases
        if case.normalized_status is ArbitrationStatus.OPEN
    ]
    years = sorted({case.year for case in open_cases if case.year is not None})
    period_available = all(case.year is not None for case in open_cases)
    case_ids, case_ids_available = _case_identifiers(open_cases)
    open_count = len(open_cases)
    summary_count = (
        arbitration.status_summary.open_count
        if arbitration is not None
        else None
    )
    warnings = _normalization_warnings(arbitration)
    structural_inputs_usable = (
        _statuses_are_usable(cases)
        and not any(_warning_is_case_collection_structural(item) for item in warnings)
        and not any(_warning_is_status_structural(item) for item in warnings)
    )
    summary_consistent = summary_count == open_count
    unknown_status_count = sum(
        case.normalized_status is ArbitrationStatus.UNKNOWN for case in cases
    )
    facts = [
        *_common_facts(
            report,
            confidence,
            structural_inputs_usable=structural_inputs_usable,
            summary_consistent=summary_consistent,
            period_available=period_available,
            case_ids_available=case_ids_available,
        ),
        _fact(
            "case_count",
            "derived.arbitration.cases.count",
            len(cases),
        ),
        _fact(
            "open_case_count",
            "derived.arbitration.cases.open_count",
            open_count,
        ),
        _fact(
            "unknown_status_case_count",
            "derived.arbitration.cases.unknown_status_count",
            unknown_status_count,
        ),
        _fact(
            "summary_open_count",
            "arbitration.status_summary.open_count",
            summary_count,
        ),
        *_period_year_facts(years),
    ]
    period, period_basis = _period_from_years(years)
    return _PreparedRule(
        facts=facts,
        eligibility=_common_eligibility(),
        trigger=_count_at_least("open_case_count", 1),
        years=years,
        case_ids=case_ids,
        period=period,
        period_basis=period_basis,
    )


def _prepare_frequent_plaintiff(
    report: CompanyReport,
    confidence: SignalConfidence,
) -> _PreparedRule:
    (
        arbitration,
        cases,
        years,
        case_ids,
        period_available,
        case_ids_available,
    ) = _full_dataset_context(report)
    plaintiff_count = sum(
        _case_has_role(case, ArbitrationRole.PLAINTIFF) for case in cases
    )
    respondent_count = sum(
        _case_has_role(case, ArbitrationRole.RESPONDENT) for case in cases
    )
    summary_plaintiff_count = (
        arbitration.role_summary.plaintiff_count
        if arbitration is not None
        else None
    )
    summary_respondent_count = (
        arbitration.role_summary.respondent_count
        if arbitration is not None
        else None
    )
    structural_inputs_usable = _role_structural_inputs_usable(
        arbitration,
        cases,
        used_roles=frozenset(
            {ArbitrationRole.PLAINTIFF, ArbitrationRole.RESPONDENT}
        ),
    )
    summary_consistent = (
        summary_plaintiff_count == plaintiff_count
        and summary_respondent_count == respondent_count
    )
    facts = [
        *_common_facts(
            report,
            confidence,
            structural_inputs_usable=structural_inputs_usable,
            summary_consistent=summary_consistent,
            period_available=period_available,
            case_ids_available=case_ids_available,
        ),
        _fact(
            "case_count",
            "derived.arbitration.cases.count",
            len(cases),
        ),
        _fact(
            "plaintiff_case_count",
            "derived.arbitration.cases.plaintiff_count",
            plaintiff_count,
        ),
        _fact(
            "respondent_case_count",
            "derived.arbitration.cases.respondent_count",
            respondent_count,
        ),
        _fact(
            "summary_plaintiff_count",
            "arbitration.role_summary.plaintiff_count",
            summary_plaintiff_count,
        ),
        _fact(
            "summary_respondent_count",
            "arbitration.role_summary.respondent_count",
            summary_respondent_count,
        ),
        *_period_year_facts(years),
    ]
    period, period_basis = _period_from_years(years)
    trigger = AllOfExpression(
        children=[
            _count_at_least("plaintiff_case_count", 10),
            _greater_than_fact(
                "plaintiff_case_count",
                "respondent_case_count",
            ),
        ]
    )
    return _PreparedRule(
        facts=facts,
        eligibility=_common_eligibility(),
        trigger=trigger,
        years=years,
        case_ids=case_ids,
        period=period,
        period_basis=period_basis,
    )


_RULES = (
    _Rule(
        code="arbitration.high_respondent_case_count",
        direction=SignalDirection.NEGATIVE,
        strength=SignalStrength.HIGH,
        prepare=_prepare_high_respondent,
    ),
    _Rule(
        code="arbitration.respondent_case_growth",
        direction=SignalDirection.NEGATIVE,
        strength=SignalStrength.MEDIUM,
        prepare=_prepare_growth,
    ),
    _Rule(
        code="arbitration.open_cases",
        direction=SignalDirection.NEGATIVE,
        strength=SignalStrength.MEDIUM,
        prepare=_prepare_open_cases,
    ),
    _Rule(
        code="arbitration.frequent_plaintiff",
        direction=SignalDirection.POSITIVE,
        strength=SignalStrength.MEDIUM,
        prepare=_prepare_frequent_plaintiff,
    ),
)


_WARNING_MESSAGES = {
    "dataset_unavailable": "Arbitration dataset is unavailable for signal evaluation.",
    "required_fact_missing": "A required normalized arbitration fact is unavailable.",
    "arbitration_incomplete": "Arbitration completeness gate failed.",
    "arbitration_period_unavailable": "The required arbitration period cannot be constructed.",
    "arbitration_summary_conflict": "Arbitration cases conflict with the normalized summary.",
    "normalization_warning_present": "Arbitration normalization warnings reduce signal confidence.",
    "signal_confidence_insufficient": "Arbitration signal confidence is insufficient.",
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
            case_ids=prepared.case_ids,
        ),
    )


def _suppression_code(prepared: _PreparedRule) -> str:
    values = {fact.id: fact.exact_value for fact in prepared.facts}
    if values["dataset_status"] != _AVAILABLE:
        return "dataset_unavailable"
    if not values["arbitration_facts_present"]:
        return "required_fact_missing"
    if values["arbitration_is_complete"] is not True:
        return "arbitration_incomplete"
    if values["structural_inputs_usable"] is not True:
        return "required_fact_missing"
    if values["summary_consistent"] is not True:
        return "arbitration_summary_conflict"
    if values["period_available"] is not True:
        return "arbitration_period_unavailable"
    if values["case_ids_available"] is not True:
        return "required_fact_missing"
    return "signal_confidence_insufficient"


def _evaluate_rule(
    report: CompanyReport,
    rule: _Rule,
    confidence: SignalConfidence,
) -> tuple[Signal | None, SignalWarning | None]:
    prepared = rule.prepare(report, confidence)
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
        raise AssertionError("eligible triggered arbitration rule requires a period")
    arbitration = report.arbitration
    if arbitration is None:
        raise AssertionError("eligible arbitration rule requires normalized facts")
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
            category=SignalCategory.ARBITRATION,
            direction=rule.direction,
            strength=rule.strength,
            factual_basis=SignalFactualBasis(
                facts=prepared.facts,
                eligibility=prepared.eligibility,
                trigger=prepared.trigger,
                strength_decision=SignalStrengthDecision(
                    default_strength=rule.strength,
                    overrides=[],
                ),
                period_basis=prepared.period_basis,
                years=prepared.years,
                case_ids=prepared.case_ids,
            ),
            source=[arbitration.source],
            period=prepared.period,
            confidence=confidence,
            warnings=signal_warnings,
        ),
        None,
    )


def _evaluate_arbitration_signals(report: CompanyReport) -> SignalEvaluationResult:
    """Evaluate Stage 2 arbitration rules without composing other categories."""

    confidence = _confidence_for(report.arbitration)
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
