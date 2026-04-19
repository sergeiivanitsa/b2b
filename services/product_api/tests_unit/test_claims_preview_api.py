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
    assert payload["preview_header"]["format_version"] == 2
    assert payload["preview_header"]["from_party"]["line1"] == "Руководителя OOO Alpha"
    assert payload["preview_header"]["to_party"]["line1"] == "Руководителю OOO Vector"
    assert payload["preview_header"]["from_party"]["rendered"] == {
        "line1": "От руководителя",
        "line2": "OOO Alpha",
        "line3": None,
    }
    assert payload["preview_header"]["to_party"]["rendered"] == {
        "line1": "Руководителю",
        "line2": "OOO Vector",
        "line3": None,
    }
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
    assert payload["preview_header"]["format_version"] == 2
    assert payload["preview_header"]["from_party"]["line1"] == "Руководителя OOO Alpha"
    assert payload["preview_header"]["to_party"]["line1"] == "Руководителю OOO Vector"
    assert payload["preview_header"]["from_party"]["rendered"] == {
        "line1": "От руководителя",
        "line2": "OOO Alpha",
        "line3": None,
    }
    assert payload["preview_header"]["to_party"]["rendered"] == {
        "line1": "Руководителю",
        "line2": "OOO Vector",
        "line3": None,
    }


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


