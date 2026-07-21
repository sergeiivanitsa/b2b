import copy
from datetime import date
from decimal import Decimal

import pytest

from product_api.company_reports.scoring import (
    ScoringLevel,
    ScoringWarningCode,
    score_signals,
)
from product_api.company_reports.scoring.rules import SCORING_RULE_REGISTRY
from product_api.company_reports.signals import (
    Signal,
    SignalCategory,
    SignalConfidence,
    SignalDirection,
    SignalEvaluationResult,
    SignalStrength,
    SignalWarning,
    evaluate_signals,
)
from product_api.company_reports.persistence import (
    calculate_company_report_snapshot_hash,
    company_report_to_snapshot,
)
from company_report_signal_test_helpers import (
    arbitration_facts,
    company_report,
    complete_company_report,
    counterparty_facts,
    finance_facts,
)
from product_api.company_reports import DatasetReportStatus, FinancialPeriod


def _signal(
    code: str,
    *,
    confidence: SignalConfidence = SignalConfidence.HIGH,
    strength: SignalStrength | None = None,
) -> Signal:
    rule = SCORING_RULE_REGISTRY[code]
    return Signal.model_construct(
        code=code,
        category=rule.category,
        direction=rule.direction,
        strength=strength
        or next(iter(sorted(rule.allowed_strengths, key=lambda value: value.value))),
        confidence=confidence,
    )


def _warning(rule_code: str, code: str = "required_fact_missing") -> SignalWarning:
    return SignalWarning.model_construct(
        code=code,
        rule_code=rule_code,
        dataset=rule_code.split(".", maxsplit=1)[0],
    )


def _result(
    signals: list[Signal] | None = None,
    warnings: list[SignalWarning] | None = None,
) -> SignalEvaluationResult:
    return SignalEvaluationResult.model_construct(
        ruleset_version="1",
        signals=signals or [],
        warnings=warnings or [],
    )


def test_registry_has_exact_production_codes_and_no_reporting_absent():
    expected = {
        "counterparty.active": ("legal_status", "positive", {"medium": "2"}),
        "counterparty.dissolved": ("legal_status", "negative", {"critical": "-8"}),
        "counterparty.long_operating_history": ("legal_status", "positive", {"low": "1"}),
        "counterparty.status_conflict": ("legal_status", "informational", {"high": "0"}),
        "finance.negative_equity": ("financial", "negative", {"high": "-4"}),
        "finance.revenue_decline": ("financial", "negative", {"medium": "-2"}),
        "finance.net_loss": ("financial", "negative", {"medium": "-2"}),
        "finance.cash_shortfall": ("financial", "negative", {"medium": "-2", "high": "-4"}),
        "finance.high_accounts_payable": ("financial", "negative", {"high": "-3"}),
        "arbitration.high_respondent_case_count": ("arbitration", "negative", {"high": "-3"}),
        "arbitration.respondent_case_growth": ("arbitration", "negative", {"medium": "-2"}),
        "arbitration.open_cases": ("arbitration", "negative", {"medium": "-1"}),
        "arbitration.frequent_plaintiff": ("arbitration", "positive", {"medium": "1"}),
    }
    assert set(SCORING_RULE_REGISTRY) == set(expected)
    assert {
        code: (
            rule.category.value,
            rule.direction.value,
            {strength.value: str(weight) for strength, weight in rule.weights.items()},
        )
        for code, rule in SCORING_RULE_REGISTRY.items()
    } == expected
    assert "finance.reporting_absent" not in SCORING_RULE_REGISTRY


@pytest.mark.parametrize(
    ("codes", "expected_score", "expected_level"),
    [
        (
            ["counterparty.active", "counterparty.long_operating_history"],
            Decimal("3"),
            ScoringLevel.HIGH,
        ),
        (["counterparty.active"], Decimal("2"), ScoringLevel.MEDIUM),
        (
            [
                "counterparty.active",
                "finance.negative_equity",
                "finance.cash_shortfall",
            ],
            Decimal("-6"),
            ScoringLevel.MEDIUM,
        ),
        (
            [
                "counterparty.active",
                "finance.negative_equity",
                "finance.high_accounts_payable",
                "arbitration.respondent_case_growth",
            ],
            Decimal("-7"),
            ScoringLevel.LOW,
        ),
        (["counterparty.dissolved"], Decimal("-8"), ScoringLevel.LOW),
    ],
)
def test_model_b_boundaries(codes, expected_score, expected_level):
    signals = [
        _signal(
            code,
            strength=(
                SignalStrength.HIGH
                if code == "finance.cash_shortfall"
                else None
            ),
        )
        for code in codes
    ]
    result = score_signals(_result(signals))

    assert result.level is expected_level
    assert result.score_points == expected_score


