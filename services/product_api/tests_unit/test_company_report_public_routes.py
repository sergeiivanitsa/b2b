from datetime import date
from decimal import Decimal
import html
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from company_report_signal_test_helpers import (
    arbitration_facts,
    complete_company_report,
    counterparty_facts,
    finance_facts,
    finance_indicator,
)
from product_api.company_reports.models import (
    ArbitrationCaseFacts,
    ArbitrationParty,
    ArbitrationResultType,
    ArbitrationStatus,
    CompanyAddress,
    CounterpartyBlockStatus,
    FinanceForm,
)
from product_api.company_reports.persistence.serialization import calculate_company_report_snapshot_hash, company_report_to_snapshot
from product_api.company_reports.seo import canonical_path
from product_api.company_reports.public_h1 import (
    CompanyPublicH1Response,
    build_public_h1,
    render_public_h1_html,
)
from product_api.company_reports.public_h1_service import PublicH1NotEligibleError, PublicH1NotFoundError, PublicProjectionInvalidError
from product_api.company_reports.persistence.models import PUBLICATION_POLICY_VERSION
from product_api.db.session import get_session
from product_api.main import app
from product_api.routers import company_reports as api_routes
from product_api.routers import company_reports_public as public_routes
from product_api.company_reports.public_document_service import PublicDocumentKind, ResolvedPublicDocument


def _page():
    report = complete_company_report(counterparty=counterparty_facts().model_copy(update={"inn": "0000000000", "full_name": "ООО Тест"}), report_version="2")
    snapshot = company_report_to_snapshot(report)
    path = canonical_path("0000000000", "ООО Тест")
    digest = calculate_company_report_snapshot_hash(snapshot)
    subject = SimpleNamespace(id="subject", normalized_identifier="0000000000")
    record = SimpleNamespace(id=report.report_id, subject_id=subject.id, report_version="2", lifecycle_status="complete", normalized_snapshot=snapshot, snapshot_hash=digest, generated_at=report.generated_at)
    return SimpleNamespace(
        publication=SimpleNamespace(status="active", subject_id=subject.id, report_id=record.id, policy_version=PUBLICATION_POLICY_VERSION, sufficiency_status="sufficient", indexable=True, canonical_slug=path[len("/company/0000000000-"):], canonical_path=path, snapshot_hash=digest, published_lastmod=report.generated_at),
        report=record,
        subject=subject,
    )


def _rich_partial_dto() -> CompanyPublicH1Response:
    counterparty = counterparty_facts().model_copy(
        update={
            "inn": "0000000000",
            "ogrn": "0000000000000",
            "kpp": "000000000",
            "full_name": "ООО <script>alert&unsafe</script>",
            "short_name": "ООО <Short & Co>",
            "registration_date": date(2020, 2, 3),
            "dissolved_date": date(2025, 4, 5),
            "address": CompanyAddress(
                line_address='123456, <Address & "quoted">',
                zip_code="123456",
                country="Россия & РФ",
                region="Регион <R>",
                region_code="77",
                city="Город & City",
                street='Улица "Тест"',
                house="Дом <1>",
                office="Офис '2'",
                is_inaccuracy=False,
            ),
            "block_statuses": {"address": CounterpartyBlockStatus.AVAILABLE},
        }
    )
    finance = finance_facts(
        indicators=[
            finance_indicator(
                FinanceForm.FINANCIAL_RESULTS,
                "2110",
                values_by_year={2024: Decimal("80"), 2025: Decimal("100")},
            )
        ]
    )
    selected = ArbitrationCaseFacts(
        case_number='CASE-<&"\'',
        date_start=date(2024, 1, 2),
        date_update=date(2025, 3, 4),
        claim_amount=Decimal("10.5"),
        currency="RUB",
        normalized_status=ArbitrationStatus.OPEN,
        normalized_result_type=ArbitrationResultType.SATISFIED_FULL,
        plaintiffs=[ArbitrationParty(inn="0000000000", ogrn="0000000000000")],
    )
    internal_only = ArbitrationCaseFacts(
        internal_id="private-internal-id",
        claim_amount=Decimal("2.25"),
        currency="RUB",
        normalized_status=ArbitrationStatus.COMPLETED,
        normalized_result_type=ArbitrationResultType.REFUSED,
        respondents=[ArbitrationParty(inn="0000000000", ogrn="0000000000000")],
    )
    malformed = ArbitrationCaseFacts(
        case_number="MALFORMED",
        normalized_status=ArbitrationStatus.UNKNOWN,
        normalized_result_type=ArbitrationResultType.OTHER,
        party_collections_valid=False,
    )
    arbitration = arbitration_facts(
        [selected, internal_only, malformed], is_complete=False
    ).model_copy(
        update={"total_cases": 97, "returned_cases": 3, "limit": 3, "offset": 9}
    )
    report = complete_company_report(
        counterparty=counterparty,
        finance=finance,
        arbitration=arbitration,
        report_version="2",
    )
    dto = build_public_h1(
        report,
        projection_scope="published",
        persisted_canonical_path="/company/0000000000-escaped-company",
        persisted_indexable=True,
    )
    payload = dto.model_dump(mode="python")
    for index, source in enumerate(payload["sources"]):
        source["effective_at"] = date(2025, 1, index + 1)
        source["period"] = f'2025 <period & "{index}">'
    return CompanyPublicH1Response.model_validate(payload)


