from company_report_signal_test_helpers import complete_company_report, counterparty_facts, finance_facts
from product_api.company_reports.seo import canonical_path, evaluate_publication, render_html


def _report():
    counterparty = counterparty_facts().model_copy(update={"inn": "0000000000", "full_name": "ООО Тест и партнёры"})
    return complete_company_report(counterparty=counterparty)


def test_eligible_projection_is_deterministic_and_has_no_spa_or_internal_data():
    report = _report()
    decision = evaluate_publication(report)
    assert decision.indexable is True
    assert decision.projection is not None
    page = render_html(decision.projection, base_url="https://pork.su", robots="index,follow")
    assert "ООО Тест" in page
    assert "100" in page
    assert "raw_payload" not in page
    assert "request_id" not in page
    assert "application/ld+json" not in page
    assert "<script" not in page
    assert canonical_path("0000000000", "ООО Тест и партнёры") == "/company/0000000000-ooo-test-i-partnery"


def test_thin_report_is_not_indexable():
    report = _report().model_copy(update={"finance": finance_facts([]), "arbitration": None})
    assert evaluate_publication(report).indexable is False
