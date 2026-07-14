from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, field_validator, model_validator

from product_api.company_reports.models import FrozenDomainModel, SourceMetadata

from .common import canonical_representation, stable_sorted, stable_unique_sorted


ExactValue: TypeAlias = None | bool | int | str | Decimal | date | datetime


class SignalCategory(StrEnum):
    LEGAL_STATUS = "legal_status"
    FINANCIAL = "financial"
    ARBITRATION = "arbitration"


class SignalDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    INFORMATIONAL = "informational"


class SignalStrength(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SignalConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ComparisonComparator(StrEnum):
    EQUALITY = "equality"
    INEQUALITY = "inequality"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"


class LiteralOperand(FrozenDomainModel):
    kind: Literal["literal"] = "literal"
    value: ExactValue

    @field_validator("value", mode="before")
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("exact values do not accept float")
        return value


class FactOperand(FrozenDomainModel):
    kind: Literal["fact"] = "fact"
    fact_id: str = Field(min_length=1)


ComparisonOperand = Annotated[
    LiteralOperand | FactOperand,
    Field(discriminator="kind"),
]


class PresenceOperator(FrozenDomainModel):
    kind: Literal["presence"] = "presence"


class AbsenceOperator(FrozenDomainModel):
    kind: Literal["absence"] = "absence"


class EqualityOperator(FrozenDomainModel):
    kind: Literal["equality"] = "equality"
    operand: ComparisonOperand


class InequalityOperator(FrozenDomainModel):
    kind: Literal["inequality"] = "inequality"
    operand: ComparisonOperand


class GreaterThanOperator(FrozenDomainModel):
    kind: Literal["greater_than"] = "greater_than"
    operand: ComparisonOperand


class GreaterOrEqualOperator(FrozenDomainModel):
    kind: Literal["greater_or_equal"] = "greater_or_equal"
    operand: ComparisonOperand


class LessThanOperator(FrozenDomainModel):
    kind: Literal["less_than"] = "less_than"
    operand: ComparisonOperand


class LessOrEqualOperator(FrozenDomainModel):
    kind: Literal["less_or_equal"] = "less_or_equal"
    operand: ComparisonOperand


class CountOperator(FrozenDomainModel):
    kind: Literal["count"] = "count"
    comparator: ComparisonComparator
    value: int


class DecimalComparisonOperator(FrozenDomainModel):
    kind: Literal["decimal_comparison"] = "decimal_comparison"
    comparator: ComparisonComparator
    operand: ComparisonOperand

    @model_validator(mode="after")
    def _validate_literal_operand(self) -> DecimalComparisonOperator:
        if isinstance(self.operand, LiteralOperand) and not isinstance(
            self.operand.value,
            Decimal,
        ):
            raise ValueError("decimal comparison literals must be Decimal")
        return self


class DecimalRatioOperator(FrozenDomainModel):
    kind: Literal["decimal_ratio"] = "decimal_ratio"
    denominator_fact_id: str = Field(min_length=1)
    comparator: ComparisonComparator
    value: Decimal

    @field_validator("value", mode="before")
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("decimal ratios do not accept float")
        return value


PredicateOperator = Annotated[
    PresenceOperator
    | AbsenceOperator
    | EqualityOperator
    | InequalityOperator
    | GreaterThanOperator
    | GreaterOrEqualOperator
    | LessThanOperator
    | LessOrEqualOperator
    | CountOperator
    | DecimalComparisonOperator
    | DecimalRatioOperator,
    Field(discriminator="kind"),
]


class PredicateExpression(FrozenDomainModel):
    kind: Literal["predicate"] = "predicate"
    fact_id: str = Field(min_length=1)
    operator: PredicateOperator


class AllOfExpression(FrozenDomainModel):
    kind: Literal["all_of"] = "all_of"
    children: list["ExpressionNode"] = Field(min_length=1)

    @field_validator("children")
    @classmethod
    def _sort_children(cls, value: list[ExpressionNode]) -> list[ExpressionNode]:
        return stable_sorted(value)


class AnyOfExpression(FrozenDomainModel):
    kind: Literal["any_of"] = "any_of"
    children: list["ExpressionNode"] = Field(min_length=1)

    @field_validator("children")
    @classmethod
    def _sort_children(cls, value: list[ExpressionNode]) -> list[ExpressionNode]:
        return stable_sorted(value)


class NotExpression(FrozenDomainModel):
    kind: Literal["not"] = "not"
    child: "ExpressionNode"


ExpressionNode = Annotated[
    PredicateExpression | AllOfExpression | AnyOfExpression | NotExpression,
    Field(discriminator="kind"),
]


class NoPeriod(FrozenDomainModel):
    kind: Literal["no_period"] = "no_period"
    as_of: datetime


class DatePeriod(FrozenDomainModel):
    kind: Literal["date"] = "date"
    value: date


class DateRangePeriod(FrozenDomainModel):
    kind: Literal["date_range"] = "date_range"
    start: date
    end: date

    @model_validator(mode="after")
    def _validate_range(self) -> DateRangePeriod:
        if self.start > self.end:
            raise ValueError("date range start must not be after end")
        return self


class YearPeriod(FrozenDomainModel):
    kind: Literal["year"] = "year"
    year: int


class YearRangePeriod(FrozenDomainModel):
    kind: Literal["year_range"] = "year_range"
    start_year: int
    end_year: int

    @model_validator(mode="after")
    def _validate_range(self) -> YearRangePeriod:
        if self.start_year > self.end_year:
            raise ValueError("year range start must not be after end")
        return self


SignalPeriod = Annotated[
    NoPeriod | DatePeriod | DateRangePeriod | YearPeriod | YearRangePeriod,
    Field(discriminator="kind"),
]


class SignalFact(FrozenDomainModel):
    id: str = Field(min_length=1)
    normalized_path: str = Field(min_length=1)
    exact_value: ExactValue

    @field_validator("exact_value", mode="before")
    @classmethod
    def _reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("exact values do not accept float")
        return value


class SignalPeriodOperation(StrEnum):
    NO_PERIOD = "no_period"
    DATE = "date"
    DATE_RANGE = "date_range"
    YEAR = "year"
    YEAR_RANGE = "year_range"


class SignalPeriodBasis(FrozenDomainModel):
    fact_ids: list[str] = Field(min_length=1)
    operation: SignalPeriodOperation

    @field_validator("fact_ids")
    @classmethod
    def _normalize_fact_ids(cls, value: list[str]) -> list[str]:
        if any(not fact_id for fact_id in value):
            raise ValueError("period fact ids must not be empty")
        if len(value) != len(set(value)):
            raise ValueError("period fact ids must be unique")
        return sorted(value)


class SignalStrengthOverride(FrozenDomainModel):
    when: ExpressionNode
    strength: SignalStrength


class SignalStrengthDecision(FrozenDomainModel):
    default_strength: SignalStrength
    overrides: list[SignalStrengthOverride] = Field(default_factory=list)


def _normalize_facts(value: list[SignalFact]) -> list[SignalFact]:
    ids = [fact.id for fact in value]
    if len(ids) != len(set(ids)):
        raise ValueError("signal fact ids must be unique")
    return stable_sorted(
        value,
        primary_key=lambda fact: (fact.id, fact.normalized_path),
    )


def referenced_fact_ids(expression: ExpressionNode) -> set[str]:
    if isinstance(expression, PredicateExpression):
        referenced = {expression.fact_id}
        operator = expression.operator
        operand = getattr(operator, "operand", None)
        if isinstance(operand, FactOperand):
            referenced.add(operand.fact_id)
        if isinstance(operator, DecimalRatioOperator):
            referenced.add(operator.denominator_fact_id)
        return referenced
    if isinstance(expression, (AllOfExpression, AnyOfExpression)):
        return set().union(*(referenced_fact_ids(child) for child in expression.children))
    return referenced_fact_ids(expression.child)


def _compare(left: object, comparator: ComparisonComparator, right: object) -> bool:
    try:
        if comparator is ComparisonComparator.EQUALITY:
            return left == right
        if comparator is ComparisonComparator.INEQUALITY:
            return left != right
        if comparator is ComparisonComparator.GREATER_THAN:
            return left > right  # type: ignore[operator]
        if comparator is ComparisonComparator.GREATER_OR_EQUAL:
            return left >= right  # type: ignore[operator]
        if comparator is ComparisonComparator.LESS_THAN:
            return left < right  # type: ignore[operator]
        return left <= right  # type: ignore[operator]
    except TypeError:
        return False


def _operand_value(
    operand: ComparisonOperand,
    facts: dict[str, SignalFact],
) -> ExactValue:
    if isinstance(operand, LiteralOperand):
        return operand.value
    fact = facts.get(operand.fact_id)
    return fact.exact_value if fact is not None else None


def evaluate_expression(
    expression: ExpressionNode,
    facts: list[SignalFact] | dict[str, SignalFact],
) -> bool:
    facts_by_id = (
        facts
        if isinstance(facts, dict)
        else {fact.id: fact for fact in facts}
    )
    if isinstance(expression, AllOfExpression):
        return all(evaluate_expression(child, facts_by_id) for child in expression.children)
    if isinstance(expression, AnyOfExpression):
        return any(evaluate_expression(child, facts_by_id) for child in expression.children)
    if isinstance(expression, NotExpression):
        return not evaluate_expression(expression.child, facts_by_id)

    fact = facts_by_id.get(expression.fact_id)
    value = fact.exact_value if fact is not None else None
    operator = expression.operator
    if isinstance(operator, PresenceOperator):
        return value is not None
    if isinstance(operator, AbsenceOperator):
        return value is None
    if isinstance(operator, CountOperator):
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and _compare(value, operator.comparator, operator.value)
        )
    if isinstance(operator, DecimalComparisonOperator):
        operand = _operand_value(operator.operand, facts_by_id)
        return (
            isinstance(value, Decimal)
            and isinstance(operand, Decimal)
            and _compare(value, operator.comparator, operand)
        )
    if isinstance(operator, DecimalRatioOperator):
        denominator = facts_by_id.get(operator.denominator_fact_id)
        denominator_value = (
            denominator.exact_value if denominator is not None else None
        )
        return (
            isinstance(value, Decimal)
            and isinstance(denominator_value, Decimal)
            and denominator_value != 0
            and _compare(value / denominator_value, operator.comparator, operator.value)
        )

    operand = _operand_value(operator.operand, facts_by_id)
    comparator = ComparisonComparator(operator.kind)
    return _compare(value, comparator, operand)


