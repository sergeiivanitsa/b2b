from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from product_api.company_reports.persistence.presentations import (
    PresentationLifecycleInvalid,
    PresentationLifecycleNotFound,
    ResolvedPresentationLifecycle,
)
from product_api.main import app as fastapi_app
from product_api.routers import company_report_presentations as presentations_router


def _settings(*, writer_enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        company_card_v2_writer_enabled=writer_enabled,
        company_card_v2_rollout_generation=7,
        company_card_v2_arbitration_collection_enabled=False,
        company_card_v2_arbitration_mask_active_key_id=None,
    )


def _session() -> SimpleNamespace:
    return SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )


def _install_session(monkeypatch, session: object) -> None:
    async def fake_get_session():
        yield session

    monkeypatch.setattr(presentations_router, "get_session", fake_get_session)


def _install_empty_session_source(monkeypatch) -> None:
    async def fake_get_session():
        if False:
            yield None

    monkeypatch.setattr(presentations_router, "get_session", fake_get_session)


def _resolved(
    *,
    presentation_id=None,
    report_id=None,
    lifecycle_status: str = "pending",
    normalized_identifier: str = "7701234567",
) -> ResolvedPresentationLifecycle:
    return ResolvedPresentationLifecycle(
        presentation_id=presentation_id or uuid4(),
        presentation_contract="company_public_h2_v1",
        report_id=report_id or uuid4(),
        lifecycle_status=lifecycle_status,
        normalized_identifier=normalized_identifier,
    )


def _created_tuple(resolved: ResolvedPresentationLifecycle, *, reused: bool):
    subject_id = uuid4()
    presentation = SimpleNamespace(
        id=resolved.presentation_id,
        subject_id=subject_id,
        report_id=resolved.report_id,
        presentation_contract=resolved.presentation_contract,
        rollout_generation=7,
    )
    enqueued = SimpleNamespace(
        subject_id=subject_id,
        report_id=resolved.report_id,
        lifecycle_status=resolved.lifecycle_status,
        reused=reused,
    )
    return presentation, enqueued, SimpleNamespace()


def _assert_security_headers(response) -> None:
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-robots-tag"] == "noindex,follow"


def _assert_exact_lifecycle(
    response,
    resolved: ResolvedPresentationLifecycle,
    *,
    reused: bool,
) -> None:
    assert response.json() == {
        "presentation_id": str(resolved.presentation_id),
        "presentation_contract": "company_public_h2_v1",
        "report_id": str(resolved.report_id),
        "lifecycle_status": resolved.lifecycle_status,
        "public_read_path": (
            f"/company-reports/{resolved.normalized_identifier}/public-h2"
        ),
        "canonical_document_path": None,
        "reused": reused,
    }
    assert "status" not in response.json()
    _assert_security_headers(response)


