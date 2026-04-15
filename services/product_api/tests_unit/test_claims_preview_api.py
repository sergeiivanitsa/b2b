import pytest

from product_api.claims.security import hash_claim_edit_token
from product_api.models import Claim, ClaimEvent

pytestmark = pytest.mark.asyncio


class DummyResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _base_claim(claim_id: int) -> Claim:
    return Claim(
        id=claim_id,
        status="draft",
        generation_state="ready",
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
            "payment_due_date": "2026-02-01",
            "partial_payments_present": False,
            "partial_payments": [],
            "penalty_exists": False,
            "penalty_rate_text": None,
            "documents_mentioned": ["contract"],
            "missing_fields": [],
        },
    )


async def test_generate_preview_success(async_client, mock_session, monkeypatch):
    claim = _base_claim(301)
    mock_session.execute.return_value = DummyResult(claim)

    created_events: list[ClaimEvent] = []

    def add_side_effect(instance):
        if isinstance(instance, ClaimEvent):
            created_events.append(instance)

    mock_session.add.side_effect = add_side_effect

    decision = {
        "generation_state": "ready",
        "risk_flags": [],
        "allowed_blocks": ["header", "facts", "demands"],
        "blocked_blocks": [],
        "missing_fields": [],
    }

    async def fake_generate_claim_preview(
        _settings, *, claim_id, input_text, case_type, normalized_data, decision
    ):
        return {
            "generated_preview_text": "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё",
            "used_fallback": False,
            "error_code": None,
        }

    from product_api.routers import public_claims as public_claims_router

    monkeypatch.setattr(public_claims_router, "evaluate_claim_rules", lambda **_: decision)
    monkeypatch.setattr(
        public_claims_router,
        "generate_claim_preview",
        fake_generate_claim_preview,
    )

    resp = await async_client.post(
        "/claims/301/generate-preview",
        headers={"X-Claim-Edit-Token": "valid-token"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["claim_id"] == 301
    assert payload["generation_state"] == "ready"
    assert payload["manual_review_required"] is False
    assert payload["generated_preview_text"] == "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё"
    assert payload["preview_header"]["from_party"]["line1"] == "Руководителя OOO Alpha"
    assert payload["preview_header"]["to_party"]["line1"] == "Руководителю OOO Vector"
    assert claim.generated_preview_text == "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё"
    assert mock_session.flush.await_count == 1
    assert mock_session.commit.await_count == 1
    assert len(created_events) == 1
    assert created_events[0].event_type == "claim.preview_generated"


async def test_generate_preview_insufficient_data_returns_409(
    async_client, mock_session, monkeypatch
):
    claim = _base_claim(302)
    claim.generation_state = "insufficient_data"
    mock_session.execute.return_value = DummyResult(claim)

    created_events: list[ClaimEvent] = []

    def add_side_effect(instance):
        if isinstance(instance, ClaimEvent):
            created_events.append(instance)

    mock_session.add.side_effect = add_side_effect

    decision = {
        "generation_state": "insufficient_data",
        "risk_flags": ["case_type_uncertain"],
        "allowed_blocks": ["header", "facts"],
        "blocked_blocks": ["legal_basis"],
        "missing_fields": ["creditor_name"],
    }

    from product_api.routers import public_claims as public_claims_router

    monkeypatch.setattr(public_claims_router, "evaluate_claim_rules", lambda **_: decision)

    resp = await async_client.post(
        "/claims/302/generate-preview",
        headers={"X-Claim-Edit-Token": "valid-token"},
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "insufficient_data"
    assert resp.json()["detail"]["missing_fields"] == ["creditor_name"]
    assert mock_session.flush.await_count == 1
    assert mock_session.commit.await_count == 1
    assert len(created_events) == 1
    assert created_events[0].event_type == "claim.preview_blocked_insufficient_data"


async def test_get_preview_success(async_client, mock_session):
    claim = _base_claim(303)
    claim.generation_state = "manual_review_required"
    claim.risk_flags_json = ["no_supporting_documents"]
    claim.allowed_blocks_json = ["header", "facts"]
    claim.blocked_blocks_json = ["attachments"]
    claim.generated_preview_text = "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё"
    mock_session.execute.return_value = DummyResult(claim)

    resp = await async_client.get(
        "/claims/303/preview",
        headers={"X-Claim-Edit-Token": "valid-token"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["claim_id"] == 303
    assert payload["manual_review_required"] is True
    assert payload["risk_flags"] == ["no_supporting_documents"]
    assert payload["generated_preview_text"] == "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё"
    assert payload["preview_header"]["from_party"]["line1"] == "Руководителя OOO Alpha"
    assert payload["preview_header"]["to_party"]["line1"] == "Руководителю OOO Vector"


async def test_get_preview_insufficient_data_returns_409(async_client, mock_session):
    claim = _base_claim(304)
    claim.generation_state = "insufficient_data"
    claim.generated_preview_text = None
    claim.normalized_data_json["creditor_name"] = None
    claim.normalized_data_json["missing_fields"] = ["creditor_name"]
    mock_session.execute.return_value = DummyResult(claim)

    resp = await async_client.get(
        "/claims/304/preview",
        headers={"X-Claim-Edit-Token": "valid-token"},
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "insufficient_data"
    assert "creditor_name" in resp.json()["detail"]["missing_fields"]