def test_category_caps_confidence_and_permutation_are_deterministic():
    signals = [
        _signal("counterparty.active"),
        _signal("finance.negative_equity", confidence=SignalConfidence.MEDIUM),
        _signal("finance.cash_shortfall"),
        _signal("finance.high_accounts_payable"),
        _signal("arbitration.high_respondent_case_count"),
        _signal("arbitration.respondent_case_growth"),
        _signal("arbitration.open_cases"),
    ]
    left = score_signals(_result(signals))
    right = score_signals(_result(list(reversed(signals))))

    assert left.model_dump(mode="json") == right.model_dump(mode="json")
    assert left.score_points == Decimal("-11")
    assert [item.capped_points for item in left.domain_breakdown] == [
        Decimal("2"),
        Decimal("-8"),
        Decimal("-5"),
    ]
    assert left.confidence.value == Decimal("0.9808")
    assert [warning.code for warning in left.warnings] == [ScoringWarningCode.MIXED_DIRECTIONS]
    mixed = left.warnings[0]
    assert mixed.rule_code is None
    assert mixed.source_warning_codes == []
    assert mixed.signal_codes == [
        "arbitration.high_respondent_case_count",
        "arbitration.open_cases",
        "arbitration.respondent_case_growth",
        "counterparty.active",
        "finance.cash_shortfall",
        "finance.high_accounts_payable",
        "finance.negative_equity",
    ]
    assert mixed.message == "Positive and negative factual signals are both present."


def test_suppression_and_status_conflict_are_insufficient_data():
    finance_suppressed = [
        _warning(code)
        for code in SCORING_RULE_REGISTRY
        if code.startswith("finance.")
    ]
    suppressed = score_signals(
        _result([_signal("counterparty.active")], finance_suppressed)
    )
    assert suppressed.level is ScoringLevel.INSUFFICIENT_DATA
    assert suppressed.score_points is None
    assert suppressed.confidence.value == Decimal("0.6154")

    conflict = score_signals(
        _result([_signal("counterparty.status_conflict")])
    )
    assert conflict.level is ScoringLevel.INSUFFICIENT_DATA
    assert conflict.reasons[0].contribution == Decimal("0")
    assert {warning.code for warning in conflict.warnings} == {
        ScoringWarningCode.INSUFFICIENT_DATA,
        ScoringWarningCode.STATUS_CONFLICT,
    }


def test_cash_shortfall_weights_use_valid_public_signal_evaluation():
    medium_report = complete_company_report(
        finance=finance_facts(
            [
                FinancialPeriod(
                    year=2025,
                    cash_and_equivalents=Decimal("25"),
                    short_term_liabilities=Decimal("100"),
                )
            ]
        )
    )
    high_report = complete_company_report(
        finance=finance_facts(
            [
                FinancialPeriod(
                    year=2025,
                    cash_and_equivalents=Decimal("24"),
                    short_term_liabilities=Decimal("100"),
                )
            ]
        )
    )

    medium = score_signals(evaluate_signals(medium_report))
    high = score_signals(evaluate_signals(high_report))
    medium_reason = next(
        reason for reason in medium.reasons if reason.signal_code == "finance.cash_shortfall"
    )
    high_reason = next(
        reason for reason in high.reasons if reason.signal_code == "finance.cash_shortfall"
    )
    assert (medium_reason.strength, medium_reason.weight) == (
        SignalStrength.MEDIUM,
        Decimal("-2"),
    )
    assert (high_reason.strength, high_reason.weight) == (
        SignalStrength.HIGH,
        Decimal("-4"),
    )


