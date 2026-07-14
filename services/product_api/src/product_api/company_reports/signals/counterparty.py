from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from product_api.company_reports.aggregate import (
    CompanyReport,
    DatasetReportStatus,
)
from product_api.company_reports.models import CounterpartyFacts

from .models import (
    AbsenceOperator,
    AllOfExpression,
    AnyOfExpression,
    ComparisonComparator,
    DatePeriod,
    DateRangePeriod,
    EqualityOperator,
    ExpressionNode,
    GreaterOrEqualOperator,
    InequalityOperator,
    LessOrEqualOperator,
    LiteralOperand,
    NoPeriod,
    NotExpression,
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
    SignalPeriod,
    SignalPeriodBasis,
    SignalPeriodOperation,
    SignalStrength,
    SignalStrengthDecision,
    SignalWarning,
    evaluate_expression,
    failed_expression_nodes,
    referenced_fact_ids,
)


_DATASET = "counterparty"
_AVAILABLE = DatasetReportStatus.AVAILABLE.value


@dataclass(frozen=True)
class _Rule:
    code: str
    direction: SignalDirection
    strength: SignalStrength
    build_expressions: Callable[
        [list[SignalFact]],
        tuple[ExpressionNode, ExpressionNode],
    ]
    build_period: Callable[[dict[str, SignalFact]], SignalPeriod]
    period_basis: SignalPeriodBasis


def _fact(fact_id: str, normalized_path: str, value: object) -> SignalFact:
    return SignalFact(
        id=fact_id,
        normalized_path=normalized_path,
        exact_value=value,
    )


def _presence(fact_id: str) -> PredicateExpression:
    return PredicateExpression(fact_id=fact_id, operator=PresenceOperator())


def _absence(fact_id: str) -> PredicateExpression:
    return PredicateExpression(fact_id=fact_id, operator=AbsenceOperator())


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


def _greater_or_equal(fact_id: str, value: object) -> PredicateExpression:
    return PredicateExpression(
        fact_id=fact_id,
        operator=GreaterOrEqualOperator(operand=LiteralOperand(value=value)),
    )


def _less_or_equal_fact(fact_id: str, other_fact_id: str) -> PredicateExpression:
    from .models import FactOperand

    return PredicateExpression(
        fact_id=fact_id,
        operator=LessOrEqualOperator(operand=FactOperand(fact_id=other_fact_id)),
    )


def _common_eligibility(*children: ExpressionNode) -> AllOfExpression:
    return AllOfExpression(
        children=[
            _equal("dataset_status", _AVAILABLE),
            _equal("counterparty_facts_present", True),
            *children,
            _not_equal("signal_confidence", SignalConfidence.LOW.value),
        ]
    )


def _status_conflict_expression() -> AllOfExpression:
    return AllOfExpression(
        children=[
            _equal("is_active", True),
            _presence("dissolved_date"),
        ]
    )


def _active_expressions(
    _facts: list[SignalFact],
) -> tuple[ExpressionNode, ExpressionNode]:
    eligibility = _common_eligibility(
        _presence("is_active"),
        AnyOfExpression(
            children=[
                _equal("is_active", False),
                _equal("dissolved_date_usable", True),
            ]
        ),
        _presence("source_received_at"),
        NotExpression(child=_status_conflict_expression()),
    )
    trigger = AllOfExpression(
        children=[_equal("is_active", True), _absence("dissolved_date")]
    )
    return eligibility, trigger


def _dissolved_expressions(
    _facts: list[SignalFact],
) -> tuple[ExpressionNode, ExpressionNode]:
    eligibility = _common_eligibility(
        AnyOfExpression(
            children=[
                _equal("is_active", False),
                _presence("dissolved_date"),
                AllOfExpression(
                    children=[
                        _equal("is_active", True),
                        _equal("dissolved_date_usable", True),
                    ]
                ),
            ]
        ),
        _presence("source_received_at"),
        NotExpression(child=_status_conflict_expression()),
    )
    trigger = AnyOfExpression(
        children=[_equal("is_active", False), _presence("dissolved_date")]
    )
    return eligibility, trigger


