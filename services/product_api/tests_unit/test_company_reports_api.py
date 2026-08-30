from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

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
from product_api.company_reports.company_card_v2.service import (
    PublicH2NotFound,
    PublicH2Pending,
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


def _direct_h2_settings(**overrides):
    values = {
        "company_card_v2_direct_launch_enabled": True,
        "company_card_v2_presentations_enabled": True,
        "company_card_v2_writer_enabled": True,
        "company_card_v2_rollout_generation": 7,
        "company_card_v2_allowlist_inns": [],
        "company_card_v2_percentage_basis_points": 10000,
        "company_card_v2_arbitration_collection_enabled": True,
        "company_card_v2_arbitration_mask_active_key_id": "production_v1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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


async def test_direct_launch_legacy_post_creates_only_h2_writer_decision(
    async_client,
    mock_session,
    monkeypatch,
):
    report_id = uuid4()
    calls = []

    async def fake_h2_create(_session, **kwargs):
        calls.append(kwargs)
        return (
            SimpleNamespace(id=uuid4()),
            SimpleNamespace(report_id=report_id, reused=False),
            SimpleNamespace(),
        )

    async def forbidden_h1(*_args, **_kwargs):
        raise AssertionError("direct launch must not enqueue an H1 report")

    monkeypatch.setattr(company_reports_router, "get_settings", _direct_h2_settings)
    monkeypatch.setattr(
        company_reports_router,
        "create_or_reuse_h2_presentation",
        fake_h2_create,
    )
    monkeypatch.setattr(
        company_reports_router,
        "create_or_reuse_company_report",
        forbidden_h1,
    )

    response = await async_client.post(
        "/company-reports",
        json={"inn": "7700000000"},
    )

    assert response.status_code == 202
    assert response.json() == {
        "report_id": str(report_id),
        "status": "pending",
        "reused": False,
    }
    assert calls == [
        {
            "identifier": "7700000000",
            "rollout_generation": 7,
            "arbitration_collection_enabled": True,
            "arbitration_mask_key_id": "production_v1",
        }
    ]
    mock_session.commit.assert_awaited_once()


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


async def test_direct_h2_status_is_pending_until_saved_public_document_is_ready(
    async_client,
    monkeypatch,
):
    now = datetime(2026, 8, 30, tzinfo=timezone.utc)
    report_id = uuid4()

    async def fake_status(_session, *, inn, rollout_generation):
        assert rollout_generation == 7
        return CompanyReportStatusResponse(
            report_id=report_id,
            status="complete",
            started_at=now,
            generated_at=now,
            finished_at=now,
        )

    async def pending_h2(*_args, **_kwargs):
        raise PublicH2Pending("report_pending")

    monkeypatch.setattr(company_reports_router, "get_settings", _direct_h2_settings)
    monkeypatch.setattr(company_reports_router, "_get_direct_h2_status", fake_status)
    monkeypatch.setattr(company_reports_router, "resolve_direct_public_h2", pending_h2)

    response = await async_client.get("/company-reports/7700000000/status")

    assert response.status_code == 200
    assert response.json() == {
        "report_id": str(report_id),
        "status": "pending",
        "started_at": "2026-08-30T00:00:00Z",
        "generated_at": None,
        "finished_at": None,
        "fresh_until": None,
        "public_document_path": None,
    }


async def test_direct_h2_status_hands_ready_document_to_ssr_navigation(
    async_client,
    monkeypatch,
):
    now = datetime(2026, 8, 30, tzinfo=timezone.utc)
    report_id = uuid4()

    async def fake_status(_session, *, inn, rollout_generation):
        assert rollout_generation == 7
        return CompanyReportStatusResponse(
            report_id=report_id,
            status="partial",
            started_at=now,
            generated_at=now,
            finished_at=now,
        )

    async def ready_h2(_session, *, inn, rollout_generation):
        assert inn == "7700000000"
        assert rollout_generation == 7
        return SimpleNamespace()

    monkeypatch.setattr(company_reports_router, "get_settings", _direct_h2_settings)
    monkeypatch.setattr(company_reports_router, "_get_direct_h2_status", fake_status)
    monkeypatch.setattr(company_reports_router, "resolve_direct_public_h2", ready_h2)

    response = await async_client.get("/company-reports/7700000000/status")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["public_document_path"] == "/company/7700000000"


async def test_direct_status_resolves_the_h2_lifecycle_head_not_legacy_h1(
    mock_session,
    monkeypatch,
):
    now = datetime(2026, 8, 30, tzinfo=timezone.utc)
    subject_id = uuid4()
    report_id = uuid4()
    presentation_id = uuid4()
    subject = SimpleNamespace(
        id=subject_id,
        normalized_identifier="7700000000",
    )
    head = SimpleNamespace(
        subject_id=subject_id,
        presentation_id=presentation_id,
        report_id=report_id,
        presentation_contract="company_public_h2_v1",
        rollout_generation=7,
    )
    record = SimpleNamespace(
        id=report_id,
        subject_id=subject_id,
        writer_profile="company_card_v2_writer_v3",
        presentation_contract="company_public_h2_v1",
        report_version="3",
        rollout_generation=7,
        lifecycle_status="complete",
        started_at=now,
        generated_at=now,
        finished_at=now,
        fresh_until=None,
    )
    resolved = SimpleNamespace(
        presentation_id=presentation_id,
        presentation_contract="company_public_h2_v1",
        report_id=report_id,
        lifecycle_status="complete",
        normalized_identifier="7700000000",
    )

    mock_session.scalar = AsyncMock(return_value=subject)
    mock_session.get = AsyncMock(side_effect=[head, record])

    async def fake_lifecycle(_session, value):
        assert value == presentation_id
        return resolved

    monkeypatch.setattr(
        company_reports_router,
        "resolve_presentation_lifecycle",
        fake_lifecycle,
    )

    response = await company_reports_router._get_direct_h2_status(
        mock_session,
        inn="7700000000",
        rollout_generation=7,
    )

    assert response.report_id == report_id
    assert response.status == "complete"


async def test_direct_status_rejects_a_stale_rollout_head(
    mock_session,
    monkeypatch,
):
    subject_id = uuid4()
    report_id = uuid4()
    presentation_id = uuid4()
    mock_session.scalar = AsyncMock(
        return_value=SimpleNamespace(
            id=subject_id,
            normalized_identifier="7700000000",
        )
    )
    mock_session.get = AsyncMock(
        return_value=SimpleNamespace(
            subject_id=subject_id,
            presentation_id=presentation_id,
            report_id=report_id,
            presentation_contract="company_public_h2_v1",
            rollout_generation=6,
        )
    )

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("stale generation must fail before lifecycle read")

    monkeypatch.setattr(
        company_reports_router,
        "resolve_presentation_lifecycle",
        forbidden,
    )

    with pytest.raises(company_reports_router.CompanyReportServiceNotFoundError):
        await company_reports_router._get_direct_h2_status(
            mock_session,
            inn="7700000000",
            rollout_generation=7,
        )


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


async def test_direct_launch_hides_existing_h1_before_any_legacy_read(
    async_client,
    monkeypatch,
):
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("an existing H1 must not displace direct H2")

    async def no_current_h2(*_args, **_kwargs):
        raise PublicH2NotFound("company card v2 was not found")

    monkeypatch.setattr(company_reports_router, "get_settings", _direct_h2_settings)
    monkeypatch.setattr(company_reports_router, "resolve_public_h1", forbidden)
    monkeypatch.setattr(
        company_reports_router,
        "resolve_direct_public_h2",
        no_current_h2,
    )
    monkeypatch.setattr(
        company_reports_router,
        "_enforce_report_rate_limit",
        lambda *_args, **_kwargs: None,
    )

    response = await async_client.get("/company-reports/7700000000/public-h1")

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "code": "company_report_not_found",
            "message": "company report not found",
        }
    }
    _assert_h1_headers(response)