def test_real_partial_failed_and_status_conflict_paths_have_exact_warnings():
    arbitration_missing = score_signals(
        evaluate_signals(
            complete_company_report(arbitration=arbitration_facts(is_complete=False))
        )
    )
    assert arbitration_missing.level is ScoringLevel.MEDIUM
    assert arbitration_missing.score_points is not None
    assert arbitration_missing.confidence.value == Decimal("0.6923")

    failed_input = evaluate_signals(
        company_report(counterparty_status=DatasetReportStatus.DISABLED)
    )
    failed = score_signals(failed_input)
    source_warnings = [
        warning
        for warning in failed.warnings
        if warning.code is ScoringWarningCode.SOURCE_RULE_SUPPRESSED
    ]
    insufficient = next(
        warning
        for warning in failed.warnings
        if warning.code is ScoringWarningCode.INSUFFICIENT_DATA
    )
    assert failed.level is ScoringLevel.INSUFFICIENT_DATA
    assert failed.score_points is None
    assert failed.confidence.value == Decimal("0.0000")
    assert len(source_warnings) == 13
    assert [warning.rule_code for warning in source_warnings] == sorted(
        SCORING_RULE_REGISTRY
    )
    assert all(
        warning.source_warning_codes == ["dataset_unavailable"]
        and warning.signal_codes == []
        and warning.message == "A source signal rule was not evaluable."
        for warning in source_warnings
    )
    assert insufficient.source_warning_codes == ["dataset_unavailable"]
    assert insufficient.signal_codes == []
    assert insufficient.message == "Available evidence is insufficient for a scoring level."

    conflict = score_signals(
        evaluate_signals(
            complete_company_report(
                counterparty=counterparty_facts(dissolved_date=date(2025, 1, 1))
            )
        )
    )
    status = next(
        warning
        for warning in conflict.warnings
        if warning.code is ScoringWarningCode.STATUS_CONFLICT
    )
    insufficiency = next(
        warning
        for warning in conflict.warnings
        if warning.code is ScoringWarningCode.INSUFFICIENT_DATA
    )
    assert conflict.confidence.conflict_multiplier == Decimal("0.5")
    assert conflict.confidence.value == Decimal("0.4231")
    assert conflict.level is ScoringLevel.INSUFFICIENT_DATA
    assert status.source_warning_codes == ["status_conflict"]
    assert status.signal_codes == ["counterparty.status_conflict"]
    assert insufficiency.source_warning_codes == ["status_conflict"]
    assert insufficiency.signal_codes == ["counterparty.status_conflict"]
    assert len(
        [w for w in conflict.warnings if w.code is ScoringWarningCode.STATUS_CONFLICT]
    ) == 1
    assert status.message == "Counterparty status facts are conflicting."


def test_dissolved_suppression_and_invalid_source_contract_are_rejected():
    dissolved_suppressed = score_signals(
        _result(warnings=[_warning("counterparty.dissolved")])
    )
    assert dissolved_suppressed.level is ScoringLevel.INSUFFICIENT_DATA

    with pytest.raises(ValueError, match="both present and suppressed"):
        score_signals(
            _result(
                [_signal("finance.net_loss")],
                [_warning("finance.net_loss")],
            )
        )

    mismatch_dataset = _warning("finance.net_loss").model_copy(
        update={"dataset": "arbitration"}
    )
    with pytest.raises(ValueError, match="dataset"):
        score_signals(_result(warnings=[mismatch_dataset]))

    unknown_rule = _warning("finance.net_loss").model_copy(
        update={"rule_code": "finance.unknown"}
    )
    with pytest.raises(ValueError, match="not registered"):
        score_signals(_result(warnings=[unknown_rule]))
    with pytest.raises(ValueError, match="multiple result-level"):
        score_signals(
            _result(
                warnings=[
                    _warning("finance.net_loss"),
                    _warning("finance.net_loss", "required_period_unavailable"),
                ]
            )
        )


def test_unknown_or_mismatched_signal_contract_is_rejected():
    unknown = _signal("counterparty.active").model_copy(
        update={"code": "finance.reporting_absent"}
    )
    with pytest.raises(ValueError, match="not registered"):
        score_signals(_result([unknown]))

    mismatch = _signal("counterparty.active").model_copy(
        update={"category": SignalCategory.FINANCIAL}
    )
    with pytest.raises(ValueError, match="does not match"):
        score_signals(_result([mismatch]))

    wrong_direction = _signal("counterparty.active").model_copy(
        update={"direction": SignalDirection.NEGATIVE}
    )
    wrong_strength = _signal("counterparty.active").model_copy(
        update={"strength": SignalStrength.HIGH}
    )
    with pytest.raises(ValueError, match="does not match"):
        score_signals(_result([wrong_direction]))
    with pytest.raises(ValueError, match="does not match"):
        score_signals(_result([wrong_strength]))

    duplicate = _signal("counterparty.active")
    with pytest.raises(ValueError, match="unique"):
        score_signals(_result([duplicate, duplicate]))


def test_warning_permutation_and_public_input_immutability_and_privacy():
    report = company_report(counterparty_status=DatasetReportStatus.DISABLED)
    report_before = copy.deepcopy(report.model_dump(mode="json"))
    snapshot_before = company_report_to_snapshot(report)
    hash_before = calculate_company_report_snapshot_hash(report)
    evaluation = evaluate_signals(report)
    evaluation_before = copy.deepcopy(evaluation.model_dump(mode="json"))
    left = score_signals(evaluation)
    right = score_signals(
        _result(list(reversed(evaluation.signals)), list(reversed(evaluation.warnings)))
    )

    assert left.model_dump(mode="json") == right.model_dump(mode="json")
    assert report.model_dump(mode="json") == report_before
    assert company_report_to_snapshot(report) == snapshot_before
    assert calculate_company_report_snapshot_hash(report) == hash_before
    assert evaluation.model_dump(mode="json") == evaluation_before
    assert "raw_payload" not in str(left.model_dump(mode="json"))
