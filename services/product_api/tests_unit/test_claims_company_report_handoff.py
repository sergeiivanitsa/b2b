from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from product_api.claims.company_report_handoff import (
    CompanyReportHandoff,
    HandoffResolution,
    resolve_company_report_handoff,
)
from product_api.claims.extraction import build_empty_normalized_data
from product_api.claims.repository import apply_claim_extraction_result
from product_api.models import Claim, User
from product_api.routers import public_claims
from product_api.routers.public_claims import (
    derive_handoff_capabilities,
    normalize_handoff_idempotency_key,
    require_claim_handoff_member,
)


def test_handoff_capabilities_are_actor_report_and_domain_scoped():
    report_id = uuid4()
    command, edit = derive_handoff_capabilities(
        actor_user_id=1, report_id=report_id, idempotency_key="repeat-1"
    )
    assert command != edit
    assert command != derive_handoff_capabilities(
        actor_user_id=2, report_id=report_id, idempotency_key="repeat-1"
    )[0]
    assert edit != derive_handoff_capabilities(
        actor_user_id=1, report_id=uuid4(), idempotency_key="repeat-1"
    )[1]


def test_handoff_idempotency_key_is_canonical_and_strict():
    assert normalize_handoff_idempotency_key("  retry.1  ") == "retry.1"
    with pytest.raises(HTTPException):
        normalize_handoff_idempotency_key("with space")


@pytest.mark.asyncio
async def test_resolver_rejects_missing_report():
    class Result:
        def one_or_none(self):
            return None

    session = SimpleNamespace(execute=lambda _statement: _async(Result()))
    result = await resolve_company_report_handoff(session, uuid4())
    assert result.available is False
    assert result.reason == "report_not_found"


@pytest.mark.asyncio
async def test_resolver_rejects_pending_before_snapshot_access():
    record = SimpleNamespace(lifecycle_status="pending")
    subject = SimpleNamespace()

    class Result:
        def one_or_none(self):
            return record, subject

    session = SimpleNamespace(execute=lambda _statement: _async(Result()))
    result = await resolve_company_report_handoff(session, uuid4())
    assert result.reason == "report_pending"


@pytest.mark.asyncio
async def test_extraction_keeps_linked_debtor_fields():
    source_id = uuid4()
    existing = build_empty_normalized_data()
    existing.update({"debtor_name": "ООО Вектор", "debtor_inn": "7700000000"})
    claim = Claim(
        id=1,
        status="draft",
        generation_state="insufficient_data",
        price_rub=990,
        input_text="facts",
        edit_token_hash="hidden",
        source_company_report_id=source_id,
        normalized_data_json=existing,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    session = SimpleNamespace(add=lambda _value: None, flush=_async_none)
    extracted = build_empty_normalized_data()
    extracted.update({"debtor_name": "Подмена", "debtor_inn": "7800000000"})
    await apply_claim_extraction_result(session, claim, case_type=None, normalized_data=extracted)
    assert claim.normalized_data_json["debtor_name"] == "ООО Вектор"
    assert claim.normalized_data_json["debtor_inn"] == "7700000000"


@pytest.mark.asyncio
async def test_handoff_route_rejects_client_debtor_identity(async_client):
    async def member():
        return User(id=1, email="member@example.com", role="member", is_active=True)

    from product_api.main import app

    app.dependency_overrides[require_claim_handoff_member] = member
    try:
        response = await async_client.post(
            f"/claims/handoff/company-reports/{uuid4()}",
            headers={"Idempotency-Key": "repeat-1"},
            json={"input_text": "facts", "debtor_name": "client override"},
        )
    finally:
        app.dependency_overrides.pop(require_claim_handoff_member, None)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_handoff_preflight_exposes_only_trusted_debtor_fields(async_client, monkeypatch):
    report_id = uuid4()

    async def member():
        return User(id=1, email="member@example.com", role="member", is_active=True)

    async def resolve(_session, incoming_report_id):
        assert incoming_report_id == report_id
        return HandoffResolution(CompanyReportHandoff(report_id, "ООО Вектор", "7700000000"))

    from product_api.main import app

    monkeypatch.setattr(public_claims, "resolve_company_report_handoff", resolve)
    app.dependency_overrides[require_claim_handoff_member] = member
    try:
        response = await async_client.get(f"/claims/handoff/company-reports/{report_id}")
    finally:
        app.dependency_overrides.pop(require_claim_handoff_member, None)
    assert response.status_code == 200
    assert response.json() == {
        "report_id": str(report_id),
        "availability": "available",
        "reason": None,
        "prefill": {"debtor_name": "ООО Вектор", "debtor_inn": "7700000000"},
        "prefilled_fields": ["debtor_name", "debtor_inn"],
    }


async def _async(value):
    return value


async def _async_none():
    return None