def failed_expression_nodes(
    eligibility: ExpressionNode,
    facts: list[SignalFact] | dict[str, SignalFact],
) -> list[ExpressionNode]:
    candidates = (
        eligibility.children
        if isinstance(eligibility, AllOfExpression)
        else [eligibility]
    )
    return stable_unique_sorted(
        child for child in candidates if not evaluate_expression(child, facts)
    )


def _validate_expression_value_types(
    expression: ExpressionNode,
    facts: dict[str, SignalFact],
) -> None:
    if isinstance(expression, (AllOfExpression, AnyOfExpression)):
        for child in expression.children:
            _validate_expression_value_types(child, facts)
        return
    if isinstance(expression, NotExpression):
        _validate_expression_value_types(expression.child, facts)
        return
    value = facts[expression.fact_id].exact_value
    operator = expression.operator
    if isinstance(operator, CountOperator):
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool)
        ):
            raise ValueError("count predicates require an integer fact")
        return
    if isinstance(operator, DecimalComparisonOperator):
        if value is not None and not isinstance(value, Decimal):
            raise ValueError("decimal comparison requires a Decimal fact")
        if isinstance(operator.operand, FactOperand):
            operand = facts[operator.operand.fact_id].exact_value
            if operand is not None and not isinstance(operand, Decimal):
                raise ValueError("decimal comparison requires a Decimal operand fact")
        return
    if isinstance(operator, DecimalRatioOperator):
        denominator = facts[operator.denominator_fact_id].exact_value
        if value is not None and not isinstance(value, Decimal):
            raise ValueError("decimal ratio requires a Decimal numerator fact")
        if denominator is not None and not isinstance(denominator, Decimal):
            raise ValueError("decimal ratio requires a Decimal denominator fact")


