import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_post_claim_contact_persists_and_restores_via_get(async_client, engine):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    contact_resp = await async_client.post(
        f"/claims/{created['claim_id']}/contact",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        json={
            "client_email": " CLIENT@Example.com ",
            "client_phone": " +7 999 123 45 67 ",
        },
    )
    assert contact_resp.status_code == 200
    contact_payload = contact_resp.json()
    assert contact_payload["client_email"] == "client@example.com"
    assert "client_phone" not in contact_payload

    get_resp = await async_client.get(
        f"/claims/{created['claim_id']}",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert get_resp.status_code == 200
    restored = get_resp.json()
    assert restored["client_email"] == "client@example.com"
    assert "client_phone" not in restored

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text(
                "SELECT client_email, client_phone FROM claims WHERE id = :id"
            ),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        assert row[0] == "client@example.com"
        assert row[1] is None

        event_row = await session.execute(
            text(
                "SELECT event_type, payload_json "
                "FROM claim_events WHERE claim_id = :claim_id ORDER BY id DESC LIMIT 1"
            ),
            {"claim_id": created["claim_id"]},
        )
        event = event_row.first()
        assert event is not None
        assert event[0] == "claim.contact_updated"
        assert "client_email" in event[1]["changed_fields"]


async def test_post_claim_contact_invalid_email_returns_400(async_client, engine):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    contact_resp = await async_client.post(
        f"/claims/{created['claim_id']}/contact",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        json={
            "client_email": "invalid-email",
            "client_phone": "+79991234567",
        },
    )
    assert contact_resp.status_code == 400
    assert contact_resp.json()["detail"] == "invalid client_email"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text(
                "SELECT client_email, client_phone FROM claims WHERE id = :id"
            ),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        assert row[0] is None
        assert row[1] is None
