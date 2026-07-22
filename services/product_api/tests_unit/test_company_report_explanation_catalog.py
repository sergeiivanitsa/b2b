from product_api.company_reports.explanation.catalog import build_allowed_statement_catalog
from product_api.company_reports.scoring import score_signals
from product_api.company_reports.signals import evaluate_signals

from company_report_signal_test_helpers import complete_company_report


def test_catalog_is_deterministic_and_only_uses_current_signal_codes():
    report = complete_company_report()
    signals = evaluate_signals(report)
    scoring = score_signals(signals)

    first = build_allowed_statement_catalog(report, signals, scoring)
    second = build_allowed_statement_catalog(report, signals, scoring)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    catalog_text = str(first.model_dump())
    assert report.target_identifier not in catalog_text
    assert all(signal.code in catalog_text for signal in signals.signals if signal.direction.value != "informational")