def _leaf_items(value, prefix=""):
    if value is None:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaf_items(child, f"{prefix}.{key}" if prefix else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _leaf_items(child, f"{prefix}.{index}")
    else:
        yield prefix, value


def _html_scalar(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def test_public_page_serves_ssr_and_rejects_query_without_writes(monkeypatch):
    page = _page()

    report = complete_company_report(counterparty=counterparty_facts().model_copy(update={"inn": "0000000000", "full_name": "ООО Тест"}))
    dto = build_public_h1(report, projection_scope="published", persisted_canonical_path=page.publication.canonical_path, persisted_indexable=True)

    async def fake_resolve(*_args, **_kwargs):
        return ResolvedPublicDocument(PublicDocumentKind.H1, dto, False)

    async def fake_session():
        yield object()

    monkeypatch.setattr(public_routes, "resolve_public_document", fake_resolve)
    app.dependency_overrides[get_session] = fake_session
    try:
        with TestClient(app) as client:
            response = client.get("/company/0000000000-ooo-test")
            assert response.status_code == 200
            assert response.headers["x-robots-tag"] == "index,follow"
            assert "<script" not in response.text
            for section in ("Реквизиты", "Арбитраж", "Покрытие", "Источники", "Ограничения"):
                assert section in response.text
            assert client.get("/company/0000000000-ooo-test?x=1").status_code == 422
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_direct_launch_ssr_renders_staged_h2_without_assignment(monkeypatch):
    dto = SimpleNamespace(
        canonical_path="/company/0000000000-direct-h2",
        indexable=False,
    )
    calls = []

    async def fake_h2_resolve(_session, *, inn, rollout_generation):
        calls.append(inn)
        assert rollout_generation == 7
        return dto

    async def forbidden_assignment_resolver(*_args, **_kwargs):
        raise AssertionError("direct H2 must not require a public assignment")

    async def fake_session():
        yield object()

    monkeypatch.setattr(
        public_routes,
        "get_settings",
        lambda: SimpleNamespace(
            company_card_v2_direct_launch_enabled=True,
            company_card_v2_rollout_generation=7,
        ),
    )
    monkeypatch.setattr(
        public_routes,
        "resolve_direct_public_h2",
        fake_h2_resolve,
    )
    monkeypatch.setattr(
        public_routes,
        "resolve_public_document",
        forbidden_assignment_resolver,
    )
    monkeypatch.setattr(public_routes, "_public_h2_asset_manifest", lambda: object())
    monkeypatch.setattr(
        public_routes,
        "render_public_h2_document",
        lambda resolved, _manifest, _nonce, _robots: (
            "<html><body>direct-h2</body></html>"
            if resolved is dto
            else (_ for _ in ()).throw(AssertionError("wrong DTO"))
        ),
    )
    monkeypatch.setattr(
        public_routes,
        "public_h2_security_headers",
        lambda _nonce, robots: {
            "Cache-Control": "no-store",
            "X-Robots-Tag": robots,
        },
    )
    app.dependency_overrides[get_session] = fake_session
    try:
        with TestClient(app) as client:
            response = client.get(dto.canonical_path)
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.text == "<html><body>direct-h2</body></html>"
    assert response.headers["x-robots-tag"] == "noindex,follow"
    assert calls == ["0000000000"]


def test_direct_launch_pending_plain_path_remains_spa_fallback(monkeypatch):
    async def pending(*_args, **_kwargs):
        raise public_routes.PublicH2Pending("report_pending")

    async def fake_session():
        yield object()

    monkeypatch.setattr(
        public_routes,
        "get_settings",
        lambda: SimpleNamespace(
            company_card_v2_direct_launch_enabled=True,
            company_card_v2_rollout_generation=7,
        ),
    )
    monkeypatch.setattr(public_routes, "resolve_direct_public_h2", pending)
    app.dependency_overrides[get_session] = fake_session
    try:
        with TestClient(app) as client:
            response = client.get("/company/0000000000")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 404
    assert response.headers["x-robots-tag"] == "noindex,follow"


@pytest.mark.parametrize(
    "failure",
    [
        public_routes.PublicH2NotFound("company card v2 was not found"),
        public_routes.PublicH2Pending("report_pending"),
    ],
)
def test_direct_launch_old_canonical_slug_redirects_to_plain_spa_boundary(
    monkeypatch,
    failure,
):
    async def unavailable(*_args, **_kwargs):
        raise failure

    async def fake_session():
        yield object()

    monkeypatch.setattr(
        public_routes,
        "get_settings",
        lambda: SimpleNamespace(
            company_card_v2_direct_launch_enabled=True,
            company_card_v2_rollout_generation=7,
        ),
    )
    monkeypatch.setattr(public_routes, "resolve_direct_public_h2", unavailable)
    app.dependency_overrides[get_session] = fake_session
    try:
        with TestClient(app, follow_redirects=False) as client:
            response = client.get("/company/0000000000-old-h1-slug")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 302
    assert response.headers["location"] == "/company/0000000000"
    assert response.headers["x-robots-tag"] == "noindex,follow"
    assert response.headers["cache-control"] == "no-store"


def test_api_and_ssr_have_complete_deterministic_escaped_partial_dto_parity(
    monkeypatch,
):
    dto = _rich_partial_dto()

    async def fake_resolve(*_args, **_kwargs):
        return ResolvedPublicDocument(PublicDocumentKind.H1, dto, False)

    async def fake_h1_resolve(*_args, **_kwargs):
        return dto

    async def fake_session():
        yield object()

    monkeypatch.setattr(api_routes, "resolve_public_h1", fake_h1_resolve)
    monkeypatch.setattr(public_routes, "resolve_public_document", fake_resolve)
    monkeypatch.setattr(
        api_routes, "_enforce_report_rate_limit", lambda *_args, **_kwargs: None
    )
    app.dependency_overrides[get_session] = fake_session
    try:
        with TestClient(app) as client:
            api_response = client.get("/company-reports/0000000000/public-h1")
            ssr_response = client.get(dto.canonical_path)
    finally:
        app.dependency_overrides.pop(get_session, None)

    expected_json = dto.model_dump(mode="json")
    expected_html = render_public_h1_html(dto)
    assert api_response.status_code == ssr_response.status_code == 200
    assert api_response.json() == expected_json
    assert ssr_response.text == expected_html
    assert render_public_h1_html(dto) == expected_html
    assert ssr_response.headers["x-robots-tag"] == "index,follow"

    root_attributes = {
        "contract-version": dto.contract_version,
        "report-id": str(dto.report_id),
        "report-version": dto.report_version,
        "projection-scope": dto.projection_scope,
        "canonical-path": dto.canonical_path,
        "indexable": "true",
        "block-order": ",".join(dto.block_order),
    }
    for name, value in root_attributes.items():
        assert f'data-{name}="{html.escape(value, quote=True)}"' in expected_html

    parity_surfaces = {
        "identity": expected_json["identity"],
        "requisites": expected_json["blocks"]["requisites"],
        "finance": expected_json["blocks"]["finance"],
        "arbitration": expected_json["blocks"]["arbitration"],
        "coverage": expected_json["coverage"],
        "sources": expected_json["sources"],
        "limitations": expected_json["limitations"],
        "actions": expected_json["actions"],
        "breadcrumbs": expected_json["breadcrumbs"],
    }
    parity_surfaces.update(
        {
            "": {
                "checked_at": expected_json["checked_at"],
                "checked_date": expected_json["checked_date"],
                "checked_date_display": expected_json["checked_date_display"],
            }
        }
    )
    for prefix, surface in parity_surfaces.items():
        for field, value in _leaf_items(surface, prefix):
            escaped_field = html.escape(field, quote=True)
            escaped_value = html.escape(_html_scalar(value), quote=True)
            expected_item = (
                f'<li data-field="{escaped_field}"><span class="field-label">'
                f'{html.escape(field)}</span>: <span class="field-value">'
                f"{escaped_value}</span></li>"
            )
            assert expected_item in expected_html

    ordered_dom_ids = {
        "breadcrumbs": "breadcrumbs",
        "identity_status": "identity-status",
        "known_summary": "known-summary",
        "in_page_navigation": "in-page-navigation",
        "coverage_checked_at": "coverage-checked-at",
        "requisites": "requisites",
        "finance": "finance",
        "arbitration": "arbitration",
        "sources_limitations": "sources-limitations",
        "neutral_actions": "neutral-actions",
    }
    positions = [
        expected_html.index(f'id="{ordered_dom_ids[block_id]}"')
        for block_id in dto.block_order
    ]
    assert positions == sorted(positions)

    arbitration = expected_json["blocks"]["arbitration"]
    assert {
        key: arbitration[key]
        for key in (
            "total_cases",
            "returned_cases",
            "normalized_case_count",
            "malformed_count",
            "limit",
            "offset",
        )
    } == {
        "total_cases": 97,
        "returned_cases": 3,
        "normalized_case_count": 2,
        "malformed_count": 1,
        "limit": 3,
        "offset": 9,
    }
    arbitration_coverage = next(
        item for item in expected_json["coverage"] if item["block_id"] == "arbitration"
    )
    assert arbitration_coverage["state"] == "partial"
    assert {
        key: arbitration_coverage[key]
        for key in ("total", "returned", "limit", "offset")
    } == {"total": 97, "returned": 3, "limit": 3, "offset": 9}
    assert {
        "arbitration_partial_slice",
        "arbitration_malformed_records",
    } <= set(arbitration_coverage["limitation_codes"])
    assert len(arbitration["selected_cases"]) == 1
    assert len(arbitration["claim_amounts"]) == 2

    for raw_value in (
        "ООО <script>alert&unsafe</script>",
        '123456, <Address & "quoted">',
        'CASE-<&"\'',
        '2025 <period & "0">',
        "private-internal-id",
    ):
        assert raw_value not in expected_html
    assert "<script" not in expected_html.lower()
    assert "&lt;script&gt;alert&amp;unsafe&lt;/script&gt;" in expected_html
    assert "CASE-&lt;&amp;&quot;&#x27;" in expected_html
    for forbidden in ("raw_payload", "provider_status_code", "snapshot_hash"):
        assert forbidden not in expected_html


def test_sitemap_predicate_uses_complete_shared_pin_validator(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("sitemap must not evaluate publication, signals or scoring")
    monkeypatch.setattr("product_api.company_reports.seo.evaluate_publication", forbidden)
    monkeypatch.setattr("product_api.company_reports.ephemeral_evaluation.evaluate_report_ephemerally", forbidden)
    page = _page()
    assert public_routes._current_public_projection(page) is not None
    page.report.subject_id = "other"
    assert public_routes._current_public_projection(page) is None


def test_sitemap_overlong_numeric_chunk_is_stable_404_without_scan(monkeypatch):
    async def forbidden_scan(*_args, **_kwargs):
        raise AssertionError("an overlong chunk must be rejected before scanning")

    async def fake_session():
        yield object()

    monkeypatch.setattr(public_routes, "scan_public_sitemap", forbidden_scan)
    app.dependency_overrides[get_session] = fake_session
    try:
        with TestClient(app) as client:
            response = client.get(f"/sitemaps/{'9' * 5000}.xml")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 404
    assert response.headers["x-robots-tag"] == "noindex,follow"


@pytest.mark.parametrize("error", [PublicH1NotFoundError(), PublicH1NotEligibleError()])
def test_ssr_unpublished_states_are_404_but_invalid_active_is_500(monkeypatch, error):
    async def fail(*_args, **_kwargs):
        raise error
    async def fake_session():
        yield object()
    monkeypatch.setattr(public_routes, "resolve_public_document", fail)
    app.dependency_overrides[get_session] = fake_session
    try:
        with TestClient(app) as client:
            assert client.get("/company/0000000000-ooo-test").status_code == 404
    finally:
        app.dependency_overrides.pop(get_session, None)

    async def invalid(*_args, **_kwargs):
        raise PublicProjectionInvalidError()
    monkeypatch.setattr(public_routes, "resolve_public_document", invalid)
    app.dependency_overrides[get_session] = fake_session
    try:
        with TestClient(app) as client:
            assert client.get("/company/0000000000-ooo-test").status_code == 500
    finally:
        app.dependency_overrides.pop(get_session, None)