class SignalEvaluationBasis(FrozenDomainModel):
    facts: list[SignalFact]
    eligibility: ExpressionNode
    failed_eligibility: list[ExpressionNode] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    case_ids: list[str] = Field(default_factory=list)

    @field_validator("facts")
    @classmethod
    def _validate_facts(cls, value: list[SignalFact]) -> list[SignalFact]:
        return _normalize_facts(value)

    @field_validator("failed_eligibility")
    @classmethod
    def _sort_failed(cls, value: list[ExpressionNode]) -> list[ExpressionNode]:
        return stable_unique_sorted(value)

    @field_validator("years")
    @classmethod
    def _sort_years(cls, value: list[int]) -> list[int]:
        return sorted(set(value))

    @field_validator("case_ids")
    @classmethod
    def _sort_case_ids(cls, value: list[str]) -> list[str]:
        return sorted(set(value))

    @model_validator(mode="after")
    def _validate_fact_references(self) -> SignalEvaluationBasis:
        facts_by_id = {fact.id: fact for fact in self.facts}
        available = set(facts_by_id)
        referenced = referenced_fact_ids(self.eligibility)
        for expression in self.failed_eligibility:
            referenced.update(referenced_fact_ids(expression))
        missing = sorted(referenced - available)
        if missing:
            raise ValueError(f"expression references unknown fact ids: {missing}")
        _validate_expression_value_types(self.eligibility, facts_by_id)
        for expression in self.failed_eligibility:
            _validate_expression_value_types(expression, facts_by_id)
        expected_failed = failed_expression_nodes(self.eligibility, facts_by_id)
        if [canonical_representation(item) for item in self.failed_eligibility] != [
            canonical_representation(item) for item in expected_failed
        ]:
            raise ValueError(
                "failed eligibility must contain exactly the failed eligibility nodes"
            )
        return self


