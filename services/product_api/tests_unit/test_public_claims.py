from datetime import datetime, timezone

import pytest

from product_api.claims.security import hash_claim_edit_token, require_claim_access
from product_api.gateway_client import GatewayError
from product_api.models import Claim, ClaimEvent

pytestmark = pytest.mark.asyncio


class DummyResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


async def test_create_public_claim_ok(async_client, mock_session):
    created_claims: list[Claim] = []
    created_events: list[ClaimEvent] = []

    def add_side_effect(instance):
        if isinstance(instance, Claim):
            instance.id = 101
            created_claims.append(instance)
        elif isinstance(instance, ClaimEvent):
            instance.id = 202
            created_events.append(instance)

    mock_session.add.side_effect = add_side_effect

    resp = await async_client.post(
        "/claims",
        json={"input_text": "  OOO Vector did not pay for delivery  "},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["claim_id"] == 101
    assert isinstance(payload["edit_token"], str)
    assert payload["edit_token"]
    assert payload["claim"]["id"] == 101
    assert payload["claim"]["status"] == "draft"
    assert payload["claim"]["generation_state"] == "insufficient_data"
    assert payload["claim"]["manual_review_required"] is False
    assert payload["claim"]["input_text"] == "OOO Vector did not pay for delivery"

    assert len(created_claims) == 1
    assert created_claims[0].edit_token_hash != payload["edit_token"]
    assert len(created_events) == 1
    assert created_events[0].event_type == "claim.created"
    assert created_events[0].payload_json["input_text_length"] == len(
        "OOO Vector did not pay for delivery"
    )


async def test_create_public_claim_blank_input_400(async_client):
    resp = await async_client.post("/claims", json={"input_text": "   "})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "input_text is required"


async def test_get_public_claim_ok(async_client):
    async def override_claim_access():
        return Claim(
            id=55,
            status="draft",
            generation_state="manual_review_required",
            price_rub=990,
            input_text="Claim text",
            edit_token_hash="hidden",
            client_email="client@example.com",
            client_phone="+79990000000",
            case_type="supply",
            normalized_data_json={"debtor_name": "OOO Vector"},
            created_at=datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 2, 16, 12, 5, tzinfo=timezone.utc),
        )

    from product_api.main import app

    app.dependency_overrides[require_claim_access] = override_claim_access
    try:
        resp = await async_client.get("/claims/55")
    finally:
        app.dependency_overrides.pop(require_claim_access, None)

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == 55
    assert payload["manual_review_required"] is True
    assert payload["normalized_data"] == {"debtor_name": "OOO Vector"}
    assert "edit_token_hash" not in payload
    assert "risk_flags_json" not in payload
    assert "summary_for_admin" not in payload


