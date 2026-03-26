from datetime import datetime, timezone

import pytest

from product_api.claims.security import require_claim_access
from product_api.models import Claim, ClaimEvent

pytestmark = pytest.mark.asyncio


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
