from __future__ import annotations

from product_api.company_reports.aggregate import CompanyReport
from product_api.company_reports.scoring import ScoringResult, score_signals
from product_api.company_reports.signals import (
    SignalEvaluationResult,
    evaluate_signals,
)


def evaluate_report_ephemerally(
    report: CompanyReport,
) -> tuple[SignalEvaluationResult, ScoringResult]:
    signals = evaluate_signals(report)
    return signals, score_signals(signals)


__all__ = ["evaluate_report_ephemerally"]