def _status_conflict_expressions(
    _facts: list[SignalFact],
) -> tuple[ExpressionNode, ExpressionNode]:
    eligibility = _common_eligibility(
        _presence("is_active"),
        AnyOfExpression(
            children=[
                _equal("is_active", False),
                _equal("dissolved_date_usable", True),
            ]
        ),
        _presence("source_received_at"),
    )
    return eligibility, _status_conflict_expression()


def _long_history_expressions(
    _facts: list[SignalFact],
) -> tuple[ExpressionNode, ExpressionNode]:
    eligibility = _common_eligibility(
        _presence("years_from_registration"),
        _presence("registration_date"),
        _presence("source_received_at"),
        _presence("source_received_date"),
        _less_or_equal_fact("registration_date", "source_received_date"),
    )
    return eligibility, _greater_or_equal("years_from_registration", 5)


def _no_period(facts: dict[str, SignalFact]) -> NoPeriod:
    value = facts["source_received_at"].exact_value
    if not isinstance(value, datetime):
        raise ValueError("source received_at is required for no_period")
    return NoPeriod(as_of=value)


def _dissolved_period(facts: dict[str, SignalFact]) -> SignalPeriod:
    dissolved_date = facts["dissolved_date"].exact_value
    if isinstance(dissolved_date, date):
        return DatePeriod(value=dissolved_date)
    return _no_period(facts)


def _long_history_period(facts: dict[str, SignalFact]) -> DateRangePeriod:
    start = facts["registration_date"].exact_value
    received_at = facts["source_received_at"].exact_value
    if not isinstance(start, date) or not isinstance(received_at, datetime):
        raise ValueError("registration and source dates are required for date_range")
    return DateRangePeriod(start=start, end=received_at.date())


_RULES = (
    _Rule(
        code="counterparty.active",
        direction=SignalDirection.POSITIVE,
        strength=SignalStrength.MEDIUM,
        build_expressions=_active_expressions,
        build_period=_no_period,
        period_basis=SignalPeriodBasis(
            fact_ids=["source_received_at"],
            operation=SignalPeriodOperation.NO_PERIOD,
        ),
    ),
    _Rule(
        code="counterparty.dissolved",
        direction=SignalDirection.NEGATIVE,
        strength=SignalStrength.CRITICAL,
        build_expressions=_dissolved_expressions,
        build_period=_dissolved_period,
        period_basis=SignalPeriodBasis(
            fact_ids=["dissolved_date", "source_received_at"],
            operation=SignalPeriodOperation.DATE,
        ),
    ),
    _Rule(
        code="counterparty.long_operating_history",
        direction=SignalDirection.POSITIVE,
        strength=SignalStrength.LOW,
        build_expressions=_long_history_expressions,
        build_period=_long_history_period,
        period_basis=SignalPeriodBasis(
            fact_ids=["registration_date", "source_received_at"],
            operation=SignalPeriodOperation.DATE_RANGE,
        ),
    ),
    _Rule(
        code="counterparty.status_conflict",
        direction=SignalDirection.INFORMATIONAL,
        strength=SignalStrength.HIGH,
        build_expressions=_status_conflict_expressions,
        build_period=_no_period,
        period_basis=SignalPeriodBasis(
            fact_ids=["source_received_at"],
            operation=SignalPeriodOperation.NO_PERIOD,
        ),
    ),
)


def _normalization_warnings(facts: CounterpartyFacts | None) -> bool:
    if facts is None:
        return False
    return bool(facts.warnings or facts.source.warnings)


def _confidence_for(facts: CounterpartyFacts | None) -> SignalConfidence:
    return (
        SignalConfidence.MEDIUM
        if _normalization_warnings(facts)
        else SignalConfidence.HIGH
    )


