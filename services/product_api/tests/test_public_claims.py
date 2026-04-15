from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import hmac_sha256
from product_api.gateway_client import GatewayError
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


async def test_post_claims_extract_updates_claim(async_client, engine, monkeypatch):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    async def fake_run_claim_extraction(_settings, *, claim_id, input_text):
        assert claim_id == created["claim_id"]
        assert input_text == "OOO Vector did not pay for delivery"
        return {
            "case_type": "supply",
            "normalized_data": {
                "creditor_name": "OOO Alpha",
                "creditor_inn": "7701234567",
                "debtor_name": "OOO Vector",
                "debtor_inn": "780123456789",
                "contract_signed": True,
                "contract_number": "17",
                "contract_date": "2026-01-12",
                "debt_amount": 380000,
                "payment_due_date": "2026-02-01",
                "partial_payments_present": False,
                "partial_payments": [],
                "penalty_exists": False,
                "penalty_rate_text": None,
                "documents_mentioned": ["contract", "invoice"],
                "missing_fields": [],
            },
            "error_code": None,
        }

    from product_api.routers import public_claims as public_claims_router

    monkeypatch.setattr(public_claims_router, "run_claim_extraction", fake_run_claim_extraction)

    resp = await async_client.post(
        f"/claims/{created['claim_id']}/extract",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["case_type"] == "supply"
    assert payload["generation_state"] == "ready"
    assert payload["normalized_data"]["debtor_name"] == "OOO Vector"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text(
                "SELECT case_type, generation_state, normalized_data_json "
                "FROM claims WHERE id = :id"
            ),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        assert row[0] == "supply"
        assert row[1] == "ready"
        assert row[2]["debtor_name"] == "OOO Vector"

        event_row = await session.execute(
            text(
                "SELECT event_type, payload_json "
                "FROM claim_events WHERE claim_id = :claim_id ORDER BY id DESC LIMIT 1"
            ),
            {"claim_id": created["claim_id"]},
        )
        event = event_row.first()
        assert event is not None
        assert event[0] == "claim.extract_succeeded"
        assert event[1]["result"] == "success"


async def test_post_claims_extract_gateway_error_returns_502(async_client, engine, monkeypatch):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    async def fake_run_claim_extraction(_settings, *, claim_id, input_text):
        raise GatewayError("boom")

    from product_api.routers import public_claims as public_claims_router

    monkeypatch.setattr(public_claims_router, "run_claim_extraction", fake_run_claim_extraction)

    resp = await async_client.post(
        f"/claims/{created['claim_id']}/extract",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )

    assert resp.status_code == 502
    assert resp.json()["detail"] == "gateway error"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        event_row = await session.execute(
            text(
                "SELECT event_type, payload_json "
                "FROM claim_events WHERE claim_id = :claim_id ORDER BY id DESC LIMIT 1"
            ),
            {"claim_id": created["claim_id"]},
        )
        event = event_row.first()
        assert event is not None
        assert event[0] == "claim.extract_failed"
        assert event[1]["error_code"] == "gateway_error"


async def test_patch_claims_updates_claim_step2(async_client, engine):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    resp = await async_client.patch(
        f"/claims/{created['claim_id']}",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        json={
            "case_type": "подряд",
            "client_email": " CLIENT@Example.com ",
            "normalized_data": {
                "creditor_name": "OOO Alpha",
                "creditor_inn": "7701234567",
                "debtor_name": "OOO Vector",
                "debtor_inn": "780123456789",
                "contract_signed": "да",
                "contract_number": "17",
                "debt_amount": "380 000 ₽",
                "payment_due_date": "2000-01-01",
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
    assert payload["generation_state"] == "ready"
    assert payload["normalized_data"]["partial_payments"] == [
        {"amount": 50000, "date": "2026-01-20"},
        {"amount": 30000, "date": "2026-01-28"},
    ]
    assert payload["normalized_data"]["penalty_rate_text"] is None
    assert payload["step2"]["derived"]["total_paid_amount"] == 80000
    assert payload["step2"]["derived"]["remaining_debt_amount"] == 300000

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text(
                "SELECT case_type, client_email, generation_state, normalized_data_json "
                "FROM claims WHERE id = :id"
            ),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        assert row[0] == "contract_work"
        assert row[1] == "client@example.com"
        assert row[2] == "ready"
        assert row[3]["partial_payments"][0]["amount"] == 50000
        assert row[3]["penalty_rate_text"] is None

        event_row = await session.execute(
            text(
                "SELECT event_type, payload_json "
                "FROM claim_events WHERE claim_id = :claim_id ORDER BY id DESC LIMIT 1"
            ),
            {"claim_id": created["claim_id"]},
        )
        event = event_row.first()
        assert event is not None
        assert event[0] == "claim.step2_updated"
        assert "case_type" in event[1]["changed_fields"]


async def test_patch_claims_invalid_case_type_returns_400(async_client):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    resp = await async_client.patch(
        f"/claims/{created['claim_id']}",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        json={"case_type": "other"},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid case_type"


async def test_patch_claims_with_datanewton_failure_falls_back_to_local_header(
    async_client,
    monkeypatch,
):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    from product_api.routers import public_claims as public_claims_router
    from product_api.claims import preview_header_enrichment

    monkeypatch.setattr(public_claims_router.settings, "datanewton_enabled", True)
    monkeypatch.setattr(public_claims_router.settings, "datanewton_api_key", "test-key")

    async def fake_fetch(_settings, inn):
        raise RuntimeError("datanewton unavailable")

    monkeypatch.setattr(preview_header_enrichment, "fetch_datanewton_party_by_inn", fake_fetch)

    resp = await async_client.patch(
        f"/claims/{created['claim_id']}",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        json={
            "normalized_data": {
                "creditor_name": "OOO Alpha",
                "creditor_inn": "7701234567",
                "debtor_name": "OOO Vector",
                "debtor_inn": "780123456789",
            },
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["preview_header"]["from_party"]["line1"] == "Руководителя OOO Alpha"
    assert payload["preview_header"]["to_party"]["line1"] == "Индивидуальному предпринимателю"


async def test_post_claims_files_upload_and_list(async_client, engine):
    settings = get_settings()
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    upload_resp = await async_client.post(
        f"/claims/{created['claim_id']}/files",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        files={"file": ("contract.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert upload_resp.status_code == 200
    uploaded = upload_resp.json()
    assert uploaded["filename"] == "contract.pdf"
    assert uploaded["mime_type"] == "application/pdf"
    assert uploaded["file_role"] == "supporting_document"

    list_resp = await async_client.get(
        f"/claims/{created['claim_id']}/files",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert list_resp.status_code == 200
    files_payload = list_resp.json()
    assert len(files_payload) == 1
    assert files_payload[0]["id"] == uploaded["id"]

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        file_row = await session.execute(
            text(
                "SELECT storage_path, filename, mime_type, file_role "
                "FROM claim_files WHERE id = :id"
            ),
            {"id": uploaded["id"]},
        )
        row = file_row.first()
        assert row is not None
        assert row[1] == "contract.pdf"
        assert row[2] == "application/pdf"
        assert row[3] == "supporting_document"
        assert (Path(settings.claims_upload_dir) / row[0]).is_file()

        event_row = await session.execute(
            text(
                "SELECT event_type, payload_json "
                "FROM claim_events WHERE claim_id = :claim_id ORDER BY id DESC LIMIT 1"
            ),
            {"claim_id": created["claim_id"]},
        )
        event = event_row.first()
        assert event is not None
        assert event[0] == "claim.file_uploaded"
        assert event[1]["file_id"] == uploaded["id"]


async def test_post_claims_files_rejects_unsupported_extension(async_client):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    upload_resp = await async_client.post(
        f"/claims/{created['claim_id']}/files",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        files={"file": ("contract.gif", b"GIF89a", "image/gif")},
    )

    assert upload_resp.status_code == 400
    assert upload_resp.json()["detail"] == "unsupported extension"


@pytest.mark.parametrize(
    ("filename", "mime_type"),
    [
        ("contract.doc", "application/msword"),
        ("contract.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("contract.rtf", "application/rtf"),
        ("scan.jpg", "image/jpeg"),
        ("scan.png", "image/png"),
    ],
)
async def test_post_claims_files_accepts_supported_formats(async_client, filename, mime_type):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    upload_resp = await async_client.post(
        f"/claims/{created['claim_id']}/files",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        files={"file": (filename, b"payload", mime_type)},
    )

    assert upload_resp.status_code == 200
    payload = upload_resp.json()
    assert payload["filename"] == filename
    assert payload["mime_type"] in {
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/rtf",
        "image/jpeg",
        "image/png",
    }


async def test_post_claims_files_accepts_supported_extension_with_nonstandard_mime(async_client):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    upload_resp = await async_client.post(
        f"/claims/{created['claim_id']}/files",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        files={"file": ("contract.pdf", b"%PDF-1.4", "application/x-custom-pdf")},
    )

    assert upload_resp.status_code == 200
    payload = upload_resp.json()
    assert payload["filename"] == "contract.pdf"
    assert payload["mime_type"] == "application/x-custom-pdf"


async def test_post_claims_files_accepts_cyrillic_filename(async_client):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    upload_resp = await async_client.post(
        f"/claims/{created['claim_id']}/files",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        files={"file": ("договор.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert upload_resp.status_code == 200
    payload = upload_resp.json()
    assert payload["filename"] == "договор.pdf"
    assert payload["mime_type"] == "application/pdf"


async def test_delete_claim_file_removes_record_and_storage(async_client, engine):
    settings = get_settings()
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    upload_resp = await async_client.post(
        f"/claims/{created['claim_id']}/files",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        files={"file": ("contract.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert upload_resp.status_code == 200
    uploaded = upload_resp.json()

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        file_row = await session.execute(
            text("SELECT storage_path FROM claim_files WHERE id = :id"),
            {"id": uploaded["id"]},
        )
        row = file_row.first()
        assert row is not None
        storage_path = row[0]
        assert (Path(settings.claims_upload_dir) / storage_path).is_file()

    delete_resp = await async_client.delete(
        f"/claims/{created['claim_id']}/files/{uploaded['id']}",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert delete_resp.status_code == 204

    list_resp = await async_client.get(
        f"/claims/{created['claim_id']}/files",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert list_resp.status_code == 200
    assert list_resp.json() == []

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        file_row = await session.execute(
            text("SELECT id FROM claim_files WHERE id = :id"),
            {"id": uploaded["id"]},
        )
        assert file_row.first() is None

        event_row = await session.execute(
            text(
                "SELECT event_type, payload_json "
                "FROM claim_events WHERE claim_id = :claim_id ORDER BY id DESC LIMIT 1"
            ),
            {"claim_id": created["claim_id"]},
        )
        event = event_row.first()
        assert event is not None
        assert event[0] == "claim.file_deleted"
        assert event[1]["file_id"] == uploaded["id"]

    assert not (Path(settings.claims_upload_dir) / storage_path).exists()
