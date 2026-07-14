import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from company_report_signal_test_helpers import sample_signal, signal_source
from product_api.company_reports.signals import (
    AllOfExpression,
    AnyOfExpression,
    ComparisonComparator,
    CountOperator,
    DateRangePeriod,
    DecimalComparisonOperator,
    DecimalRatioOperator,
    EqualityOperator,
    ExpressionNode,
    FactOperand,
    LiteralOperand,
    NoPeriod,
    NotExpression,
    PredicateExpression,
    PresenceOperator,
    Signal,
    SignalCategory,
    SignalEvaluationBasis,
    SignalEvaluationResult,
    SignalFact,
    SignalFactualBasis,
    SignalPeriodBasis,
    SignalPeriodOperation,
    SignalStrength,
    SignalStrengthDecision,
    SignalWarning,
    YearRangePeriod,
    canonical_representation,
    evaluate_expression,
)


def _predicate(fact_id: str) -> PredicateExpression:
    return PredicateExpression(fact_id=fact_id, operator=PresenceOperator())


def test_signal_models_are_frozen_extra_forbid_and_enums_are_closed():
    fact = SignalFact(id="value", normalized_path="counterparty.value", exact_value=1)

    with pytest.raises(ValidationError):
        fact.exact_value = 2
    with pytest.raises(ValidationError):
        SignalFact(
            id="value",
            normalized_path="counterparty.value",
            exact_value=1,
            extra_field=True,
        )
    with pytest.raises(ValueError):
        SignalCategory("unknown")
    with pytest.raises(ValidationError):
        Signal.model_validate(
            {**sample_signal().model_dump(mode="python"), "direction": "unknown"}
        )


def test_signal_source_and_unique_codes_are_validated():
    with pytest.raises(ValidationError):
        sample_signal(source=[])

    duplicate = sample_signal()
    with pytest.raises(ValidationError):
        SignalEvaluationResult(signals=[duplicate, duplicate])


def test_signal_fact_ids_and_expression_references_are_validated():
    fact = SignalFact(id="known", normalized_path="counterparty.known", exact_value=1)
    eligibility = _predicate("known")

    with pytest.raises(ValidationError):
        SignalFactualBasis(
            facts=[fact, fact],
            eligibility=eligibility,
            trigger=eligibility,
            strength_decision=SignalStrengthDecision(
                default_strength=SignalStrength.LOW
            ),
            period_basis=SignalPeriodBasis(
                fact_ids=["known"], operation=SignalPeriodOperation.YEAR
            ),
        )


def test_failed_eligibility_and_warning_registry_are_strict():
    fact = SignalFact(id="missing", normalized_path="counterparty.missing", exact_value=None)
    eligibility = _predicate("missing")

    with pytest.raises(ValidationError):
        SignalEvaluationBasis(
            facts=[fact],
            eligibility=eligibility,
            failed_eligibility=[],
        )
    basis = SignalEvaluationBasis(
        facts=[fact],
        eligibility=eligibility,
        failed_eligibility=[eligibility],
    )
    with pytest.raises(ValidationError):
        SignalWarning(
            code="dataset_unavailable",
            rule_code="counterparty.sample",
            dataset="unregistered",
            message="Safe message.",
            evaluation_basis=basis,
        )
    with pytest.raises(ValidationError):
        SignalWarning(
            code="unknown_warning",
            rule_code="counterparty.sample",
            dataset="counterparty",
            message="Safe message.",
            evaluation_basis=basis,
        )
    for invalid_rule_code in (None, ""):
        with pytest.raises(ValidationError):
            SignalWarning(
                code="dataset_unavailable",
                rule_code=invalid_rule_code,
                dataset="counterparty",
                message="Safe message.",
                evaluation_basis=basis,
            )
    with pytest.raises(ValidationError):
        SignalWarning(
            code="dataset_unavailable",
            rule_code="finance.sample",
            dataset="counterparty",
            message="Safe message.",
            evaluation_basis=basis,
        )
    warning = SignalWarning(
        code="dataset_unavailable",
        rule_code="counterparty.sample",
        dataset="counterparty",
        message="Safe message.",
        evaluation_basis=basis,
    )
    assert warning.rule_code == "counterparty.sample"
    with pytest.raises(ValidationError):
        SignalFactualBasis(
            facts=[fact],
            eligibility=_predicate("missing"),
            trigger=eligibility,
            strength_decision=SignalStrengthDecision(
                default_strength=SignalStrength.LOW
            ),
            period_basis=SignalPeriodBasis(
                fact_ids=["known"], operation=SignalPeriodOperation.YEAR
            ),
        )