class SignalWarning(FrozenDomainModel):
    code: str = Field(min_length=1)
    rule_code: str | None = None
    dataset: str | None = None
    message: str = Field(min_length=1)
    evaluation_basis: SignalEvaluationBasis

    @field_validator("dataset")
    @classmethod
    def _validate_dataset(cls, value: str | None) -> str | None:
        if value not in {None, "counterparty", "finance", "arbitration"}:
            raise ValueError("warning dataset is not registered")
        return value

    @model_validator(mode="after")
    def _validate_registry_contract(self) -> SignalWarning:
        registry = {
            "dataset_unavailable",
            "required_fact_missing",
            "required_period_unavailable",
            "normalization_warning_present",
            "status_conflict",
            "finance_reporting_semantics_unconfirmed",
            "finance_period_conflict",
            "arbitration_incomplete",
            "arbitration_period_unavailable",
            "arbitration_summary_conflict",
            "signal_confidence_insufficient",
        }
        if self.code not in registry:
            raise ValueError("warning code is not registered")
        if not self.rule_code or self.dataset is None:
            raise ValueError(
                "registered warnings require a non-empty rule_code and dataset"
            )
        required_prefix = {
            "counterparty": "counterparty.",
            "finance": "finance.",
            "arbitration": "arbitration.",
        }[self.dataset]
        if not self.rule_code.startswith(required_prefix):
            raise ValueError("warning rule_code does not match its dataset")
        expected_dataset = (
            "counterparty"
            if self.code == "status_conflict"
            else "finance"
            if self.code.startswith("finance_")
            else "arbitration"
            if self.code.startswith("arbitration_")
            else None
        )
        if expected_dataset is not None and self.dataset != expected_dataset:
            raise ValueError("warning code does not match its dataset")
        return self