async def test_extract_public_claim_ok(async_client, mock_session, monkeypatch):
    claim = Claim(
        id=88,
        status="draft",
        generation_state="insufficient_data",
        price_rub=990,
        input_text="OOO Vector did not pay for delivery",
        edit_token_hash=hash_claim_edit_token("valid-token"),
    )
    mock_session.execute.return_value = DummyResult(claim)

    created_events: list[ClaimEvent] = []

    def add_side_effect(instance):
        if isinstance(instance, ClaimEvent):
            created_events.append(instance)

    mock_session.add.side_effect = add_side_effect

    async def fake_run_claim_extraction(_settings, *, claim_id, input_text):
        assert claim_id == 88
        assert input_text == "OOO Vector did not pay for delivery"
        return {
            "case_type": "supply",
            "normalized_data": {
                "creditor_name": "OOO Alpha",
                "debtor_name": "OOO Vector",
                "contract_signed": True,
                "contract_number": "17",
                "contract_date": "2026-01-12",
                "debt_amount": 380000,
                "payment_due_date": "2026-02-01",
                "partial_payments_present": False,
                "partial_payments": [],
                "penalty_exists": False,
                "penalty_rate_text": None,
                "documents_mentioned": ["contract"],
                "missing_fields": [],
            },
            "error_code": None,
        }

    from product_api.routers import public_claims as public_claims_router

    monkeypatch.setattr(public_claims_router, "run_claim_extraction", fake_run_claim_extraction)

    resp = await async_client.post(
        "/claims/88/extract",
        headers={"X-Claim-Edit-Token": "valid-token"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == 88
    assert payload["case_type"] == "supply"
    assert payload["generation_state"] == "ready"
    assert payload["normalized_data"]["debtor_name"] == "OOO Vector"
    assert claim.case_type == "supply"
    assert claim.generation_state == "ready"
    assert mock_session.flush.await_count == 1
    assert mock_session.commit.await_count == 1
    assert len(created_events) == 1
    assert created_events[0].event_type == "claim.extract_succeeded"
    assert created_events[0].payload_json["result"] == "success"


async def test_extract_public_claim_gateway_error_502(async_client, mock_session, monkeypatch):
    claim = Claim(
        id=89,
        status="draft",
        generation_state="insufficient_data",
        price_rub=990,
        input_text="OOO Vector did not pay for delivery",
        edit_token_hash=hash_claim_edit_token("valid-token"),
    )
    mock_session.execute.return_value = DummyResult(claim)

    created_events: list[ClaimEvent] = []

    def add_side_effect(instance):
        if isinstance(instance, ClaimEvent):
            created_events.append(instance)

    mock_session.add.side_effect = add_side_effect

    async def fake_run_claim_extraction(_settings, *, claim_id, input_text):
        raise GatewayError("boom")

    from product_api.routers import public_claims as public_claims_router

    monkeypatch.setattr(public_claims_router, "run_claim_extraction", fake_run_claim_extraction)

    resp = await async_client.post(
        "/claims/89/extract",
        headers={"X-Claim-Edit-Token": "valid-token"},
    )

    assert resp.status_code == 502
    assert resp.json()["detail"] == "gateway error"
    assert mock_session.flush.await_count == 0
    assert mock_session.commit.await_count == 1
    assert len(created_events) == 1
    assert created_events[0].event_type == "claim.extract_failed"
    assert created_events[0].payload_json["error_code"] == "gateway_error"


async def test_update_public_claim_patch_merges_user_edits(async_client, mock_session):
    claim = Claim(
        id=90,
        status="draft",
        generation_state="insufficient_data",
        price_rub=990,
        input_text="OOO Vector did not pay for delivery",
        edit_token_hash=hash_claim_edit_token("valid-token"),
        case_type="supply",
        normalized_data_json={
            "creditor_name": "OOO Alpha",
            "debtor_name": "OOO Vector",
            "contract_signed": True,
            "contract_number": "17",
            "contract_date": "2026-01-12",
            "debt_amount": 380000,
            "payment_due_date": "2000-01-01",
            "partial_payments_present": False,
            "partial_payments": [],
            "penalty_exists": True,
            "penalty_rate_text": "0.1% per day",
            "documents_mentioned": ["contract"],
            "missing_fields": [],
        },
    )
    mock_session.execute.return_value = DummyResult(claim)

    created_events: list[ClaimEvent] = []

    def add_side_effect(instance):
        if isinstance(instance, ClaimEvent):
            created_events.append(instance)

    mock_session.add.side_effect = add_side_effect

    resp = await async_client.patch(
        "/claims/90",
        headers={"X-Claim-Edit-Token": "valid-token"},
        json={
            "case_type": "подряд",
            "client_email": " CLIENT@Example.com ",
            "normalized_data": {
                "partial_payments_present": "да",
                "partial_payments": [
                    {"amount": "50 000 ₽", "date": "20.01.2026"},
                    {"amount": 30000, "date": "2026-01-28"},
                ],
                "penalty_exists": "нет",
                "penalty_rate_text": "0.1% per day",
                "documents_mentioned": ["Договор", "Счёт"],
            },
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["case_type"] == "contract_work"
    assert payload["client_email"] == "client@example.com"
    assert payload["normalized_data"]["partial_payments_present"] is True
    assert payload["normalized_data"]["partial_payments"] == [
        {"amount": 50000, "date": "2026-01-20"},
        {"amount": 30000, "date": "2026-01-28"},
    ]
    assert payload["normalized_data"]["penalty_exists"] is False
    assert payload["normalized_data"]["penalty_rate_text"] is None
    assert payload["step2"]["derived"]["total_paid_amount"] == 80000
    assert payload["step2"]["derived"]["remaining_debt_amount"] == 300000
    assert payload["step2"]["conditional_visibility"]["show_partial_payments"] is True
    assert payload["step2"]["conditional_visibility"]["show_penalty_rate"] is False
    assert claim.generation_state == "ready"
    assert mock_session.flush.await_count == 1
    assert mock_session.commit.await_count == 1
    assert len(created_events) == 1
    assert created_events[0].event_type == "claim.step2_updated"
    assert "case_type" in created_events[0].payload_json["changed_fields"]


async def test_update_public_claim_patch_invalid_case_type_returns_400(async_client, mock_session):
    claim = Claim(
        id=91,
        status="draft",
        generation_state="insufficient_data",
        price_rub=990,
        input_text="OOO Vector did not pay for delivery",
        edit_token_hash=hash_claim_edit_token("valid-token"),
    )
    mock_session.execute.return_value = DummyResult(claim)

    resp = await async_client.patch(
        "/claims/91",
        headers={"X-Claim-Edit-Token": "valid-token"},
        json={"case_type": "other"},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid case_type"
    assert mock_session.flush.await_count == 0
    assert mock_session.commit.await_count == 0
