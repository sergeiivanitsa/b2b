import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_generate_preview_and_get_preview(async_client, engine, monkeypatch):
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
                "creditor_inn": "7701234567",
                "debtor_name": "OOO Vector",
                "debtor_inn": "780123456789",
                "contract_signed": True,
                "debt_amount": 380000,
                "payment_due_date": "2026-02-01",
                "documents_mentioned": ["contract"],
            },
        },
    )
    assert patch_resp.status_code == 200

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

    generate_resp = await async_client.post(
        f"/claims/{created['claim_id']}/generate-preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert generate_resp.status_code == 200
    preview = generate_resp.json()
    assert preview["claim_id"] == created["claim_id"]
    assert preview["generation_state"] == "ready"
    assert preview["generated_preview_text"] == "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё"
    assert preview["preview_header"]["from_party"]["line1"] == "Руководителя OOO Alpha"
    assert preview["preview_header"]["to_party"]["line1"] == "Индивидуальному предпринимателю"

    get_preview_resp = await async_client.get(
        f"/claims/{created['claim_id']}/preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert get_preview_resp.status_code == 200
    get_payload = get_preview_resp.json()
    assert get_payload["generated_preview_text"] == "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё"
    assert get_payload["preview_header"]["from_party"]["line1"] == "Руководителя OOO Alpha"
    assert get_payload["preview_header"]["to_party"]["line1"] == "Индивидуальному предпринимателю"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text(
                "SELECT generation_state, risk_flags_json, allowed_blocks_json, "
                "blocked_blocks_json, generated_preview_text "
                "FROM claims WHERE id = :id"
            ),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        assert row[0] == "ready"
        assert row[1] == []
        assert row[2] == ["header", "facts", "demands"]
        assert row[3] == []
        assert row[4] == "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё"


async def test_generate_preview_insufficient_data_blocks(async_client, engine, monkeypatch):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    decision = {
        "generation_state": "insufficient_data",
        "risk_flags": ["case_type_uncertain"],
        "allowed_blocks": ["header", "facts"],
        "blocked_blocks": ["legal_basis"],
        "missing_fields": ["creditor_name", "debt_amount"],
    }

    from product_api.routers import public_claims as public_claims_router

    monkeypatch.setattr(public_claims_router, "evaluate_claim_rules", lambda **_: decision)

    generate_resp = await async_client.post(
        f"/claims/{created['claim_id']}/generate-preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert generate_resp.status_code == 409
    assert generate_resp.json()["detail"]["code"] == "insufficient_data"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text(
                "SELECT generation_state, generated_preview_text FROM claims WHERE id = :id"
            ),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        assert row[0] == "insufficient_data"
        assert row[1] is None


async def test_get_preview_upgrades_legacy_header_full_raw_without_mutating_stored_payload(
    async_client,
    engine,
):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    legacy_header = {
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
    normalized_data = {
        "creditor_name": "Fallback Alpha",
        "debtor_name": "Fallback Vector",
        "missing_fields": [],
    }
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await session.execute(
            text(
                "UPDATE claims "
                "SET generation_state = :generation_state, "
                "generated_preview_text = :generated_preview_text, "
                "normalized_data_json = :normalized_data_json, "
                "preview_header_json = :preview_header_json "
                "WHERE id = :id"
            ),
            {
                "generation_state": "ready",
                "generated_preview_text": "Draft preview text",
                "normalized_data_json": normalized_data,
                "preview_header_json": legacy_header,
                "id": created["claim_id"],
            },
        )
        await session.commit()

    get_preview_resp = await async_client.get(
        f"/claims/{created['claim_id']}/preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert get_preview_resp.status_code == 200
    payload = get_preview_resp.json()
    assert payload["preview_header"]["format_version"] == 2
    assert payload["preview_header"]["from_party"]["line1"] == "Генерального директора ООО «Stored Alpha»"
    assert payload["preview_header"]["from_party"]["line2"] == "Петров Петр Петрович"
    assert payload["preview_header"]["from_party"]["rendered"] == {
        "line1": "От генерального директора",
        "line2": "ООО «Stored Alpha»",
        "line3": "Петров Петр Петрович",
    }
    assert payload["preview_header"]["to_party"]["line1"] == "Директору ООО «Stored Vector»"
    assert payload["preview_header"]["to_party"]["line2"] == "Ivanov Ivan Ivanovich"
    assert payload["preview_header"]["to_party"]["rendered"] == {
        "line1": "Директору",
        "line2": "ООО «Stored Vector»",
        "line3": "Ivanov Ivan Ivanovich",
    }

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text("SELECT preview_header_json FROM claims WHERE id = :id"),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        stored_header = row[0]

    assert stored_header == legacy_header
    assert "format_version" not in stored_header
    assert "rendered" not in stored_header["from_party"]
    assert "rendered" not in stored_header["to_party"]


async def test_get_preview_upgrades_legacy_header_with_normalized_fallback_without_mutation(
    async_client,
    engine,
):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    legacy_header = {
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
    normalized_data = {
        "creditor_name": "Fallback Alpha",
        "debtor_name": "Fallback Vector",
        "missing_fields": [],
    }
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await session.execute(
            text(
                "UPDATE claims "
                "SET generation_state = :generation_state, "
                "generated_preview_text = :generated_preview_text, "
                "normalized_data_json = :normalized_data_json, "
                "preview_header_json = :preview_header_json "
                "WHERE id = :id"
            ),
            {
                "generation_state": "ready",
                "generated_preview_text": "Draft preview text",
                "normalized_data_json": normalized_data,
                "preview_header_json": legacy_header,
                "id": created["claim_id"],
            },
        )
        await session.commit()

    get_preview_resp = await async_client.get(
        f"/claims/{created['claim_id']}/preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert get_preview_resp.status_code == 200
    payload = get_preview_resp.json()
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

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text("SELECT preview_header_json FROM claims WHERE id = :id"),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        stored_header = row[0]

    assert stored_header == legacy_header
    assert "format_version" not in stored_header
    assert "rendered" not in stored_header["from_party"]
    assert "rendered" not in stored_header["to_party"]


async def test_get_preview_upgrades_legacy_broken_header_with_emergency_bridge_without_mutation(
    async_client,
    engine,
):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    legacy_header = {
        "from_party": {
            "line1": "Рук. ООО «Альфа»",
            "line2": "Петров П.П.",
        },
        "to_party": {
            "line1": "Кому: ???",
            "line2": None,
        },
    }
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await session.execute(
            text(
                "UPDATE claims "
                "SET generation_state = :generation_state, "
                "generated_preview_text = :generated_preview_text, "
                "normalized_data_json = :normalized_data_json, "
                "preview_header_json = :preview_header_json "
                "WHERE id = :id"
            ),
            {
                "generation_state": "ready",
                "generated_preview_text": "Draft preview text",
                "normalized_data_json": None,
                "preview_header_json": legacy_header,
                "id": created["claim_id"],
            },
        )
        await session.commit()

    get_preview_resp = await async_client.get(
        f"/claims/{created['claim_id']}/preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert get_preview_resp.status_code == 200
    payload = get_preview_resp.json()
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

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text("SELECT preview_header_json FROM claims WHERE id = :id"),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        stored_header = row[0]

    assert stored_header == legacy_header
    assert "format_version" not in stored_header
    assert "rendered" not in stored_header["from_party"]
    assert "rendered" not in stored_header["to_party"]
