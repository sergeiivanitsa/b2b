import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_post_claims_pay_success(async_client, engine):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    patch_resp = await async_client.patch(
        f"/claims/{created['claim_id']}",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        json={
            "case_type": "supply",
            "normalized_data": {
                "creditor_name": "OOO Alpha",
                "debtor_name": "OOO Vector",
                "contract_signed": True,
                "debt_amount": 380000,
                "payment_due_date": "2026-02-01",
            },
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["generation_state"] == "ready"

    pay_resp = await async_client.post(
        f"/claims/{created['claim_id']}/pay",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert pay_resp.status_code == 200
    payload = pay_resp.json()
    assert payload["status"] == "paid"
    assert payload["paid_at"] is not None

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text("SELECT status, generation_state, paid_at FROM claims WHERE id = :id"),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        assert row[0] == "paid"
        assert row[1] == "ready"
        assert row[2] is not None

        event_row = await session.execute(
            text(
                "SELECT event_type, payload_json "
                "FROM claim_events WHERE claim_id = :claim_id ORDER BY id DESC LIMIT 1"
            ),
            {"claim_id": created["claim_id"]},
        )
        event = event_row.first()
        assert event is not None
        assert event[0] == "claim.paid_stub"
        assert event[1]["payment_mode"] == "stub"


async def test_post_claims_pay_rejects_insufficient_data(async_client):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    pay_resp = await async_client.post(
        f"/claims/{created['claim_id']}/pay",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )

    assert pay_resp.status_code == 409
    assert pay_resp.json()["detail"] == "insufficient_data"