async def test_direct_launch_public_h1_does_not_reenqueue_current_pending_h2(
    async_client,
    monkeypatch,
):
    async def pending(_session, *, inn, rollout_generation):
        assert inn == "7700000000"
        assert rollout_generation == 7
        raise PublicH2Pending("report_pending")

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("current H2 must never fall through to H1")

    monkeypatch.setattr(company_reports_router, "get_settings", _direct_h2_settings)
    monkeypatch.setattr(company_reports_router, "resolve_direct_public_h2", pending)
    monkeypatch.setattr(company_reports_router, "resolve_public_h1", forbidden)
    monkeypatch.setattr(
        company_reports_router,
        "_enforce_report_rate_limit",
        lambda *_args, **_kwargs: None,
    )

    response = await async_client.get("/company-reports/7700000000/public-h1")

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "report_pending",
            "message": "company report is pending",
        }
    }
    _assert_h1_headers(response)


async def test_direct_launch_public_h2_uses_exact_head_not_generic_assignment(
    async_client,
    monkeypatch,
):
    calls = []

    class Dto:
        def model_dump(self, *, mode):
            assert mode == "json"
            return {"contract_version": "company_public_h2_v1"}

    async def direct(_session, *, inn, rollout_generation):
        calls.append((inn, rollout_generation))
        return Dto()

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("direct H2 must not resolve an old assignment")

    async def fake_session():
        yield object()

    monkeypatch.setattr(company_reports_router, "get_settings", _direct_h2_settings)
    monkeypatch.setattr(company_reports_router, "resolve_direct_public_h2", direct)
    monkeypatch.setattr(company_reports_router, "resolve_public_h2", forbidden)
    monkeypatch.setattr(company_reports_router, "get_session", fake_session)
    monkeypatch.setattr(
        company_reports_router,
        "_enforce_report_rate_limit",
        lambda *_args, **_kwargs: None,
    )

    response = await async_client.get("/company-reports/7700000000/public-h2")

    assert response.status_code == 200
    assert response.json() == {"contract_version": "company_public_h2_v1"}
    assert calls == [("7700000000", 7)]