def test_presentation_create_openapi_declares_exact_202_lifecycle():
    fastapi_app.openapi_schema = None
    document = fastapi_app.openapi()
    create = document["paths"]["/company-report-presentations"]["post"]
    status = document["paths"][
        "/company-report-presentations/{presentation_id}/status"
    ]["get"]

    request_ref = create["requestBody"]["content"]["application/json"]["schema"]
    create_ref = create["responses"]["202"]["content"]["application/json"][
        "schema"
    ]
    status_ref = status["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert request_ref == {
        "$ref": "#/components/schemas/CompanyReportPresentationCreateRequest"
    }
    assert create_ref == {
        "$ref": "#/components/schemas/CompanyReportPresentationLifecycle"
    }
    assert status_ref == create_ref
    assert create.get("parameters", []) == []
    assert [parameter["name"] for parameter in status["parameters"]] == [
        "presentation_id"
    ]

    request_schema = document["components"]["schemas"][
        "CompanyReportPresentationCreateRequest"
    ]
    assert request_schema["additionalProperties"] is False
    assert request_schema["required"] == ["identifier"]
    assert set(request_schema["properties"]) == {"identifier"}

    lifecycle_schema = document["components"]["schemas"][
        "CompanyReportPresentationLifecycle"
    ]
    expected_fields = {
        "presentation_id",
        "presentation_contract",
        "report_id",
        "lifecycle_status",
        "public_read_path",
        "canonical_document_path",
        "reused",
    }
    assert lifecycle_schema["additionalProperties"] is False
    assert set(lifecycle_schema["required"]) == expected_fields
    assert set(lifecycle_schema["properties"]) == expected_fields
    assert lifecycle_schema["properties"]["presentation_contract"]["const"] == (
        "company_public_h2_v1"
    )
    assert lifecycle_schema["properties"]["lifecycle_status"]["enum"] == [
        "pending",
        "complete",
        "partial",
        "failed",
    ]
    assert "status" not in lifecycle_schema["properties"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {},
        None,
        [],
        "7701234567",
        {"identifier": "7701234567", "writer_profile": "private"},
        {"identifier": 7701234567},
    ],
)
async def test_presentation_create_body_is_strict(async_client, body):
    response = await async_client.post(
        "/company-report-presentations",
        json=body,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "suffix", "headers", "expected_code"),
    [
        ("post", "?unknown=value", {}, "presentation_query_forbidden"),
        ("post", "?blank=", {}, "presentation_query_forbidden"),
        ("post", "?a=1&a=2", {}, "presentation_query_forbidden"),
        ("get", "?unknown=value", {}, "presentation_query_forbidden"),
        (
            "post",
            "",
            {"X-Report-Version": ""},
            "presentation_selector_forbidden",
        ),
        (
            "post",
            "",
            {"x-wRiTeR-pRoFiLe": "v3"},
            "presentation_selector_forbidden",
        ),
        (
            "get",
            "",
            {"X-REPORT-VERSION": "3"},
            "presentation_selector_forbidden",
        ),
        (
            "get",
            "",
            {"x-writer-profile": ""},
            "presentation_selector_forbidden",
        ),
    ],
)
async def test_presentation_routes_reject_query_and_selector_before_gate_or_db(
    async_client,
    monkeypatch,
    method,
    suffix,
    headers,
    expected_code,
):
    def forbidden_settings():
        raise AssertionError("settings must not be read")

    def forbidden_session():
        raise AssertionError("database session must not be requested")

    monkeypatch.setattr(presentations_router, "get_settings", forbidden_settings)
    monkeypatch.setattr(presentations_router, "get_session", forbidden_session)
    presentation_id = uuid4()
    path = (
        "/company-report-presentations"
        if method == "post"
        else f"/company-report-presentations/{presentation_id}/status"
    )
    if method == "post":
        response = await async_client.post(
            path + suffix,
            json={"identifier": "7701234567"},
            headers=headers,
        )
    else:
        response = await async_client.get(path + suffix, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == expected_code
    _assert_security_headers(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["", "123456789", "1027700132195"])
async def test_presentation_create_rejects_non_inn_before_gate_or_db(
    async_client,
    monkeypatch,
    identifier,
):
    def forbidden_settings():
        raise AssertionError("settings must not be read")

    def forbidden_session():
        raise AssertionError("database session must not be requested")

    monkeypatch.setattr(presentations_router, "get_settings", forbidden_settings)
    monkeypatch.setattr(presentations_router, "get_session", forbidden_session)
    response = await async_client.post(
        "/company-report-presentations",
        json={"identifier": identifier},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "invalid_company_identifier",
            "message": "invalid INN",
        }
    }
    _assert_security_headers(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("reused", [False, True])
async def test_presentation_create_normalizes_and_returns_frozen_lifecycle(
    async_client,
    monkeypatch,
    reused,
):
    session = _session()
    _install_session(monkeypatch, session)
    resolved = _resolved()
    created = _created_tuple(resolved, reused=reused)

    def selected(*, inn, settings):
        assert inn == "7701234567"
        assert settings.company_card_v2_rollout_generation == 7
        return True

    async def create(_session, **kwargs):
        assert _session is session
        assert kwargs == {
            "identifier": "7701234567",
            "rollout_generation": 7,
            "arbitration_collection_enabled": False,
            "arbitration_mask_key_id": None,
        }
        return created

    async def resolve(_session, presentation_id):
        assert _session is session
        assert presentation_id == resolved.presentation_id
        return resolved

    monkeypatch.setattr(presentations_router, "get_settings", _settings)
    monkeypatch.setattr(presentations_router, "h2_cohort_selected", selected)
    monkeypatch.setattr(
        presentations_router,
        "create_or_reuse_h2_presentation",
        create,
    )
    monkeypatch.setattr(
        presentations_router,
        "resolve_presentation_lifecycle",
        resolve,
    )
    response = await async_client.post(
        "/company-report-presentations",
        json={"identifier": "77-01-234-567"},
        headers={
            "Authorization": "Bearer ignored",
            "Cookie": "locale=ru",
            "Accept-Language": "ru",
            "X-Unrelated": "ignored",
        },
    )

    assert response.status_code == 202
    _assert_exact_lifecycle(response, resolved, reused=reused)
    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_presentation_create_rejects_mismatched_exact_tuple_before_commit(
    async_client,
    monkeypatch,
):
    session = _session()
    _install_session(monkeypatch, session)
    resolved = _resolved()
    created = _created_tuple(resolved, reused=False)
    mismatched = _resolved(
        presentation_id=resolved.presentation_id,
        report_id=uuid4(),
    )

    async def create(*_args, **_kwargs):
        return created

    async def resolve(*_args, **_kwargs):
        return mismatched

    monkeypatch.setattr(presentations_router, "get_settings", _settings)
    monkeypatch.setattr(
        presentations_router,
        "h2_cohort_selected",
        lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        presentations_router,
        "create_or_reuse_h2_presentation",
        create,
    )
    monkeypatch.setattr(
        presentations_router,
        "resolve_presentation_lifecycle",
        resolve,
    )
    response = await async_client.post(
        "/company-report-presentations",
        json={"identifier": "7701234567"},
    )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "presentation_invalid"
    _assert_security_headers(response)
    session.rollback.assert_awaited_once_with()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_presentation_status_ignores_flags_and_reads_exact_opaque_binding(
    async_client,
    monkeypatch,
):
    session = _session()
    _install_session(monkeypatch, session)
    resolved = _resolved(lifecycle_status="partial", normalized_identifier="500100732259")

    def forbidden_settings():
        raise AssertionError("status must not read rollout settings")

    async def resolve(_session, presentation_id):
        assert _session is session
        assert presentation_id == resolved.presentation_id
        return resolved

    monkeypatch.setattr(presentations_router, "get_settings", forbidden_settings)
    monkeypatch.setattr(
        presentations_router,
        "resolve_presentation_lifecycle",
        resolve,
    )
    response = await async_client.get(
        f"/company-report-presentations/{resolved.presentation_id}/status",
        headers={
            "Authorization": "Bearer ignored",
            "Cookie": "locale=ru",
            "Accept-Language": "ru",
            "X-Unrelated": "ignored",
        },
    )

    assert response.status_code == 200
    _assert_exact_lifecycle(response, resolved, reused=True)
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (PresentationLifecycleNotFound(), 404, "presentation_not_found"),
        (PresentationLifecycleInvalid(), 500, "presentation_invalid"),
        (SQLAlchemyError("storage unavailable"), 503, "presentation_unavailable"),
    ],
)
async def test_presentation_status_fails_closed_with_route_headers(
    async_client,
    monkeypatch,
    error,
    status_code,
    code,
):
    session = _session()
    _install_session(monkeypatch, session)

    async def resolve(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(
        presentations_router,
        "resolve_presentation_lifecycle",
        resolve,
    )
    response = await async_client.get(
        f"/company-report-presentations/{uuid4()}/status"
    )

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code
    assert "storage unavailable" not in response.text
    _assert_security_headers(response)


@pytest.mark.asyncio
async def test_presentation_status_empty_session_source_is_unavailable(
    async_client,
    monkeypatch,
):
    _install_empty_session_source(monkeypatch)
    response = await async_client.get(
        f"/company-report-presentations/{uuid4()}/status"
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "presentation_unavailable"
    _assert_security_headers(response)