async def test_get_preview_with_null_header_keeps_null_without_artificial_shape(
    async_client,
    mock_session,
    monkeypatch,
):
    claim = _base_claim(310)
    claim.generated_preview_text = "Draft preview text"
    claim.preview_header_json = None
    claim.normalized_data_json = None
    mock_session.execute.return_value = DummyResult(claim)

    from product_api.claims import repository as claims_repository
    from product_api.routers import public_claims as public_claims_router

    monkeypatch.setattr(
        claims_repository,
        "build_preview_header_from_normalized_data",
        lambda _normalized_data: None,
    )

    async def fake_rebuild_claim_preview_header(_settings, target_claim):
        target_claim.preview_header_json = None
        return None

    monkeypatch.setattr(
        public_claims_router,
        "rebuild_claim_preview_header",
        fake_rebuild_claim_preview_header,
    )

    resp = await async_client.get(
        "/claims/310/preview",
        headers={"X-Claim-Edit-Token": "valid-token"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["claim_id"] == 310
    assert payload["generated_preview_text"] == "Draft preview text"
    assert payload["preview_header"] is None


async def test_get_preview_old_payload_line2_null_bridge_is_stable(async_client, mock_session):
    claim = _base_claim(305)
    claim.generated_preview_text = "Draft preview text"
    claim.preview_header_json = {
        "from_party": {
            "kind": "legal_entity",
            "company_name": "ООО «Альфа»",
            "position_raw": None,
            "person_name": None,
            "line1": "Руководителя ООО «Альфа»",
            "line2": None,
        },
        "to_party": {
            "kind": "legal_entity",
            "company_name": "ООО «Вектор»",
            "position_raw": None,
            "person_name": None,
            "line1": "Руководителю ООО «Вектор»",
            "line2": None,
        },
    }
    original_payload = claim.preview_header_json.copy()
    original_from_party = dict(claim.preview_header_json["from_party"])
    original_to_party = dict(claim.preview_header_json["to_party"])
    mock_session.execute.return_value = DummyResult(claim)

    resp = await async_client.get(
        "/claims/305/preview",
        headers={"X-Claim-Edit-Token": "valid-token"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["preview_header"]["format_version"] == 2
    assert payload["preview_header"]["from_party"]["line1"] == "Руководителя ООО «Альфа»"
    assert payload["preview_header"]["from_party"]["line2"] is None
    assert payload["preview_header"]["from_party"]["rendered"]["line1"] == "От руководителя"
    assert payload["preview_header"]["from_party"]["rendered"]["line2"] == "ООО «Альфа»"
    assert payload["preview_header"]["from_party"]["rendered"]["line3"] is None
    assert payload["preview_header"]["to_party"]["line1"] == "Руководителю ООО «Вектор»"
    assert payload["preview_header"]["to_party"]["line2"] is None
    assert payload["preview_header"]["to_party"]["rendered"]["line1"] == "Руководителю"
    assert payload["preview_header"]["to_party"]["rendered"]["line2"] == "ООО «Вектор»"
    assert payload["preview_header"]["to_party"]["rendered"]["line3"] is None
    assert claim.preview_header_json == original_payload
    assert claim.preview_header_json["from_party"] == original_from_party
    assert claim.preview_header_json["to_party"] == original_to_party
    assert "format_version" not in claim.preview_header_json
    assert "rendered" not in claim.preview_header_json["from_party"]
    assert "rendered" not in claim.preview_header_json["to_party"]


async def test_get_preview_legacy_payload_full_raw_inflects_rendered_line3_from_stored_raw(
    async_client,
    mock_session,
):
    claim = _base_claim(307)
    claim.generated_preview_text = "Draft preview text"
    claim.normalized_data_json["creditor_name"] = "Fallback Alpha"
    claim.normalized_data_json["debtor_name"] = "Fallback Vector"
    claim.preview_header_json = {
        "from_party": {
            "kind": "legal_entity",
            "company_name": "ООО «Stored Alpha»",
            "position_raw": "генеральный директор",
            "person_name": "Петров Петр Петрович",
            "line1": "Генерального директора ООО «Stored Alpha»",
            "line2": "Петров Петр Петрович",
        },
        "to_party": {
            "kind": "legal_entity",
            "company_name": "ООО «Stored Vector»",
            "position_raw": "director",
            "person_name": "Ivanov Ivan Ivanovich",
            "line1": "Директору ООО «Stored Vector»",
            "line2": "Ivanov Ivan Ivanovich",
        },
    }
    original_payload = claim.preview_header_json.copy()
    original_from_party = dict(claim.preview_header_json["from_party"])
    original_to_party = dict(claim.preview_header_json["to_party"])
    mock_session.execute.return_value = DummyResult(claim)

    resp = await async_client.get(
        "/claims/307/preview",
        headers={"X-Claim-Edit-Token": "valid-token"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["preview_header"]["format_version"] == 2
    assert payload["preview_header"]["from_party"]["line1"] == "Генерального директора ООО «Stored Alpha»"
    assert payload["preview_header"]["from_party"]["line2"] == "Петров Петр Петрович"
    assert payload["preview_header"]["from_party"]["rendered"] == {
        "line1": "От генерального директора",
        "line2": "ООО «Stored Alpha»",
        "line3": "Петрова Петра Петровича",
    }
    assert payload["preview_header"]["to_party"]["line1"] == "Директору ООО «Stored Vector»"
    assert payload["preview_header"]["to_party"]["line2"] == "Ivanov Ivan Ivanovich"
    assert payload["preview_header"]["to_party"]["rendered"] == {
        "line1": "Директору",
        "line2": "ООО «Stored Vector»",
        "line3": "Ivanov Ivan Ivanovich",
    }
    assert claim.preview_header_json == original_payload
    assert claim.preview_header_json["from_party"] == original_from_party
    assert claim.preview_header_json["to_party"] == original_to_party
    assert "format_version" not in claim.preview_header_json
    assert "rendered" not in claim.preview_header_json["from_party"]
    assert "rendered" not in claim.preview_header_json["to_party"]


async def test_get_preview_legacy_payload_partial_raw_uses_normalized_fallback(
    async_client,
    mock_session,
):
    claim = _base_claim(308)
    claim.generated_preview_text = "Draft preview text"
    claim.normalized_data_json["creditor_name"] = "Fallback Alpha"
    claim.normalized_data_json["debtor_name"] = "Fallback Vector"
    claim.preview_header_json = {
        "from_party": {
            "kind": "legal_entity",
            "company_name": None,
            "position_raw": None,
            "person_name": None,
            "line1": "Руководителя ООО «Old Alpha»",
            "line2": None,
        },
        "to_party": {
            "kind": "legal_entity",
            "company_name": None,
            "position_raw": None,
            "person_name": None,
            "line1": "Руководителю ООО «Old Vector»",
            "line2": None,
        },
    }
    original_payload = claim.preview_header_json.copy()
    original_from_party = dict(claim.preview_header_json["from_party"])
    original_to_party = dict(claim.preview_header_json["to_party"])
    mock_session.execute.return_value = DummyResult(claim)

    resp = await async_client.get(
        "/claims/308/preview",
        headers={"X-Claim-Edit-Token": "valid-token"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["preview_header"]["format_version"] == 2
    assert payload["preview_header"]["from_party"]["line1"] == "Руководителя ООО «Old Alpha»"
    assert payload["preview_header"]["from_party"]["line2"] is None
    assert payload["preview_header"]["from_party"]["rendered"] == {
        "line1": "От руководителя",
        "line2": "Fallback Alpha",
        "line3": None,
    }
    assert payload["preview_header"]["to_party"]["line1"] == "Руководителю ООО «Old Vector»"
    assert payload["preview_header"]["to_party"]["line2"] is None
    assert payload["preview_header"]["to_party"]["rendered"] == {
        "line1": "Руководителю",
        "line2": "Fallback Vector",
        "line3": None,
    }
    assert claim.preview_header_json == original_payload
    assert claim.preview_header_json["from_party"] == original_from_party
    assert claim.preview_header_json["to_party"] == original_to_party
    assert "format_version" not in claim.preview_header_json
    assert "rendered" not in claim.preview_header_json["from_party"]
    assert "rendered" not in claim.preview_header_json["to_party"]


async def test_get_preview_legacy_broken_payload_uses_emergency_bridge(
    async_client,
    mock_session,
):
    claim = _base_claim(309)
    claim.generated_preview_text = "Draft preview text"
    claim.normalized_data_json = None
    claim.preview_header_json = {
        "from_party": {
            "line1": "Рук. ООО «Альфа»",
            "line2": "Петров П.П.",
        },
        "to_party": {
            "line1": "Кому: ???",
            "line2": None,
        },
    }
    original_payload = claim.preview_header_json.copy()
    original_from_party = dict(claim.preview_header_json["from_party"])
    original_to_party = dict(claim.preview_header_json["to_party"])
    mock_session.execute.return_value = DummyResult(claim)

    resp = await async_client.get(
        "/claims/309/preview",
        headers={"X-Claim-Edit-Token": "valid-token"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["preview_header"]["format_version"] == 2
    assert payload["preview_header"]["from_party"]["line1"] == "Рук. ООО «Альфа»"
    assert payload["preview_header"]["from_party"]["line2"] == "Петров П.П."
    assert payload["preview_header"]["from_party"]["rendered"] == {
        "line1": "Рук. ООО «Альфа»",
        "line2": None,
        "line3": "Петров П.П.",
    }
    assert payload["preview_header"]["to_party"]["line1"] == "Кому: ???"
    assert payload["preview_header"]["to_party"]["line2"] is None
    assert payload["preview_header"]["to_party"]["rendered"] == {
        "line1": "Кому: ???",
        "line2": None,
        "line3": None,
    }
    assert claim.preview_header_json == original_payload
    assert claim.preview_header_json["from_party"] == original_from_party
    assert claim.preview_header_json["to_party"] == original_to_party
    assert "format_version" not in claim.preview_header_json
    assert "rendered" not in claim.preview_header_json["from_party"]
    assert "rendered" not in claim.preview_header_json["to_party"]


async def test_generate_preview_with_null_header_keeps_null_without_artificial_shape(
    async_client, mock_session, monkeypatch
):
    claim = _base_claim(306)
    claim.preview_header_json = None
    mock_session.execute.return_value = DummyResult(claim)

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

    async def fake_rebuild_claim_preview_header(_settings, target_claim):
        target_claim.preview_header_json = None
        return None

    from product_api.claims import repository as claims_repository
    from product_api.routers import public_claims as public_claims_router

    monkeypatch.setattr(public_claims_router, "evaluate_claim_rules", lambda **_: decision)
    monkeypatch.setattr(
        public_claims_router,
        "generate_claim_preview",
        fake_generate_claim_preview,
    )
    monkeypatch.setattr(
        public_claims_router,
        "rebuild_claim_preview_header",
        fake_rebuild_claim_preview_header,
    )
    monkeypatch.setattr(
        claims_repository,
        "build_preview_header_from_normalized_data",
        lambda _normalized_data: None,
    )

    resp = await async_client.post(
        "/claims/306/generate-preview",
        headers={"X-Claim-Edit-Token": "valid-token"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["claim_id"] == 306
    assert payload["generated_preview_text"] == "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё"
    assert payload["preview_header"] is None
