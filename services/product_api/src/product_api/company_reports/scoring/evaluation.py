from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from product_api.company_reports.signals.models import (
    SignalConfidence,
    SignalDirection,
    SignalEvaluationResult,
)

from .models import (
    ScoringConfidenceBreakdown,
    ScoringDomainBreakdown,
    ScoringLevel,
    ScoringReason,
    ScoringReasonRole,
    ScoringResult,
    ScoringWarning,
    ScoringWarningCode,
)
from .rules import (
    CATEGORY_CAPS,
    CATEGORY_ORDER,
    CONFIDENCE_QUANTUM,
    CONFLICT_MULTIPLIER,
    MAX_QUALITY_POINTS,
    MINIMUM_CONFIDENCE,
    QUALITY_HIGH_OR_CLEAN,
    SCORING_RULESET_VERSION,
    dataset_for_code,
    rule_for_code,
)


def _source_suppression_warning(rule_code: str, source_codes: list[str]) -> ScoringWarning:
    return ScoringWarning(
        code=ScoringWarningCode.SOURCE_RULE_SUPPRESSED,
        rule_code=rule_code,
        source_warning_codes=source_codes,
        signal_codes=[],
        message="A source signal rule was not evaluable.",
    )


def score_signals(signal_evaluation: SignalEvaluationResult) -> ScoringResult:
    """Score a ruleset-v1 factual signal result without mutating its input."""

    if signal_evaluation.ruleset_version != SCORING_RULESET_VERSION:
        raise ValueError("signal evaluation has an incompatible ruleset")

    present_by_code = {}
    for signal in signal_evaluation.signals:
        rule = rule_for_code(signal.code)
        if (
            signal.category is not rule.category
            or signal.direction is not rule.direction
            or signal.strength not in rule.allowed_strengths
            or signal.confidence is SignalConfidence.LOW
        ):
            raise ValueError("signal does not match the scoring registry")
        if signal.code in present_by_code:
            raise ValueError("signal codes must be unique")
        present_by_code[signal.code] = signal

    suppressed_by_code: dict[str, list[str]] = {}
    source_status_conflict = False
    for warning in signal_evaluation.warnings:
        if warning.rule_code is None or warning.dataset is None:
            raise ValueError("result warning must identify its rule and dataset")
        if dataset_for_code(warning.rule_code) != warning.dataset:
            raise ValueError("result warning dataset does not match the scoring registry")
        if warning.rule_code in present_by_code:
            raise ValueError("a signal rule cannot be both present and suppressed")
        if warning.rule_code in suppressed_by_code:
            raise ValueError("a rule cannot have multiple result-level suppression warnings")
        suppressed_by_code[warning.rule_code] = [warning.code]
        source_status_conflict = source_status_conflict or warning.code == "status_conflict"

    reasons: list[ScoringReason] = []
    for code, signal in present_by_code.items():
        rule = rule_for_code(code)
        informational = signal.direction is SignalDirection.INFORMATIONAL
        weight = Decimal("0") if informational else rule.weight_for(signal.strength)
        reasons.append(
            ScoringReason(
                signal_code=code,
                category=signal.category,
                direction=signal.direction,
                strength=signal.strength,
                signal_confidence=signal.confidence,
                weight=weight,
                contribution=weight,
                role=(
                    ScoringReasonRole.INFORMATIONAL
                    if informational
                    else ScoringReasonRole.SCORED
                ),
            )
        )

    breakdown: list[ScoringDomainBreakdown] = []
    for category in sorted(CATEGORY_ORDER, key=CATEGORY_ORDER.__getitem__):
        category_reasons = [reason for reason in reasons if reason.category is category]
        raw_points = sum(
            (reason.contribution for reason in category_reasons), Decimal("0")
        )
        lower, upper = CATEGORY_CAPS[category]
        breakdown.append(
            ScoringDomainBreakdown(
                category=category,
                raw_points=raw_points,
                capped_points=min(max(raw_points, lower), upper),
                considered_signal_codes=[reason.signal_code for reason in category_reasons],
                suppressed_rule_codes=[
                    code
                    for code in suppressed_by_code
                    if rule_for_code(code).category is category
                ],
            )
        )

    medium_count = sum(
        signal.confidence is SignalConfidence.MEDIUM
        for signal in present_by_code.values()
    )
    high_count = sum(
        signal.confidence is SignalConfidence.HIGH
        for signal in present_by_code.values()
    )
    suppressed_count = len(suppressed_by_code)
    quality_points = (13 - suppressed_count) * QUALITY_HIGH_OR_CLEAN - medium_count
    status_signal_present = "counterparty.status_conflict" in present_by_code
    conflict_multiplier = (
        CONFLICT_MULTIPLIER
        if source_status_conflict or status_signal_present
        else Decimal("1")
    )
    confidence_value = (
        Decimal(quality_points) / Decimal(MAX_QUALITY_POINTS) * conflict_multiplier
    ).quantize(CONFIDENCE_QUANTUM, rounding=ROUND_HALF_UP)
    confidence = ScoringConfidenceBreakdown(
        value=confidence_value,
        quality_points=quality_points,
        max_quality_points=MAX_QUALITY_POINTS,
        evaluated_rule_count=13 - suppressed_count,
        suppressed_rule_count=suppressed_count,
        high_confidence_signal_count=high_count,
        medium_confidence_signal_count=medium_count,
        conflict_multiplier=conflict_multiplier,
    )

    score = sum((item.capped_points for item in breakdown), Decimal("0"))
    insufficient = (
        "counterparty.dissolved" in suppressed_by_code
        or source_status_conflict
        or status_signal_present
        or confidence.value < MINIMUM_CONFIDENCE
    )
    if insufficient:
        level = ScoringLevel.INSUFFICIENT_DATA
        score_points: Decimal | None = None
    elif score >= Decimal("3"):
        level = ScoringLevel.HIGH
        score_points = score
    elif score <= Decimal("-7"):
        level = ScoringLevel.LOW
        score_points = score
    else:
        level = ScoringLevel.MEDIUM
        score_points = score

    warnings: list[ScoringWarning] = [
        _source_suppression_warning(code, source_codes)
        for code, source_codes in suppressed_by_code.items()
    ]
    signed_reasons = [
        reason
        for reason in reasons
        if reason.direction
        in {SignalDirection.POSITIVE, SignalDirection.NEGATIVE}
    ]
    if {
        reason.direction for reason in signed_reasons
    } == {SignalDirection.POSITIVE, SignalDirection.NEGATIVE}:
        warnings.append(
            ScoringWarning(
                code=ScoringWarningCode.MIXED_DIRECTIONS,
                rule_code=None,
                source_warning_codes=[],
                signal_codes=[reason.signal_code for reason in signed_reasons],
                message="Positive and negative factual signals are both present.",
            )
        )
    if source_status_conflict or status_signal_present:
        warnings.append(
            ScoringWarning(
                code=ScoringWarningCode.STATUS_CONFLICT,
                rule_code="counterparty.status_conflict",
                source_warning_codes=(
                    ["status_conflict"] if source_status_conflict else []
                ),
                signal_codes=(
                    ["counterparty.status_conflict"] if status_signal_present else []
                ),
                message="Counterparty status facts are conflicting.",
            )
        )
    if level is ScoringLevel.INSUFFICIENT_DATA:
        warnings.append(
            ScoringWarning(
                code=ScoringWarningCode.INSUFFICIENT_DATA,
                rule_code=None,
                source_warning_codes=sorted(
                    code for codes in suppressed_by_code.values() for code in codes
                ),
                signal_codes=(
                    ["counterparty.status_conflict"] if status_signal_present else []
                ),
                message="Available evidence is insufficient for a scoring level.",
            )
        )

    return ScoringResult(
        ruleset_version=SCORING_RULESET_VERSION,
        signal_ruleset_version=signal_evaluation.ruleset_version,
        level=level,
        score_points=score_points,
        reasons=reasons,
        domain_breakdown=breakdown,
        confidence=confidence,
        warnings=warnings,
    )


__all__ = ["score_signals"]
