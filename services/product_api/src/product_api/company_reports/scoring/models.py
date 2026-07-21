from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from product_api.company_reports.models import FrozenDomainModel
from product_api.company_reports.signals.models import (
    SignalCategory,
    SignalConfidence,
    SignalDirection,
    SignalStrength,
)

from .rules import (
    CATEGORY_CAPS,
    CATEGORY_ORDER,
    CONFIDENCE_QUANTUM,
    CONFLICT_MULTIPLIER,
    MAX_QUALITY_POINTS,
    QUALITY_HIGH_OR_CLEAN,
    QUALITY_MEDIUM,
    SCORING_RULESET_VERSION,
    rule_for_code,
)


class ScoringLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT_DATA = "insufficient_data"


class ScoringReasonRole(StrEnum):
    SCORED = "scored"
    INFORMATIONAL = "informational"


class ScoringWarningCode(StrEnum):
    SOURCE_RULE_SUPPRESSED = "source_rule_suppressed"
    MIXED_DIRECTIONS = "mixed_directions"
    STATUS_CONFLICT = "status_conflict"
    INSUFFICIENT_DATA = "insufficient_data"


_MESSAGES = {
    ScoringWarningCode.SOURCE_RULE_SUPPRESSED: "A source signal rule was not evaluable.",
    ScoringWarningCode.MIXED_DIRECTIONS: "Positive and negative factual signals are both present.",
    ScoringWarningCode.STATUS_CONFLICT: "Counterparty status facts are conflicting.",
    ScoringWarningCode.INSUFFICIENT_DATA: "Available evidence is insufficient for a scoring level.",
}


def _reject_float(value: object) -> object:
    if isinstance(value, float):
        raise ValueError("scoring decimals do not accept float")
    return value


def _sorted_unique_codes(value: list[str]) -> list[str]:
    return sorted(set(value))


class ScoringReason(FrozenDomainModel):
    signal_code: str = Field(min_length=1)
    category: SignalCategory
    direction: SignalDirection
    strength: SignalStrength
    signal_confidence: SignalConfidence
    weight: Decimal
    contribution: Decimal
    role: ScoringReasonRole

    @field_validator("weight", "contribution", mode="before")
    @classmethod
    def _validate_decimal(cls, value: object) -> object:
        return _reject_float(value)

    @model_validator(mode="after")
    def _validate_registered_rule(self) -> ScoringReason:
        rule = rule_for_code(self.signal_code)
        if self.signal_confidence is SignalConfidence.LOW:
            raise ValueError("low-confidence observations cannot be scoring reasons")
        if (
            self.category is not rule.category
            or self.direction is not rule.direction
            or self.strength not in rule.allowed_strengths
        ):
            raise ValueError("scoring reason does not match the registered signal rule")
        registered_weight = rule.weight_for(self.strength)
        if self.direction is SignalDirection.INFORMATIONAL:
            if (
                self.role is not ScoringReasonRole.INFORMATIONAL
                or self.weight != Decimal("0")
                or self.contribution != Decimal("0")
            ):
                raise ValueError("informational scoring reasons must have zero impact")
        elif (
            self.role is not ScoringReasonRole.SCORED
            or self.weight != registered_weight
            or self.contribution != registered_weight
        ):
            raise ValueError("scored contribution must equal the registered weight")
        return self


class ScoringDomainBreakdown(FrozenDomainModel):
    category: SignalCategory
    raw_points: Decimal
    capped_points: Decimal
    considered_signal_codes: list[str] = Field(default_factory=list)
    suppressed_rule_codes: list[str] = Field(default_factory=list)

    @field_validator("raw_points", "capped_points", mode="before")
    @classmethod
    def _validate_decimal(cls, value: object) -> object:
        return _reject_float(value)

    @field_validator("considered_signal_codes", "suppressed_rule_codes")
    @classmethod
    def _normalize_codes(cls, value: list[str]) -> list[str]:
        return _sorted_unique_codes(value)

    @model_validator(mode="after")
    def _validate_category_codes_and_cap(self) -> ScoringDomainBreakdown:
        for code in [*self.considered_signal_codes, *self.suppressed_rule_codes]:
            if rule_for_code(code).category is not self.category:
                raise ValueError("domain breakdown code does not match its category")
        lower, upper = CATEGORY_CAPS[self.category]
        expected = min(max(self.raw_points, lower), upper)
        if self.capped_points != expected:
            raise ValueError("capped points do not match the registered category cap")
        return self