def test_period_models_validate_ranges_and_required_fields():
    assert NoPeriod(as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)).kind == "no_period"
    with pytest.raises(ValidationError):
        DateRangePeriod(start=date(2026, 2, 1), end=date(2026, 1, 1))
    with pytest.raises(ValidationError):
        YearRangePeriod(start_year=2026, end_year=2025)
    with pytest.raises(ValidationError):
        NoPeriod(as_of=None)


def test_expression_shape_empty_nodes_not_contract_and_cycles_are_rejected():
    with pytest.raises(ValidationError):
        AllOfExpression(children=[])
    with pytest.raises(ValidationError):
        AnyOfExpression(children=[])
    with pytest.raises(ValidationError):
        NotExpression.model_validate({"kind": "not", "children": [_predicate("x")]})

    cyclic: dict[str, object] = {"kind": "not"}
    cyclic["child"] = cyclic
    with pytest.raises(ValidationError):
        TypeAdapter(ExpressionNode).validate_python(cyclic)


def test_expression_children_are_sorted_and_and_or_not_are_evaluated():
    first = _predicate("a")
    second = _predicate("b")
    left = AllOfExpression(children=[second, first])
    right = AllOfExpression(children=[first, second])
    facts = [
        SignalFact(id="a", normalized_path="a", exact_value=1),
        SignalFact(id="b", normalized_path="b", exact_value=None),
    ]

    assert left.model_dump(mode="json") == right.model_dump(mode="json")
    assert evaluate_expression(left, facts) is False
    assert evaluate_expression(AnyOfExpression(children=[first, second]), facts) is True
    assert evaluate_expression(NotExpression(child=second), facts) is True


def test_count_decimal_comparison_and_decimal_ratio_are_exact():
    facts = [
        SignalFact(id="count", normalized_path="count", exact_value=10),
        SignalFact(id="numerator", normalized_path="numerator", exact_value=Decimal("1")),
        SignalFact(id="denominator", normalized_path="denominator", exact_value=Decimal("4")),
        SignalFact(id="threshold", normalized_path="threshold", exact_value=Decimal("0.25")),
    ]
    count = PredicateExpression(
        fact_id="count",
        operator=CountOperator(
            comparator=ComparisonComparator.GREATER_OR_EQUAL,
            value=10,
        ),
    )
    comparison = PredicateExpression(
        fact_id="numerator",
        operator=DecimalComparisonOperator(
            comparator=ComparisonComparator.LESS_OR_EQUAL,
            operand=FactOperand(fact_id="denominator"),
        ),
    )
    ratio = PredicateExpression(
        fact_id="numerator",
        operator=DecimalRatioOperator(
            denominator_fact_id="denominator",
            comparator=ComparisonComparator.EQUALITY,
            value=Decimal("0.25"),
        ),
    )

    assert evaluate_expression(count, facts) is True
    assert evaluate_expression(comparison, facts) is True
    assert evaluate_expression(ratio, facts) is True

    zero_denominator = [
        *facts[:2],
        SignalFact(id="denominator", normalized_path="denominator", exact_value=Decimal("0")),
    ]
    assert evaluate_expression(ratio, zero_denominator) is False


def test_decimal_canonical_serialization_preserves_precision_without_float():
    value = Decimal("0.123456789012345678901234567890")
    fact = SignalFact(id="decimal", normalized_path="finance.decimal", exact_value=value)
    dumped = fact.model_dump(mode="json")
    canonical = canonical_representation(fact)

    assert fact.exact_value == value
    assert dumped["exact_value"] == str(value)
    assert str(value) in canonical
    assert json.loads(canonical)["exact_value"] == str(value)
    with pytest.raises(ValidationError):
        SignalFact(id="float", normalized_path="float", exact_value=0.1)


def test_canonical_ordering_is_identical_for_equivalent_permutations():
    first_source = signal_source()
    second_source = first_source.model_copy(
        update={
            "dataset": "finance",
            "endpoint": "/v1/finance",
            "response_hash": "b" * 64,
        }
    )
    left = sample_signal(source=[second_source, first_source])
    right = sample_signal(source=[first_source, second_source])
    arbitration = sample_signal(
        code="arbitration.sample",
        category=SignalCategory.ARBITRATION,
    )

    left_result = SignalEvaluationResult(signals=[arbitration, left])
    right_result = SignalEvaluationResult(signals=[right, arbitration])
    assert left_result.model_dump(mode="json") == right_result.model_dump(mode="json")
    assert canonical_representation(left_result) == canonical_representation(right_result)


def test_serialized_models_cannot_contain_raw_payload():
    serialized = canonical_representation(SignalEvaluationResult(signals=[sample_signal()]))

    assert "raw_payload" not in serialized
    with pytest.raises(ValidationError):
        SignalFact.model_validate(
            {
                "id": "unsafe",
                "normalized_path": "unsafe",
                "exact_value": 1,
                "raw_payload": {"secret": True},
            }
        )