async def test_direct_launch_public_h2_maps_storage_failure_to_503(
    async_client,
    monkeypatch,
):
    async def unavailable(*_args, **_kwargs):
        raise SQLAlchemyError("private storage detail")

    async def fake_session():
        yield object()

    monkeypatch.setattr(company_reports_router, "get_settings", _direct_h2_settings)
    monkeypatch.setattr(
        company_reports_router,
        "resolve_direct_public_h2",
        unavailable,
    )
    monkeypatch.setattr(company_reports_router, "get_session", fake_session)
    monkeypatch.setattr(
        company_reports_router,
        "_enforce_report_rate_limit",
        lambda *_args, **_kwargs: None,
    )

    response = await async_client.get("/company-reports/7700000000/public-h2")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "company_report_unavailable",
            "message": "company report service is unavailable",
        }
    }
    assert "private storage detail" not in response.text


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


async def test_direct_launch_final_h1_json_read_fails_closed_with_h2_handoff(
    async_client,
    monkeypatch,
):
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("direct launch must not return a stale H1 snapshot")

    monkeypatch.setattr(company_reports_router, "get_settings", _direct_h2_settings)
    monkeypatch.setattr(
        company_reports_router,
        "get_latest_company_report",
        forbidden,
    )
    monkeypatch.setattr(
        company_reports_router,
        "_enforce_report_rate_limit",
        lambda *_args, **_kwargs: None,
    )

    response = await async_client.get("/company-reports/7700000000")

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "company_report_h2_document",
            "message": "company report uses the H2 document lifecycle",
            "public_document_path": "/company/7700000000",
        }
    }
