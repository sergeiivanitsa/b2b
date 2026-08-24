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
from product_api.company_reports.company_card_v2.models import (
    ArbitrationBasisV1,
    CompanyCardCounterpartyCoreV1,
    CompanyCardV2Snapshot,
    FinanceBasisV1,
)
from product_api.company_reports.company_card_v2.finance import build_chart_facts
from product_api.company_reports.persistence.v3 import (
    calculate_company_card_v2_snapshot_hash,
    company_card_v2_from_snapshot,
    company_card_v2_to_snapshot,
)
from product_api.company_reports.company_card_v2.arbitration import collect_fixture_arbitration_pages
from product_api.company_reports.company_card_v2.evidence import EvidenceGate
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


def _v3_card(report_id):
    return CompanyCardV2Snapshot(
        report_id=str(report_id),
        rollout_config_generation=1,
        subject_inn="7700000000",
        target_inn="7700000000",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        counterparty=CompanyCardCounterpartyCoreV1(
            inn="7700000000", short_name="ООО Вектор", full_name="ООО Вектор"
        ),
        finance_basis=FinanceBasisV1(),
        arbitration_basis=ArbitrationBasisV1(),
        chart_facts=build_chart_facts(FinanceBasisV1()),
        evidence_version="evidence_v1",
        privacy_version="privacy_v1",
    )


def _verified_arbitration_registry() -> dict[str, object]:
    return {
        name: EvidenceGate(name=name, state="verified", reason="fixture_only")
        for name in (
            "arbitration_total_path", "arbitration_total_type", "total_scope",
            "data_path", "offset_path", "limit_path", "shape_version",
        )
    }


def test_v3_snapshot_roundtrips_private_arbitration_collection_metadata_and_hash() -> None:
    report_id = uuid4()
    collection = collect_fixture_arbitration_pages(
        [{"total_cases": 1, "offset": 0, "limit": 100, "data": [
            {"case_id": "private-case", "respondents": [{"inn": "7700000000"}], "year": 2025},
        ]}], registry=_verified_arbitration_registry(), secret=b"a" * 32,
        key_id="key_1", target_inn="7700000000", report_id=report_id,
    )
    card = _v3_card(report_id).model_copy(update={"arbitration_basis": collection.basis})

    snapshot = company_card_v2_to_snapshot(card)
    restored = company_card_v2_from_snapshot(snapshot)

    assert restored.arbitration_basis == collection.basis
    assert calculate_company_card_v2_snapshot_hash(restored) == calculate_company_card_v2_snapshot_hash(card)
    persisted = str(snapshot)
    for forbidden in ("raw_payload", "raw_headers", "https://"):
        assert forbidden not in persisted


@pytest.mark.asyncio
async def test_v3_handoff_requires_exact_record_tuple_and_exposes_identity_only():
    report_id = uuid4()
    card = _v3_card(report_id)
    record = SimpleNamespace(
        id=report_id,
        report_version="3",
        writer_profile="company_card_v2_writer_v3",
        presentation_contract="company_public_h2_v1",
        rollout_generation=1,
        lifecycle_status="complete",
        normalized_snapshot=card.model_dump(mode="json"),
        snapshot_hash=calculate_company_card_v2_snapshot_hash(card),
    )
    subject = SimpleNamespace(normalized_identifier="7700000000")

    class Result:
        def one_or_none(self):
            return record, subject

    session = SimpleNamespace(execute=lambda _statement: _async(Result()))
    result = await resolve_company_report_handoff(session, report_id)

    assert result.available
    assert result.handoff is not None
    assert result.handoff.debtor_fields() == {"debtor_name": "ООО Вектор", "debtor_inn": "7700000000"}

    record.rollout_generation = 0
    rejected = await resolve_company_report_handoff(session, report_id)
    assert rejected.reason == "invalid_report"


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
