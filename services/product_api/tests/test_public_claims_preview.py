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
                "debtor_name": "OOO Vector",
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
            "generated_preview_text": "Черновик претензии",
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
    assert preview["generated_preview_text"] == "Черновик претензии"

    get_preview_resp = await async_client.get(
        f"/claims/{created['claim_id']}/preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert get_preview_resp.status_code == 200
    get_payload = get_preview_resp.json()
    assert get_payload["generated_preview_text"] == "Черновик претензии"

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
        assert row[4] == "Черновик претензии"


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
