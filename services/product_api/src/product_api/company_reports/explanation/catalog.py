from __future__ import annotations

from product_api.company_reports.aggregate import CompanyReport
from product_api.company_reports.scoring.models import ScoringResult
from product_api.company_reports.signals.models import SignalDirection, SignalEvaluationResult

from .models import AllowedStatementCatalog, CatalogStatement


def _statement(identifier: str, text: str) -> CatalogStatement:
    return CatalogStatement(id=identifier, text=text)


def build_allowed_statement_catalog(
    report: CompanyReport,
    signal_evaluation: SignalEvaluationResult,
    scoring: ScoringResult,
) -> AllowedStatementCatalog:
    """Build a deterministic catalog whose every entry is grounded in current inputs."""

    level = scoring.level.value
    overall = [_statement(f"overall_level_{level}", f"Scoring level: {level}.")]
    urgency = [_statement(f"urgency_level_{level}", f"Scoring level: {level}.")]
    next_steps = [
        _statement(
            "next_step_review_available_evidence",
            "Review the available report and scoring evidence.",
        )
    ]
    factors = [
        _statement(f"factor_signal_{signal.code}", f"Positive signal recorded: {signal.code}.")
        for signal in signal_evaluation.signals
        if signal.direction is SignalDirection.POSITIVE
    ]
    risks = [
        _statement(f"risk_signal_{signal.code}", f"Negative signal recorded: {signal.code}.")
        for signal in signal_evaluation.signals
        if signal.direction is SignalDirection.NEGATIVE
    ]
    limitations: list[CatalogStatement] = []
    if report.status.value != "complete":
        limitations.append(
            _statement(
                f"limitation_report_status_{report.status.value}",
                f"Report status: {report.status.value}.",
            )
        )
    for dataset, item in sorted(report.datasets.items()):
        if item.status.value != "available":
            limitations.append(
                _statement(
                    f"limitation_dataset_{dataset}_{item.status.value}",
                    f"Dataset status for {dataset}: {item.status.value}.",
                )
            )
    for code in sorted({warning.code for warning in report.warnings}):
        limitations.append(_statement(f"limitation_report_warning_{code}", f"Report warning: {code}."))
    for code in sorted({warning.code for warning in signal_evaluation.warnings}):
        limitations.append(_statement(f"limitation_signal_warning_{code}", f"Signal warning: {code}."))
    for warning in scoring.warnings:
        limitations.append(
            _statement(
                f"limitation_scoring_warning_{warning.code.value}",
                f"Scoring warning: {warning.code.value}.",
            )
        )
    return AllowedStatementCatalog(
        overall_conclusions=overall,
        recovery_factors=sorted(factors, key=lambda item: item.id),
        key_risks=sorted(risks, key=lambda item: item.id),
        urgencies=urgency,
        recommended_next_steps=next_steps,
        limitations=sorted({item.id: item for item in limitations}.values(), key=lambda item: item.id),
    )
