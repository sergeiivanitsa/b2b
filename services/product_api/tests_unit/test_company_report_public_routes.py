from types import SimpleNamespace

from fastapi.testclient import TestClient

from company_report_signal_test_helpers import complete_company_report, counterparty_facts
from product_api.company_reports.persistence.serialization import calculate_company_report_snapshot_hash, company_report_to_snapshot
from product_api.company_reports.seo import canonical_path
from product_api.db.session import get_session
from product_api.main import app
from product_api.routers import company_reports_public as public_routes


def _page():
    report = complete_company_report(counterparty=counterparty_facts().model_copy(update={"inn": "0000000000", "full_name": "ООО Тест"}))
    snapshot = company_report_to_snapshot(report)
    path = canonical_path("0000000000", "ООО Тест")
    return SimpleNamespace(
        publication=SimpleNamespace(status="active", indexable=True, canonical_slug="ooo-test", canonical_path=path, snapshot_hash=calculate_company_report_snapshot_hash(snapshot), published_lastmod=report.generated_at),
        report=SimpleNamespace(lifecycle_status="complete", normalized_snapshot=snapshot, snapshot_hash=calculate_company_report_snapshot_hash(snapshot)),
    )


def test_public_page_serves_ssr_and_rejects_query_without_writes(monkeypatch):
    page = _page()

    async def fake_page(*_args, **_kwargs):
        return page

    async def fake_session():
        yield object()

    monkeypatch.setattr(public_routes, "get_public_page", fake_page)
    app.dependency_overrides[get_session] = fake_session
    try:
        with TestClient(app) as client:
            response = client.get("/company/0000000000-ooo-test")
            assert response.status_code == 200
            assert response.headers["x-robots-tag"] == "index,follow"
            assert "<script" not in response.text
            assert client.get("/company/0000000000-ooo-test?x=1").status_code == 404
    finally:
        app.dependency_overrides.pop(get_session, None)