def _dissolved_date_usable(facts: CounterpartyFacts | None) -> bool:
    if facts is None:
        return False
    if facts.dissolved_date is not None:
        return True
    return not any(
        warning.code == "date_parse_failed" and "dissolved_date" in warning.path
        for warning in [*facts.warnings, *facts.source.warnings]
    )


def _facts_for(
    report: CompanyReport,
    confidence: SignalConfidence,
    rule: _Rule,
) -> list[SignalFact]:
    counterparty = report.counterparty
    dataset = report.datasets.get(_DATASET)
    source = counterparty.source if counterparty is not None else None
    received_at = source.received_at if source is not None else None
    all_facts = [
        _fact(
            "dataset_status",
            "datasets.counterparty.status",
            dataset.status.value if dataset is not None else None,
        ),
        _fact(
            "counterparty_facts_present",
            "counterparty",
            counterparty is not None,
        ),
        _fact(
            "is_active",
            "counterparty.is_active",
            counterparty.is_active if counterparty is not None else None,
        ),
        _fact(
            "dissolved_date",
            "counterparty.dissolved_date",
            counterparty.dissolved_date if counterparty is not None else None,
        ),
        _fact(
            "dissolved_date_usable",
            "derived.counterparty.dissolved_date_usable",
            _dissolved_date_usable(counterparty),
        ),
        _fact(
            "registration_date",
            "counterparty.registration_date",
            counterparty.registration_date if counterparty is not None else None,
        ),
        _fact(
            "years_from_registration",
            "counterparty.years_from_registration",
            counterparty.years_from_registration if counterparty is not None else None,
        ),
        _fact(
            "source_received_at",
            "counterparty.source.received_at",
            received_at,
        ),
        _fact(
            "source_received_date",
            "derived.counterparty.source.received_at.date",
            received_at.date() if received_at is not None else None,
        ),
        _fact(
            "signal_confidence",
            "derived.signals.confidence",
            confidence.value,
        ),
    ]
    common_ids = {
        "dataset_status",
        "counterparty_facts_present",
        "source_received_at",
        "signal_confidence",
    }
    if rule.code == "counterparty.long_operating_history":
        selected = common_ids | {
            "registration_date",
            "years_from_registration",
            "source_received_date",
        }
    else:
        selected = common_ids | {
            "is_active",
            "dissolved_date",
            "dissolved_date_usable",
        }
    return [fact for fact in all_facts if fact.id in selected]


def _evaluation_basis(
    facts: list[SignalFact],
    eligibility: ExpressionNode,
) -> SignalEvaluationBasis:
    return SignalEvaluationBasis(
        facts=facts,
        eligibility=eligibility,
        failed_eligibility=failed_expression_nodes(eligibility, facts),
        years=[],
        case_ids=[],
    )


_WARNING_MESSAGES = {
    "dataset_unavailable": "Counterparty dataset is unavailable for signal evaluation.",
    "required_fact_missing": "A required normalized counterparty fact is unavailable.",
    "required_period_unavailable": "The required counterparty period cannot be constructed.",
    "normalization_warning_present": "Counterparty normalization warnings reduce signal confidence.",
    "status_conflict": "Counterparty status facts conflict under ruleset v1.",
    "signal_confidence_insufficient": "Counterparty signal confidence is insufficient.",
}


def _warning(
    code: str,
    rule: _Rule,
    facts: list[SignalFact],
    eligibility: ExpressionNode,
    *,
    failed_eligibility: list[ExpressionNode] | None = None,
) -> SignalWarning:
    basis = _evaluation_basis(facts, eligibility)
    if failed_eligibility is not None:
        basis = SignalEvaluationBasis(
            facts=basis.facts,
            eligibility=basis.eligibility,
            failed_eligibility=failed_eligibility,
            years=basis.years,
            case_ids=basis.case_ids,
        )
    return SignalWarning(
        code=code,
        rule_code=rule.code,
        dataset=_DATASET,
        message=_WARNING_MESSAGES[code],
        evaluation_basis=basis,
    )


