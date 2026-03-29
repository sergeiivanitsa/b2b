import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.models import Claim, ClaimFile
from product_api.settings import get_settings

from .utils import create_session_cookie, create_user

pytestmark = pytest.mark.asyncio


async def _create_claim(
    session: AsyncSession,
    *,
    status: str = "paid",
    generation_state: str = "ready",
) -> Claim:
    claim = Claim(
        status=status,
        generation_state=generation_state,
        price_rub=990,
        input_text="OOO Vector did not pay for delivery",
        edit_token_hash=f"hash-{uuid.uuid4().hex}",
    )
    session.add(claim)
    await session.commit()
    await session.refresh(claim)
    return claim


async def _create_claims_admin_cookie(session: AsyncSession) -> str:
    user = await create_user(
        session,
        "claims-admin@example.com",
        role=None,
        company_id=None,
        is_superadmin=False,
    )
    return await create_session_cookie(session, user.id)


async def test_admin_claims_list_and_detail(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        cookie = await _create_claims_admin_cookie(session)
        paid_claim = await _create_claim(session, status="paid", generation_state="ready")
        await _create_claim(session, status="draft", generation_state="insufficient_data")

    cookies = {settings.session_cookie_name: cookie}
    list_resp = await async_client.get(
        "/admin/claims",
        params={"status": "paid"},
        cookies=cookies,
    )
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert len(list_payload["items"]) == 1
    assert list_payload["items"][0]["id"] == paid_claim.id
    assert list_payload["items"][0]["status"] == "paid"

    detail_resp = await async_client.get(
        f"/admin/claims/{paid_claim.id}",
        cookies=cookies,
    )
    assert detail_resp.status_code == 200
    detail_payload = detail_resp.json()
    assert detail_payload["id"] == paid_claim.id
    assert detail_payload["status"] == "paid"
    assert "edit_token_hash" not in detail_payload


async def test_admin_claim_status_transition_and_files(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        cookie = await _create_claims_admin_cookie(session)
        claim = await _create_claim(session, status="paid", generation_state="ready")
        session.add(
            ClaimFile(
                claim_id=claim.id,
                filename="contract.pdf",
                storage_path="claims/test/contract.pdf",
                mime_type="application/pdf",
                file_role="contract",
            )
        )
        await session.commit()

    cookies = {settings.session_cookie_name: cookie}
    in_review_resp = await async_client.post(
        f"/admin/claims/{claim.id}/status",
        json={"status": "in_review"},
        cookies=cookies,
    )
    assert in_review_resp.status_code == 200
    assert in_review_resp.json()["status"] == "in_review"
    assert in_review_resp.json()["reviewed_at"] is not None

    sent_resp = await async_client.post(
        f"/admin/claims/{claim.id}/status",
        json={"status": "sent"},
        cookies=cookies,
    )
    assert sent_resp.status_code == 200
    assert sent_resp.json()["status"] == "sent"
    assert sent_resp.json()["sent_at"] is not None

    files_resp = await async_client.get(
        f"/admin/claims/{claim.id}/files",
        cookies=cookies,
    )
    assert files_resp.status_code == 200
    files_payload = files_resp.json()
    assert len(files_payload) == 1
    assert files_payload[0]["filename"] == "contract.pdf"
    assert "storage_path" not in files_payload[0]

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text("SELECT status, reviewed_at, sent_at FROM claims WHERE id = :id"),
            {"id": claim.id},
        )
        row = claim_row.first()
        assert row is not None
        assert row[0] == "sent"
        assert row[1] is not None
        assert row[2] is not None

        events_row = await session.execute(
            text(
                "SELECT COUNT(*) FROM claim_events "
                "WHERE claim_id = :claim_id AND event_type = 'claim.admin_status_updated'"
            ),
            {"claim_id": claim.id},
        )
        assert int(events_row.scalar_one()) == 2


async def test_admin_claim_final_text_update(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        cookie = await _create_claims_admin_cookie(session)
        claim = await _create_claim(session, status="in_review", generation_state="ready")

    cookies = {settings.session_cookie_name: cookie}
    resp = await async_client.post(
        f"/admin/claims/{claim.id}/final-text",
        json={"final_text": "  Final claim text  "},
        cookies=cookies,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["final_text"] == "Final claim text"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text("SELECT final_text FROM claims WHERE id = :id"),
            {"id": claim.id},
        )
        assert claim_row.scalar_one() == "Final claim text"

        event_row = await session.execute(
            text(
                "SELECT event_type, payload_json "
                "FROM claim_events WHERE claim_id = :claim_id ORDER BY id DESC LIMIT 1"
            ),
            {"claim_id": claim.id},
        )
        event = event_row.first()
        assert event is not None
        assert event[0] == "claim.admin_final_text_updated"
        assert event[1]["final_text_length"] == len("Final claim text")


async def test_admin_claims_forbidden_for_non_whitelisted_user(async_client, engine):
    settings = get_settings()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        outsider = await create_user(
            session,
            "outsider@example.com",
            role=None,
            company_id=None,
            is_superadmin=False,
        )
        outsider_cookie = await create_session_cookie(session, outsider.id)

    resp = await async_client.get(
        "/admin/claims",
        cookies={settings.session_cookie_name: outsider_cookie},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden"