class SignalFactualBasis(FrozenDomainModel):
    facts: list[SignalFact]
    eligibility: ExpressionNode
    trigger: ExpressionNode
    strength_decision: SignalStrengthDecision
    period_basis: SignalPeriodBasis
    years: list[int] = Field(default_factory=list)
    case_ids: list[str] = Field(default_factory=list)

    @field_validator("facts")
    @classmethod
    def _validate_facts(cls, value: list[SignalFact]) -> list[SignalFact]:
        return _normalize_facts(value)

    @field_validator("years")
    @classmethod
    def _sort_years(cls, value: list[int]) -> list[int]:
        return sorted(set(value))

    @field_validator("case_ids")
    @classmethod
    def _sort_case_ids(cls, value: list[str]) -> list[str]:
        return sorted(set(value))

    @model_validator(mode="after")
    def _validate_fact_references(self) -> SignalFactualBasis:
        facts_by_id = {fact.id: fact for fact in self.facts}
        available = set(facts_by_id)
        referenced = referenced_fact_ids(self.eligibility)
        referenced.update(referenced_fact_ids(self.trigger))
        for override in self.strength_decision.overrides:
            referenced.update(referenced_fact_ids(override.when))
        referenced.update(self.period_basis.fact_ids)
        missing = sorted(referenced - available)
        if missing:
            raise ValueError(f"basis references unknown fact ids: {missing}")
        _validate_expression_value_types(self.eligibility, facts_by_id)
        _validate_expression_value_types(self.trigger, facts_by_id)
        for override in self.strength_decision.overrides:
            _validate_expression_value_types(override.when, facts_by_id)
        return self


_CATEGORY_ORDER = {
    SignalCategory.LEGAL_STATUS: 0,
    SignalCategory.FINANCIAL: 1,
    SignalCategory.ARBITRATION: 2,
}


class Signal(FrozenDomainModel):
    code: str = Field(min_length=1)
    category: SignalCategory
    direction: SignalDirection
    strength: SignalStrength
    factual_basis: SignalFactualBasis
    source: list[SourceMetadata] = Field(min_length=1)
    period: SignalPeriod
    confidence: SignalConfidence
    warnings: list[SignalWarning] = Field(default_factory=list)

    @field_validator("source")
    @classmethod
    def _sort_sources(cls, value: list[SourceMetadata]) -> list[SourceMetadata]:
        normalized = [
            source.model_copy(
                update={"warnings": stable_unique_sorted(source.warnings)}
            )
            for source in value
        ]
        return stable_unique_sorted(
            normalized,
            primary_key=lambda source: (
                source.provider,
                source.dataset,
                source.received_at.isoformat(),
                source.endpoint,
                source.response_hash,
            ),
        )

    @field_validator("warnings")
    @classmethod
    def _sort_warnings(cls, value: list[SignalWarning]) -> list[SignalWarning]:
        return stable_unique_sorted(
            value,
            primary_key=lambda warning: (
                warning.code,
                warning.rule_code or "",
                warning.dataset or "",
            ),
        )

    @model_validator(mode="after")
    def _reject_low_confidence(self) -> Signal:
        if self.confidence is SignalConfidence.LOW:
            raise ValueError("low-confidence observations must not create a signal")
        expected_strength = self.factual_basis.strength_decision.default_strength
        for override in self.factual_basis.strength_decision.overrides:
            if evaluate_expression(override.when, self.factual_basis.facts):
                expected_strength = override.strength
                break
        if self.strength is not expected_strength:
            raise ValueError("signal strength does not match its factual basis")
        if self.period.kind != self.factual_basis.period_basis.operation.value:
            raise ValueError("signal period does not match its period basis")
        facts_by_id = {fact.id: fact for fact in self.factual_basis.facts}
        period_values = [
            facts_by_id[fact_id].exact_value
            for fact_id in self.factual_basis.period_basis.fact_ids
        ]
        if isinstance(self.period, NoPeriod):
            period_matches = self.period.as_of in period_values
        elif isinstance(self.period, DatePeriod):
            period_matches = self.period.value in period_values
        elif isinstance(self.period, DateRangePeriod):
            dates = [
                value.date() if isinstance(value, datetime) else value
                for value in period_values
                if isinstance(value, date)
            ]
            period_matches = bool(dates) and (
                self.period.start == min(dates) and self.period.end == max(dates)
            )
        elif isinstance(self.period, YearPeriod):
            years = [
                value
                for value in period_values
                if isinstance(value, int) and not isinstance(value, bool)
            ]
            period_matches = self.period.year in years
        else:
            years = [
                value
                for value in period_values
                if isinstance(value, int) and not isinstance(value, bool)
            ]
            period_matches = bool(years) and (
                self.period.start_year == min(years)
                and self.period.end_year == max(years)
            )
        if not period_matches:
            raise ValueError("signal period value is not reproducible from period basis")
        if any(warning.evaluation_basis.failed_eligibility for warning in self.warnings):
            raise ValueError("signal-level warnings must not contain failed eligibility")
        if any(
            warning.code != "normalization_warning_present"
            or warning.rule_code != self.code
            for warning in self.warnings
        ):
            raise ValueError("signal-level warnings must be related normalization warnings")
        if isinstance(self.period, NoPeriod) and self.period.as_of not in {
            source.received_at for source in self.source
        }:
            raise ValueError("no_period as_of must come from signal source metadata")
        if not evaluate_expression(
            self.factual_basis.eligibility,
            self.factual_basis.facts,
        ):
            raise ValueError("signal eligibility must evaluate to true")
        if not evaluate_expression(
            self.factual_basis.trigger,
            self.factual_basis.facts,
        ):
            raise ValueError("signal trigger must evaluate to true")
        return self


