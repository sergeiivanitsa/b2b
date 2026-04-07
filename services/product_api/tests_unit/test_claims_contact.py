import pytest

from product_api.claims.security import hash_claim_edit_token
from product_api.models import Claim, ClaimEvent

pytestmark = pytest.mark.asyncio


class DummyResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


async def test_post_claim_contact_updates_contact(async_client, mock_session):
    claim = Claim(
        id=201,
        status="in_review",
        generation_state="manual_review_required",
        price_rub=990,
        input_text="OOO Vector did not pay",
        edit_token_hash=hash_claim_edit_token("valid-token"),
        client_email="old@example.com",
        client_phone="+79990000000",
    )
    mock_session.execute.return_value = DummyResult(claim)

    created_events: list[ClaimEvent] = []

    def add_side_effect(instance):
        if isinstance(instance, ClaimEvent):
            created_events.append(instance)

    mock_session.add.side_effect = add_side_effect

    resp = await async_client.post(
        "/claims/201/contact",
        headers={"X-Claim-Edit-Token": "valid-token"},
        json={
            "client_email": " CLIENT@Example.com ",
            "client_phone": " +7 999 123 45 67 ",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["client_email"] == "client@example.com"
    assert "client_phone" not in payload
    assert claim.client_phone == "+79990000000"
    assert claim.status == "in_review"
    assert claim.generation_state == "manual_review_required"
    assert mock_session.flush.await_count == 1
    assert mock_session.commit.await_count == 1
    assert len(created_events) == 1
    assert created_events[0].event_type == "claim.contact_updated"
    assert "client_email" in created_events[0].payload_json["changed_fields"]
    assert "client_phone" not in created_events[0].payload_json["changed_fields"]


async def test_post_claim_contact_invalid_email_returns_400(async_client, mock_session):
    claim = Claim(
        id=202,
        status="draft",
        generation_state="insufficient_data",
        price_rub=990,
        input_text="OOO Vector did not pay",
        edit_token_hash=hash_claim_edit_token("valid-token"),
    )
    mock_session.execute.return_value = DummyResult(claim)

    resp = await async_client.post(
        "/claims/202/contact",
        headers={"X-Claim-Edit-Token": "valid-token"},
        json={"client_email": "invalid-email"},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid client_email"
    assert mock_session.flush.await_count == 0
    assert mock_session.commit.await_count == 0


async def test_post_claim_contact_does_not_touch_phone(async_client, mock_session):
    claim = Claim(
        id=203,
        status="draft",
        generation_state="ready",
        price_rub=990,
        input_text="OOO Vector did not pay",
        edit_token_hash=hash_claim_edit_token("valid-token"),
        client_email="client@example.com",
        client_phone="+79990000000",
    )
    mock_session.execute.return_value = DummyResult(claim)

    created_events: list[ClaimEvent] = []

    def add_side_effect(instance):
        if isinstance(instance, ClaimEvent):
            created_events.append(instance)

    mock_session.add.side_effect = add_side_effect

    resp = await async_client.post(
        "/claims/203/contact",
        headers={"X-Claim-Edit-Token": "valid-token"},
        json={
            "client_email": "client@example.com",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["client_email"] == "client@example.com"
    assert "client_phone" not in payload
    assert claim.client_phone == "+79990000000"
    assert mock_session.flush.await_count == 1
    assert mock_session.commit.await_count == 1
    assert len(created_events) == 1
    assert created_events[0].event_type == "claim.contact_updated"
    assert created_events[0].payload_json["changed_fields"] == []
