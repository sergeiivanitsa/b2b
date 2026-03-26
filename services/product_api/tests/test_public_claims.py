import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import hmac_sha256
from product_api.settings import get_settings

pytestmark = pytest.mark.asyncio


async def test_post_claims_creates_draft_and_event(async_client, engine):
    settings = get_settings()

    resp = await async_client.post(
        "/claims",
        json={"input_text": "  OOO Vector did not pay under contract 17  "},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert isinstance(payload["claim_id"], int)
    assert payload["claim"]["status"] == "draft"
    assert payload["claim"]["generation_state"] == "insufficient_data"
    assert payload["claim"]["manual_review_required"] is False
    assert payload["claim"]["input_text"] == "OOO Vector did not pay under contract 17"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text(
                "SELECT edit_token_hash, price_rub, input_text, status, generation_state "
                "FROM claims WHERE id = :id"
            ),
            {"id": payload["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        assert row[0] == hmac_sha256(settings.claim_edit_token_secret, payload["edit_token"])
        assert row[0] != payload["edit_token"]
        assert row[1] == settings.claims_price_rub
        assert row[2] == "OOO Vector did not pay under contract 17"
        assert row[3] == "draft"
        assert row[4] == "insufficient_data"

        event_row = await session.execute(
            text(
                "SELECT event_type, payload_json "
                "FROM claim_events WHERE claim_id = :claim_id"
            ),
            {"claim_id": payload["claim_id"]},
        )
        event = event_row.first()
        assert event is not None
        assert event[0] == "claim.created"
        assert event[1]["input_text_length"] == len(
            "OOO Vector did not pay under contract 17"
        )


async def test_get_claims_requires_token(async_client):
    resp = await async_client.get("/claims/123")

    assert resp.status_code == 401
    assert resp.json()["detail"] == "claim edit token required"


async def test_get_claims_by_id_restores_public_snapshot(async_client, engine):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    resp = await async_client.get(
        f"/claims/{created['claim_id']}",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == created["claim_id"]
    assert payload["input_text"] == "OOO Vector did not pay for delivery"
    assert payload["manual_review_required"] is False
    assert "edit_token_hash" not in payload
    assert "summary_for_admin" not in payload
    assert "final_text" not in payload


async def test_get_claims_by_id_invalid_token_returns_404(async_client):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    resp = await async_client.get(
        f"/claims/{created['claim_id']}",
        headers={"X-Claim-Edit-Token": "bad-token"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "claim not found"