class SignalEvaluationResult(FrozenDomainModel):
    ruleset_version: Literal["1"] = "1"
    signals: list[Signal] = Field(default_factory=list)
    warnings: list[SignalWarning] = Field(default_factory=list)

    @field_validator("signals")
    @classmethod
    def _sort_signals(cls, value: list[Signal]) -> list[Signal]:
        codes = [signal.code for signal in value]
        if len(codes) != len(set(codes)):
            raise ValueError("signal codes must be unique")
        return stable_sorted(
            value,
            primary_key=lambda signal: (_CATEGORY_ORDER[signal.category], signal.code),
        )

    @field_validator("warnings")
    @classmethod
    def _sort_warnings(cls, value: list[SignalWarning]) -> list[SignalWarning]:
        if any(not warning.evaluation_basis.failed_eligibility for warning in value):
            raise ValueError("result-level warnings must contain failed eligibility")
        return stable_unique_sorted(
            value,
            primary_key=lambda warning: (
                warning.code,
                warning.rule_code or "",
                warning.dataset or "",
            ),
        )


AllOfExpression.model_rebuild()
AnyOfExpression.model_rebuild()
NotExpression.model_rebuild()
SignalStrengthOverride.model_rebuild()
SignalEvaluationBasis.model_rebuild()
SignalFactualBasis.model_rebuild()
Signal.model_rebuild()


__all__ = [
    "AbsenceOperator",
    "AllOfExpression",
    "AnyOfExpression",
    "ComparisonComparator",
    "CountOperator",
    "DatePeriod",
    "DateRangePeriod",
    "DecimalComparisonOperator",
    "DecimalRatioOperator",
    "EqualityOperator",
    "ExactValue",
    "ExpressionNode",
    "FactOperand",
    "GreaterOrEqualOperator",
    "GreaterThanOperator",
    "InequalityOperator",
    "LessOrEqualOperator",
    "LessThanOperator",
    "LiteralOperand",
    "NoPeriod",
    "NotExpression",
    "PredicateExpression",
    "PresenceOperator",
    "Signal",
    "SignalCategory",
    "SignalConfidence",
    "SignalDirection",
    "SignalEvaluationBasis",
    "SignalEvaluationResult",
    "SignalFact",
    "SignalFactualBasis",
    "SignalPeriod",
    "SignalPeriodBasis",
    "SignalPeriodOperation",
    "SignalStrength",
    "SignalStrengthDecision",
    "SignalStrengthOverride",
    "SignalWarning",
    "YearPeriod",
    "YearRangePeriod",
    "canonical_representation",
    "evaluate_expression",
    "failed_expression_nodes",
    "referenced_fact_ids",
]