class ScoringConfidenceBreakdown(FrozenDomainModel):
    value: Decimal
    quality_points: int = Field(ge=0)
    max_quality_points: int = Field(ge=0)
    evaluated_rule_count: int = Field(ge=0)
    suppressed_rule_count: int = Field(ge=0)
    high_confidence_signal_count: int = Field(ge=0)
    medium_confidence_signal_count: int = Field(ge=0)
    conflict_multiplier: Decimal

    @field_validator("value", "conflict_multiplier", mode="before")
    @classmethod
    def _validate_decimal(cls, value: object) -> object:
        return _reject_float(value)

    @model_validator(mode="after")
    def _validate_confidence(self) -> ScoringConfidenceBreakdown:
        if not Decimal("0") <= self.value <= Decimal("1"):
            raise ValueError("confidence must be within [0, 1]")
        if self.max_quality_points != MAX_QUALITY_POINTS:
            raise ValueError("confidence maximum quality points are incompatible")
        if self.evaluated_rule_count + self.suppressed_rule_count != 13:
            raise ValueError("confidence rule counts must cover the scoring registry")
        if self.conflict_multiplier not in {Decimal("1"), CONFLICT_MULTIPLIER}:
            raise ValueError("confidence conflict multiplier is incompatible")
        return self


class ScoringWarning(FrozenDomainModel):
    code: ScoringWarningCode
    rule_code: str | None = None
    source_warning_codes: list[str] = Field(default_factory=list)
    signal_codes: list[str] = Field(default_factory=list)
    message: str = Field(min_length=1)

    @field_validator("source_warning_codes", "signal_codes")
    @classmethod
    def _normalize_codes(cls, value: list[str]) -> list[str]:
        return _sorted_unique_codes(value)

    @model_validator(mode="after")
    def _validate_shape(self) -> ScoringWarning:
        if self.message != _MESSAGES[self.code]:
            raise ValueError("scoring warning message is incompatible")
        if self.code is ScoringWarningCode.SOURCE_RULE_SUPPRESSED:
            if (
                self.rule_code is None
                or not self.source_warning_codes
                or self.signal_codes
            ):
                raise ValueError("source suppression warning fields are incompatible")
            rule_for_code(self.rule_code)
        elif self.code is ScoringWarningCode.MIXED_DIRECTIONS:
            if self.rule_code is not None or self.source_warning_codes:
                raise ValueError("mixed directions warning fields are incompatible")
        elif self.code is ScoringWarningCode.STATUS_CONFLICT:
            if (
                self.rule_code != "counterparty.status_conflict"
                or any(code != "status_conflict" for code in self.source_warning_codes)
                or any(
                    code != "counterparty.status_conflict" for code in self.signal_codes
                )
            ):
                raise ValueError("status conflict warning fields are incompatible")
        elif self.rule_code is not None:
            raise ValueError("insufficient data warning fields are incompatible")
        return self


