from __future__ import annotations

from product_api.company_reports.aggregate import CompanyReport

from .arbitration import _evaluate_arbitration_signals
from .counterparty import _evaluate_counterparty_signals
from .finance import _evaluate_finance_signals
from .models import SignalEvaluationResult


def evaluate_signals(report: CompanyReport) -> SignalEvaluationResult:
    """Compose all ruleset v1 signal evaluators for a normalized report."""

    counterparty_result = _evaluate_counterparty_signals(report)
    finance_result = _evaluate_finance_signals(report)
    arbitration_result = _evaluate_arbitration_signals(report)
    results = (
        counterparty_result,
        finance_result,
        arbitration_result,
    )

    if any(result.ruleset_version != "1" for result in results):
        raise ValueError("internal signal evaluator returned an incompatible ruleset")

    return SignalEvaluationResult(
        ruleset_version="1",
        signals=[
            signal
            for result in results
            for signal in result.signals
        ],
        warnings=[
            warning
            for result in results
            for warning in result.warnings
        ],
    )


__all__ = ["evaluate_signals"]
