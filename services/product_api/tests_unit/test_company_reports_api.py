from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from company_report_signal_test_helpers import complete_company_report, counterparty_facts
from product_api.company_reports.public_h1 import build_public_h1
from product_api.company_reports.public_h1_service import (
    PublicH1FailedError,
    PublicH1NotEligibleError,
    PublicH1NotFoundError,
    PublicH1PendingError,
    PublicH1UnavailableError,
    PublicProjectionInvalidError,
)

from product_api.company_reports.schemas import (
    CompanyReportAcceptedResponse,
    CompanyReportResponse,
    CompanyReportStatusResponse,
)
from product_api.company_reports.service import (
    InvalidCompanyReportIdentifierError,
)
from product_api.routers import company_reports as company_reports_router

pytestmark = pytest.mark.asyncio


async def test_post_returns_202_and_is_strict(async_client, monkeypatch):
    report_id = uuid4()

    async def fake_create(_session, *, inn):
        assert inn == "7700000000"
        return CompanyReportAcceptedResponse(
            report_id=report_id,
            status="pending",
            reused=False,
        )

    monkeypatch.setattr(
        company_reports_router,
        "create_or_reuse_company_report",
        fake_create,
    )
    response = await async_client.post(
        "/company-reports",
        json={"inn": "7700000000"},
    )
    invalid = await async_client.post(
        "/company-reports",
        json={"inn": "7700000000", "provider": "private"},
    )

    assert response.status_code == 202
    assert response.json() == {
        "report_id": str(report_id),
        "status": "pending",
        "reused": False,
    }
    assert invalid.status_code == 422


async def test_typed_error_mapping_is_safe(async_client, monkeypatch):
    async def fake_create(_session, *, inn):
        raise InvalidCompanyReportIdentifierError()

    monkeypatch.setattr(
        company_reports_router,
        "create_or_reuse_company_report",
        fake_create,
    )
    response = await async_client.post(
        "/company-reports",
        json={"inn": "7700000000000"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {"code": "invalid_inn", "message": "invalid INN"}
    }


async def test_public_status_has_no_query_surface(
    async_client,
    monkeypatch,
):
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)

    async def fake_status(_session, *, inn):
        return CompanyReportStatusResponse(
            report_id=uuid4(),
            status="pending",
            started_at=now,
        )

    monkeypatch.setattr(
        company_reports_router,
        "get_company_report_status",
        fake_status,
    )
    response = await async_client.get(
        "/company-reports/7700000000/status",
    )
    invalid = await async_client.get(
        "/company-reports/7700000000/status?extra=value",
    )

    assert response.status_code == 200
    assert invalid.status_code == 422


def _assert_h1_headers(response):
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-robots-tag"] == "noindex,follow"


async def test_public_h1_success_is_anonymous_strict_and_side_effect_free(async_client, monkeypatch):
    report = complete_company_report(counterparty=counterparty_facts().model_copy(update={"inn": "0000000000", "full_name": "ООО Тест"}), report_version="2")
    dto = build_public_h1(report, projection_scope="latest_unpublished")
    calls = 0

    async def resolve(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return dto

    monkeypatch.setattr(company_reports_router, "resolve_public_h1", resolve)
    monkeypatch.setattr(company_reports_router, "_enforce_report_rate_limit", lambda *_args, **_kwargs: None)
    response = await async_client.get("/company-reports/0000000000/public-h1", headers={"Authorization": "Bearer ignored"})
    assert response.status_code == 200
    assert response.json()["contract_version"] == "company_public_h1_v1"
    _assert_h1_headers(response)
    assert calls == 1


async def test_public_h1_rejects_every_query_in_fastapi_form_before_service(async_client, monkeypatch):
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("resolver must not be called")

    monkeypatch.setattr(company_reports_router, "resolve_public_h1", forbidden)
    response = await async_client.get("/company-reports/7700000000/public-h1?a=1&a=2&blank=")
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], list)
    assert [item["loc"] for item in body["detail"]] == [["query", "a"], ["query", "a"], ["query", "blank"]]
    _assert_h1_headers(response)


@pytest.mark.parametrize(
    ("error", "status_code", "code", "message"),
    [
        (PublicH1NotFoundError(), 404, "company_report_not_found", "company report not found"),
        (PublicH1PendingError(), 409, "report_pending", "company report is pending"),
        (PublicH1FailedError(), 409, "report_failed", "company report failed"),
        (PublicH1NotEligibleError(), 409, "report_not_eligible", "company report is not eligible for public projection"),
        (PublicProjectionInvalidError(), 500, "public_projection_invalid", "public company projection is invalid"),
        (PublicH1UnavailableError(), 503, "company_report_unavailable", "company report service is unavailable"),
    ],
)
async def test_public_h1_exact_typed_errors_and_headers(async_client, monkeypatch, error, status_code, code, message):
    async def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(company_reports_router, "resolve_public_h1", fail)
    monkeypatch.setattr(company_reports_router, "_enforce_report_rate_limit", lambda *_args, **_kwargs: None)
    response = await async_client.get("/company-reports/7700000000/public-h1")
    assert response.status_code == status_code
    assert response.json() == {"detail": {"code": code, "message": message}}
    _assert_h1_headers(response)


async def test_public_h1_400_429_and_unexpected_500_have_shared_headers(async_client, monkeypatch):
    invalid = await async_client.get("/company-reports/770000000X/public-h1")
    assert invalid.status_code == 400
    assert invalid.json() == {"detail": {"code": "invalid_inn", "message": "invalid INN"}}
    _assert_h1_headers(invalid)

    def limited(*_args, **_kwargs):
        raise HTTPException(status_code=429)

    monkeypatch.setattr(company_reports_router, "_enforce_report_rate_limit", limited)
    limited_response = await async_client.get("/company-reports/7700000000/public-h1")
    assert limited_response.status_code == 429
    assert limited_response.json() == {"detail": {"code": "rate_limited", "message": "rate limit"}}
    _assert_h1_headers(limited_response)

    monkeypatch.setattr(company_reports_router, "_enforce_report_rate_limit", lambda *_args, **_kwargs: None)
    async def unexpected(*_args, **_kwargs):
        raise RuntimeError("private database detail")
    monkeypatch.setattr(company_reports_router, "resolve_public_h1", unexpected)
    failed = await async_client.get("/company-reports/7700000000/public-h1")
    assert failed.status_code == 500
    assert failed.json() == {"detail": {"code": "public_projection_invalid", "message": "public company projection is invalid"}}
    assert "private database detail" not in failed.text
    _assert_h1_headers(failed)


async def test_get_query_forbids_extra_and_invalid_bool(async_client):
    extra = await async_client.get(
        "/company-reports/7700000000?extra=value",
    )
    invalid = await async_client.get(
        "/company-reports/7700000000?include_ai_explanation=not-a-bool",
    )

    assert extra.status_code == 422
    assert invalid.status_code == 422


async def test_final_response_exposes_additive_canonical_path(
    async_client,
    monkeypatch,
):
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)

    async def fake_get(_session, *, inn, settings, include_ai_explanation):
        assert inn == "7700000000"
        assert include_ai_explanation is False
        return CompanyReportResponse(
            report_id=uuid4(),
            status="complete",
            started_at=now,
            canonical_path="/company/7700000000-ooo-vektor",
        )

    monkeypatch.setattr(company_reports_router, "get_latest_company_report", fake_get)
    response = await async_client.get("/company-reports/7700000000")

    assert response.status_code == 200
    assert response.json()["canonical_path"] == "/company/7700000000-ooo-vektor"