class ScoringResult(FrozenDomainModel):
    ruleset_version: Literal["1"] = SCORING_RULESET_VERSION
    signal_ruleset_version: Literal["1"] = SCORING_RULESET_VERSION
    level: ScoringLevel
    score_points: Decimal | None
    reasons: list[ScoringReason] = Field(default_factory=list)
    domain_breakdown: list[ScoringDomainBreakdown]
    confidence: ScoringConfidenceBreakdown
    warnings: list[ScoringWarning] = Field(default_factory=list)

    @field_validator("score_points", mode="before")
    @classmethod
    def _validate_score(cls, value: object) -> object:
        return _reject_float(value)

    @field_validator("reasons")
    @classmethod
    def _sort_reasons(cls, value: list[ScoringReason]) -> list[ScoringReason]:
        codes = [reason.signal_code for reason in value]
        if len(codes) != len(set(codes)):
            raise ValueError("scoring reason signal codes must be unique")
        return sorted(
            value,
            key=lambda reason: (CATEGORY_ORDER[reason.category], reason.signal_code),
        )

    @field_validator("warnings")
    @classmethod
    def _sort_warnings(cls, value: list[ScoringWarning]) -> list[ScoringWarning]:
        return sorted(
            value,
            key=lambda warning: (
                warning.code.value,
                warning.rule_code or "",
                warning.model_dump_json(),
            ),
        )

    @model_validator(mode="after")
    def _validate_result(self) -> ScoringResult:
        categories = [item.category for item in self.domain_breakdown]
        expected_categories = [
            SignalCategory.LEGAL_STATUS,
            SignalCategory.FINANCIAL,
            SignalCategory.ARBITRATION,
        ]
        if categories != expected_categories:
            raise ValueError("domain breakdown must contain the three categories in order")

        reason_codes = {reason.signal_code for reason in self.reasons}
        breakdown_by_category = {
            breakdown.category: breakdown for breakdown in self.domain_breakdown
        }
        for category, breakdown in breakdown_by_category.items():
            category_reasons = [
                reason for reason in self.reasons if reason.category is category
            ]
            if breakdown.considered_signal_codes != sorted(
                reason.signal_code for reason in category_reasons
            ):
                raise ValueError("considered codes must contain category present signals")
            if breakdown.raw_points != sum(
                (reason.contribution for reason in category_reasons), Decimal("0")
            ):
                raise ValueError("domain raw points must equal reason contributions")

        suppressed_codes = {
            code
            for breakdown in self.domain_breakdown
            for code in breakdown.suppressed_rule_codes
        }
        if reason_codes & suppressed_codes:
            raise ValueError("suppressed rules cannot have scoring reasons")
        source_warnings = [
            warning
            for warning in self.warnings
            if warning.code is ScoringWarningCode.SOURCE_RULE_SUPPRESSED
        ]
        if {warning.rule_code for warning in source_warnings} != suppressed_codes:
            raise ValueError("suppressed rules require exactly one source warning")
        if len(source_warnings) != len(suppressed_codes):
            raise ValueError("source suppression warnings must be unique by rule")

        positive = any(
            reason.direction is SignalDirection.POSITIVE for reason in self.reasons
        )
        negative = any(
            reason.direction is SignalDirection.NEGATIVE for reason in self.reasons
        )
        mixed = [
            warning
            for warning in self.warnings
            if warning.code is ScoringWarningCode.MIXED_DIRECTIONS
        ]
        if len(mixed) > 1 or bool(mixed) is not (positive and negative):
            raise ValueError("mixed directions warning does not match present signals")
        if mixed and mixed[0].signal_codes != sorted(
            reason.signal_code
            for reason in self.reasons
            if reason.direction
            in {SignalDirection.POSITIVE, SignalDirection.NEGATIVE}
        ):
            raise ValueError("mixed directions codes do not match present signals")

        source_status_conflict = any(
            "status_conflict" in warning.source_warning_codes
            for warning in source_warnings
        )
        signal_status_conflict = "counterparty.status_conflict" in reason_codes
        status = [
            warning
            for warning in self.warnings
            if warning.code is ScoringWarningCode.STATUS_CONFLICT
        ]
        if len(status) != int(source_status_conflict or signal_status_conflict):
            raise ValueError("status conflict warning does not match source evidence")
        if status and (
            status[0].source_warning_codes
            != (["status_conflict"] if source_status_conflict else [])
            or status[0].signal_codes
            != (["counterparty.status_conflict"] if signal_status_conflict else [])
        ):
            raise ValueError("status conflict warning evidence is incompatible")

        expected_suppressed = len(suppressed_codes)
        expected_medium = sum(
            reason.signal_confidence is SignalConfidence.MEDIUM
            for reason in self.reasons
        )
        expected_high = sum(
            reason.signal_confidence is SignalConfidence.HIGH
            for reason in self.reasons
        )
        expected_quality = (
            (13 - expected_suppressed) * QUALITY_HIGH_OR_CLEAN
            - expected_medium
        )
        expected_multiplier = (
            CONFLICT_MULTIPLIER
            if source_status_conflict or signal_status_conflict
            else Decimal("1")
        )
        expected_confidence = (
            Decimal(expected_quality) / Decimal(MAX_QUALITY_POINTS) * expected_multiplier
        ).quantize(CONFIDENCE_QUANTUM, rounding=ROUND_HALF_UP)
        if (
            self.confidence.suppressed_rule_count != expected_suppressed
            or self.confidence.evaluated_rule_count != 13 - expected_suppressed
            or self.confidence.medium_confidence_signal_count != expected_medium
            or self.confidence.high_confidence_signal_count != expected_high
            or self.confidence.quality_points != expected_quality
            or self.confidence.conflict_multiplier != expected_multiplier
            or self.confidence.value != expected_confidence
        ):
            raise ValueError("confidence breakdown does not match scoring evidence")

        insufficient = [
            warning
            for warning in self.warnings
            if warning.code is ScoringWarningCode.INSUFFICIENT_DATA
        ]
        if len(insufficient) != int(self.level is ScoringLevel.INSUFFICIENT_DATA):
            raise ValueError("insufficient data warning does not match scoring level")
        if (self.score_points is None) is not (
            self.level is ScoringLevel.INSUFFICIENT_DATA
        ):
            raise ValueError("score points must be absent exactly for insufficient data")
        if insufficient:
            expected_source_codes = sorted(
                {
                    code
                    for warning in source_warnings
                    for code in warning.source_warning_codes
                }
            )
            expected_signal_codes = (
                ["counterparty.status_conflict"]
                if signal_status_conflict
                else []
            )
            if (
                insufficient[0].source_warning_codes != expected_source_codes
                or insufficient[0].signal_codes != expected_signal_codes
            ):
                raise ValueError(
                    "insufficient data warning evidence does not match hard gates"
                )
        if self.score_points is not None and self.score_points != sum(
            (item.capped_points for item in self.domain_breakdown), Decimal("0")
        ):
            raise ValueError("score points must equal capped domain points")
        if self.level is ScoringLevel.LOW and not negative:
            raise ValueError("low scoring level requires a present negative signal")
        return self


__all__ = [
    "ScoringConfidenceBreakdown",
    "ScoringDomainBreakdown",
    "ScoringLevel",
    "ScoringReason",
    "ScoringReasonRole",
    "ScoringResult",
    "ScoringWarning",
    "ScoringWarningCode",
]
