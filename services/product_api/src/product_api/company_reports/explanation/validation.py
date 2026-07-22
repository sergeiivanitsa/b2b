from __future__ import annotations

from decimal import Decimal

from product_api.company_reports.aggregate import CompanyReport
from product_api.company_reports.scoring.models import ScoringResult
from product_api.company_reports.signals.models import SignalEvaluationResult

from .catalog import build_allowed_statement_catalog
from .models import (
    AIExplanation,
    AllowedStatementCatalog,
    ExplanationDatasetStatus,
    ExplanationInputEnvelope,
    ExplanationScoring,
    ExplanationSelection,
    ExplanationSignal,
)
from .prompt import canonical_json


class ExplanationValidationError(ValueError):
    pass


_SIGNAL_DATASET_BY_PREFIX = {
    "counterparty": "counterparty",
    "finance": "finance",
    "arbitration": "arbitration",
}


def _dataset_for_rule_code(rule_code: str) -> str:
    prefix, separator, _ = rule_code.partition(".")
    if not separator or prefix not in _SIGNAL_DATASET_BY_PREFIX:
        raise ExplanationValidationError("signal or warning rule code has no known dataset")
    return _SIGNAL_DATASET_BY_PREFIX[prefix]


def validate_consistent_evaluation(
    report: CompanyReport,
    signal_evaluation: SignalEvaluationResult,
    scoring: ScoringResult,
) -> None:
    """Reject mixed snapshots before any allowlisted prompt is constructed."""

    if scoring.signal_ruleset_version != signal_evaluation.ruleset_version:
        raise ExplanationValidationError("signal and scoring ruleset versions do not match")

    signal_codes = {signal.code for signal in signal_evaluation.signals}
    reason_codes = {reason.signal_code for reason in scoring.reasons}
    if reason_codes != signal_codes:
        raise ExplanationValidationError("scoring reasons do not match current signals")

    suppressed_codes = {
        code
        for breakdown in scoring.domain_breakdown
        for code in breakdown.suppressed_rule_codes
    }
    warning_rule_codes = {warning.rule_code for warning in signal_evaluation.warnings}
    if suppressed_codes != warning_rule_codes:
        raise ExplanationValidationError("scoring suppressions do not match signal warnings")

    dataset_statuses = {
        name: dataset.status.value for name, dataset in report.datasets.items()
    }
    for signal in signal_evaluation.signals:
        dataset = _dataset_for_rule_code(signal.code)
        if dataset_statuses.get(dataset) != "available":
            raise ExplanationValidationError("signal has no available matching report dataset")
    for warning in signal_evaluation.warnings:
        dataset = warning.dataset
        if dataset is None or dataset not in dataset_statuses:
            raise ExplanationValidationError("signal warning has no matching report dataset")
        if _dataset_for_rule_code(warning.rule_code or "") != dataset:
            raise ExplanationValidationError("signal warning rule code does not match its dataset")
        is_available = dataset_statuses[dataset] == "available"
        if warning.code == "dataset_unavailable":
            if is_available:
                raise ExplanationValidationError("dataset unavailable warning has available report data")
        elif not is_available:
            raise ExplanationValidationError("dataset-specific warning has unavailable report data")


def build_input_envelope(
    report: CompanyReport,
    signal_evaluation: SignalEvaluationResult,
    scoring: ScoringResult,
) -> ExplanationInputEnvelope:
    validate_consistent_evaluation(report, signal_evaluation, scoring)
    catalog = build_allowed_statement_catalog(report, signal_evaluation, scoring)
    return ExplanationInputEnvelope(
        report_version=report.report_version,
        report_status=report.status.value,
        completeness={
            "available_count": report.completeness.available_count,
            "required_count": report.completeness.required_count,
            "ratio": str(report.completeness.ratio),
            "percent": report.completeness.percent,
            "identity_available": report.completeness.identity_available,
            "financial_data_available": report.completeness.financial_data_available,
            "arbitration_data_available": report.completeness.arbitration_data_available,
        },
        dataset_statuses=[
            ExplanationDatasetStatus(dataset=name, status=dataset.status.value)
            for name, dataset in sorted(report.datasets.items())
        ],
        report_warning_codes=sorted({warning.code for warning in report.warnings}),
        signals=[
            ExplanationSignal(
                code=signal.code,
                category=signal.category.value,
                direction=signal.direction.value,
                strength=signal.strength.value,
                confidence=signal.confidence.value,
            )
            for signal in signal_evaluation.signals
        ],
        signal_warning_codes=sorted({warning.code for warning in signal_evaluation.warnings}),
        scoring=ExplanationScoring(
            ruleset_version=scoring.ruleset_version,
            level=scoring.level.value,
            score_points=(str(scoring.score_points) if scoring.score_points is not None else None),
            confidence=str(scoring.confidence.value),
            reason_signal_codes=sorted(reason.signal_code for reason in scoring.reasons),
            warning_codes=sorted({warning.code.value for warning in scoring.warnings}),
        ),
        allowed_statement_catalog=catalog,
    )


def validate_input_budget(envelope: ExplanationInputEnvelope, max_input_tokens: int) -> None:
    if max_input_tokens <= 0:
        raise ExplanationValidationError("input budget must be positive")
    if len(canonical_json(envelope.model_dump(mode="json")).encode("utf-8")) > max_input_tokens:
        raise ExplanationValidationError("canonical envelope exceeds input budget")


def parse_selection(text: str) -> ExplanationSelection:
    try:
        return ExplanationSelection.model_validate_json(text)
    except ValueError as exc:
        raise ExplanationValidationError("model response is not a valid explanation selection") from exc


def _statements_by_id(statements: list) -> dict[str, str]:
    return {statement.id: statement.text for statement in statements}


def render_selection(
    selection: ExplanationSelection,
    catalog: AllowedStatementCatalog,
    *,
    prompt_version: str,
    model_profile: str,
    resolved_model: str,
    attempt_count: int,
) -> AIExplanation:
    sections = {
        "overall_conclusion_id": _statements_by_id(catalog.overall_conclusions),
        "recovery_factor_ids": _statements_by_id(catalog.recovery_factors),
        "key_risk_ids": _statements_by_id(catalog.key_risks),
        "urgency_id": _statements_by_id(catalog.urgencies),
        "recommended_next_step_id": _statements_by_id(catalog.recommended_next_steps),
        "limitation_ids": _statements_by_id(catalog.limitations),
    }
    selected = selection.model_dump()
    for field_name, choices in sections.items():
        identifiers = selected[field_name]
        identifiers = identifiers if isinstance(identifiers, list) else [identifiers]
        if any(identifier not in choices for identifier in identifiers):
            raise ExplanationValidationError("selection includes an ungrounded statement id")
    return AIExplanation(
        output_schema_version=selection.output_schema_version,
        overall_conclusion=sections["overall_conclusion_id"][selection.overall_conclusion_id],
        recovery_factors=[sections["recovery_factor_ids"][identifier] for identifier in selection.recovery_factor_ids],
        key_risks=[sections["key_risk_ids"][identifier] for identifier in selection.key_risk_ids],
        urgency=sections["urgency_id"][selection.urgency_id],
        recommended_next_step=sections["recommended_next_step_id"][selection.recommended_next_step_id],
        limitations=[sections["limitation_ids"][identifier] for identifier in selection.limitation_ids],
        prompt_version=prompt_version,
        model_profile=model_profile,
        resolved_model=resolved_model,
        attempt_count=attempt_count,
    )
