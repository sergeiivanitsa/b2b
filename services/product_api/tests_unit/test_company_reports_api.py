from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from product_api.company_reports.schemas import (
    CompanyReportAcceptedResponse,
    CompanyReportStatusResponse,
)
from product_api.company_reports.service import (
    InvalidCompanyReportIdentifierError,
)
from product_api.main import app
from product_api.models import User
from product_api.routers import company_reports as company_reports_router

pytestmark = pytest.mark.asyncio


async def _member():
    return User(
        id=501,
        email="member@example.com",
        role="member",
        is_active=True,
        company_id=42,
        is_superadmin=False,
    )


async def _superadmin():
    return User(
        id=777,
        email="root@example.com",
        role=None,
        is_active=True,
        company_id=None,
        is_superadmin=True,
    )


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
    app.dependency_overrides[
        company_reports_router.require_company_report_member
    ] = _member
    try:
        response = await async_client.post(
            "/company-reports",
            json={"inn": "7700000000"},
        )
        invalid = await async_client.post(
            "/company-reports",
            json={"inn": "7700000000", "provider": "private"},
        )
    finally:
        app.dependency_overrides.pop(
            company_reports_router.require_company_report_member,
            None,
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
    app.dependency_overrides[
        company_reports_router.require_company_report_member
    ] = _member
    try:
        response = await async_client.post(
            "/company-reports",
            json={"inn": "7700000000000"},
        )
    finally:
        app.dependency_overrides.pop(
            company_reports_router.require_company_report_member,
            None,
        )

    assert response.status_code == 400
    assert response.json() == {
        "detail": {"code": "invalid_inn", "message": "invalid INN"}
    }


async def test_status_has_no_query_surface_and_superadmin_is_allowed(
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
    app.dependency_overrides[
        company_reports_router.require_company_report_member
    ] = _superadmin
    try:
        response = await async_client.get(
            "/company-reports/7700000000/status",
        )
        invalid = await async_client.get(
            "/company-reports/7700000000/status?extra=value",
        )
    finally:
        app.dependency_overrides.pop(
            company_reports_router.require_company_report_member,
            None,
        )

    assert response.status_code == 200
    assert invalid.status_code == 422


async def test_get_query_forbids_extra_and_invalid_bool(async_client):
    app.dependency_overrides[
        company_reports_router.require_company_report_member
    ] = _member
    try:
        extra = await async_client.get(
            "/company-reports/7700000000?extra=value",
        )
        invalid = await async_client.get(
            "/company-reports/7700000000?include_ai_explanation=not-a-bool",
        )
    finally:
        app.dependency_overrides.pop(
            company_reports_router.require_company_report_member,
            None,
        )

    assert extra.status_code == 422
    assert invalid.status_code == 422


async def test_anonymous_is_unauthorized(async_client):
    response = await async_client.get(
        "/company-reports/7700000000/status",
    )
    assert response.status_code == 401


async def test_role_dependency_rejects_authenticated_user_without_role():
    outsider = User(
        id=902,
        email="outsider@example.com",
        role=None,
        is_active=True,
        company_id=None,
        is_superadmin=False,
    )
    with pytest.raises(HTTPException) as captured:
        await company_reports_router.require_company_report_member(
            current_user=outsider
        )
    assert captured.value.status_code == 403
