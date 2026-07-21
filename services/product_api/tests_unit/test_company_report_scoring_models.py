from decimal import Decimal

import pytest
from pydantic import ValidationError

from product_api.company_reports.scoring import (
    ScoringDomainBreakdown,
    ScoringReason,
    ScoringReasonRole,
    ScoringResult,
    ScoringWarning,
    ScoringWarningCode,
)
from product_api.company_reports.scoring import score_signals
from product_api.company_reports.signals import evaluate_signals
from product_api.company_reports import DatasetReportStatus
from company_report_signal_test_helpers import company_report
from product_api.company_reports.signals import (
    SignalCategory,
    SignalConfidence,
    SignalDirection,
    SignalStrength,
)


def test_reason_is_frozen_extra_forbid_and_uses_registered_weight():
    reason = ScoringReason(
        signal_code="finance.negative_equity",
        category=SignalCategory.FINANCIAL,
        direction=SignalDirection.NEGATIVE,
        strength=SignalStrength.HIGH,
        signal_confidence=SignalConfidence.HIGH,
        weight=Decimal("-4"),
        contribution=Decimal("-4"),
        role=ScoringReasonRole.SCORED,
    )

    with pytest.raises(ValidationError):
        ScoringReason(**reason.model_dump(), unexpected=True)
    with pytest.raises(ValidationError):
        reason.weight = Decimal("0")
    with pytest.raises(ValidationError, match="registered weight"):
        ScoringReason(**{**reason.model_dump(), "contribution": Decimal("-3")})


def test_models_reject_float_and_normalize_nested_code_lists():
    with pytest.raises(ValidationError, match="do not accept float"):
        ScoringDomainBreakdown(
            category=SignalCategory.FINANCIAL,
            raw_points=-4.0,
            capped_points=Decimal("-4"),
        )

    breakdown = ScoringDomainBreakdown(
        category=SignalCategory.FINANCIAL,
        raw_points=Decimal("-4"),
        capped_points=Decimal("-4"),
        considered_signal_codes=["finance.negative_equity", "finance.negative_equity"],
        suppressed_rule_codes=[],
    )
    assert breakdown.considered_signal_codes == ["finance.negative_equity"]


def test_informational_reason_and_warning_shapes_are_closed():
    reason = ScoringReason(
        signal_code="counterparty.status_conflict",
        category=SignalCategory.LEGAL_STATUS,
        direction=SignalDirection.INFORMATIONAL,
        strength=SignalStrength.HIGH,
        signal_confidence=SignalConfidence.HIGH,
        weight=Decimal("0"),
        contribution=Decimal("0"),
        role=ScoringReasonRole.INFORMATIONAL,
    )
    assert reason.role is ScoringReasonRole.INFORMATIONAL

    warning = ScoringWarning(
        code=ScoringWarningCode.SOURCE_RULE_SUPPRESSED,
        rule_code="finance.net_loss",
        source_warning_codes=["required_fact_missing", "required_fact_missing"],
        signal_codes=[],
        message="A source signal rule was not evaluable.",
    )
    assert warning.source_warning_codes == ["required_fact_missing"]
    with pytest.raises(ValidationError, match="message"):
        ScoringWarning(**{**warning.model_dump(), "message": "dynamic"})


def test_insufficient_warning_must_exactly_restate_source_gate_evidence():
    result = score_signals(
        evaluate_signals(
            company_report(counterparty_status=DatasetReportStatus.DISABLED)
        )
    )
    dumped = result.model_dump(mode="python")
    insufficient = next(
        warning
        for warning in dumped["warnings"]
        if warning["code"] == ScoringWarningCode.INSUFFICIENT_DATA
    )
    assert insufficient["source_warning_codes"] == ["dataset_unavailable"]
    assert insufficient["signal_codes"] == []
    assert ScoringResult.model_validate(dumped) == result

    invalid = {
        **dumped,
        "warnings": [
            {
                **warning,
                "source_warning_codes": [],
            }
            if warning["code"] == ScoringWarningCode.INSUFFICIENT_DATA
            else warning
            for warning in dumped["warnings"]
        ],
    }
    with pytest.raises(ValidationError, match="hard gates"):
        ScoringResult.model_validate(invalid)