def _normalization_signal_warning(
    rule: _Rule,
    facts: list[SignalFact],
    eligibility: ExpressionNode,
) -> SignalWarning:
    return _warning(
        "normalization_warning_present",
        rule,
        facts,
        eligibility,
        failed_eligibility=[],
    )


def _contains_failed_fact(
    failed: list[ExpressionNode],
    fact_id: str,
) -> bool:
    return any(fact_id in referenced_fact_ids(node) for node in failed)


def _suppression_code(
    rule: _Rule,
    facts_by_id: dict[str, SignalFact],
    failed: list[ExpressionNode],
) -> str:
    if facts_by_id["dataset_status"].exact_value != _AVAILABLE:
        return "dataset_unavailable"
    if not facts_by_id["counterparty_facts_present"].exact_value:
        return "required_fact_missing"
    if _contains_failed_fact(failed, "signal_confidence"):
        return "signal_confidence_insufficient"
    if rule.code in {"counterparty.active", "counterparty.dissolved"} and (
        facts_by_id["is_active"].exact_value is True
        and facts_by_id["dissolved_date"].exact_value is not None
    ):
        return "status_conflict"
    if (
        facts_by_id["source_received_at"].exact_value is None
        or rule.code == "counterparty.long_operating_history"
        and facts_by_id["registration_date"].exact_value is not None
        and facts_by_id["source_received_date"].exact_value is not None
        and facts_by_id["registration_date"].exact_value
        > facts_by_id["source_received_date"].exact_value
    ):
        return "required_period_unavailable"
    return "required_fact_missing"


def _evaluate_rule(
    report: CompanyReport,
    rule: _Rule,
    confidence: SignalConfidence,
) -> tuple[Signal | None, SignalWarning | None]:
    facts = _facts_for(report, confidence, rule)
    facts_by_id = {fact.id: fact for fact in facts}
    eligibility, trigger = rule.build_expressions(facts)
    eligible = evaluate_expression(eligibility, facts_by_id)
    triggered = evaluate_expression(trigger, facts_by_id)

    if not eligible:
        failed = failed_expression_nodes(eligibility, facts_by_id)
        code = _suppression_code(rule, facts_by_id, failed)
        if code == "signal_confidence_insufficient" and not triggered:
            return None, None
        return None, _warning(code, rule, facts, eligibility)
    if not triggered:
        return None, None

    period = rule.build_period(facts_by_id)
    signal_warnings = (
        [_normalization_signal_warning(rule, facts, eligibility)]
        if confidence is SignalConfidence.MEDIUM
        else []
    )
    counterparty = report.counterparty
    if counterparty is None:
        raise AssertionError("eligible counterparty rule must have facts")
    period_basis = rule.period_basis
    if rule.code == "counterparty.dissolved":
        period_basis = (
            SignalPeriodBasis(
                fact_ids=["dissolved_date"],
                operation=SignalPeriodOperation.DATE,
            )
            if isinstance(period, DatePeriod)
            else SignalPeriodBasis(
                fact_ids=["source_received_at"],
                operation=SignalPeriodOperation.NO_PERIOD,
            )
        )
    return (
        Signal(
            code=rule.code,
            category=SignalCategory.LEGAL_STATUS,
            direction=rule.direction,
            strength=rule.strength,
            factual_basis=SignalFactualBasis(
                facts=facts,
                eligibility=eligibility,
                trigger=trigger,
                strength_decision=SignalStrengthDecision(
                    default_strength=rule.strength,
                    overrides=[],
                ),
                period_basis=period_basis,
                years=[],
                case_ids=[],
            ),
            source=[counterparty.source],
            period=period,
            confidence=confidence,
            warnings=signal_warnings,
        ),
        None,
    )


def _evaluate_counterparty_signals(report: CompanyReport) -> SignalEvaluationResult:
    """Evaluate Stage 1 legal-status rules without composing other categories."""

    confidence = _confidence_for(report.counterparty)
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
