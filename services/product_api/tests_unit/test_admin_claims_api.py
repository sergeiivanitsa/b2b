import pytest

from product_api.claims.admin_auth import require_claims_admin
from product_api.models import User

pytestmark = pytest.mark.asyncio


async def _override_claims_admin():
    return User(
        id=1,
        email="claims-admin@example.com",
        role=None,
        is_active=True,
        company_id=None,
        is_superadmin=False,
    )


async def test_get_admin_claims_list_ok(async_client, monkeypatch):
    from product_api.main import app
    from product_api.routers import admin_claims as admin_claims_router

    async def fake_list_admin_claims(_session, *, status, generation_state, limit, offset):
        assert status == "paid"
        assert generation_state == "ready"
        assert limit == 20
        assert offset == 0
        return [
            {
                "id": 1,
                "status": "paid",
                "generation_state": "ready",
                "manual_review_required": False,
                "case_type": "supply",
                "client_email": "client@example.com",
                "price_rub": 990,
                "has_final_text": False,
                "created_at": None,
                "updated_at": None,
                "paid_at": None,
                "reviewed_at": None,
                "sent_at": None,
            }
        ]

    monkeypatch.setattr(admin_claims_router, "list_admin_claims", fake_list_admin_claims)
    app.dependency_overrides[require_claims_admin] = _override_claims_admin
    try:
        resp = await async_client.get(
            "/admin/claims",
            params={"status": "paid", "generation_state": "ready", "limit": 20, "offset": 0},
        )
    finally:
        app.dependency_overrides.pop(require_claims_admin, None)

    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == 1


async def test_get_admin_claims_list_invalid_filter_returns_400(async_client, monkeypatch):
    from product_api.main import app
    from product_api.routers import admin_claims as admin_claims_router

    async def fake_list_admin_claims(_session, *, status, generation_state, limit, offset):
        raise ValueError("invalid status filter")

    monkeypatch.setattr(admin_claims_router, "list_admin_claims", fake_list_admin_claims)
    app.dependency_overrides[require_claims_admin] = _override_claims_admin
    try:
        resp = await async_client.get("/admin/claims", params={"status": "bad"})
    finally:
        app.dependency_overrides.pop(require_claims_admin, None)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid status filter"


async def test_get_admin_claim_by_id_not_found_404(async_client, monkeypatch):
    from product_api.main import app
    from product_api.routers import admin_claims as admin_claims_router

    async def fake_get_admin_claim(_session, *, claim_id):
        return None

    monkeypatch.setattr(admin_claims_router, "get_admin_claim", fake_get_admin_claim)
    app.dependency_overrides[require_claims_admin] = _override_claims_admin
    try:
        resp = await async_client.get("/admin/claims/123")
    finally:
        app.dependency_overrides.pop(require_claims_admin, None)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "claim not found"


async def test_post_admin_claim_status_success(async_client, mock_session, monkeypatch):
    from product_api.main import app
    from product_api.routers import admin_claims as admin_claims_router

    async def fake_update_admin_claim_status(_session, *, claim_id, target_status):
        assert claim_id == 33
        assert target_status == "in_review"
        return {
            "id": 33,
            "status": "in_review",
            "generation_state": "ready",
            "manual_review_required": False,
            "price_rub": 990,
            "input_text": "Claim text",
            "client_email": None,
            "client_phone": None,
            "case_type": "supply",
            "normalized_data": None,
            "step2": {
                "always_visible_fields": [],
                "missing_fields": [],
                "derived": {
                    "total_paid_amount": 0,
                    "remaining_debt_amount": None,
                    "overdue_days": None,
                    "is_overdue": None,
                },
                "conditional_visibility": {
                    "show_partial_payments": False,
                    "show_penalty_rate": False,
                },
            },
            "risk_flags": [],
            "allowed_blocks": [],
            "blocked_blocks": [],
            "generation_notes": None,
            "generated_preview_text": "",
            "generated_full_text": "",
            "final_text": "",
            "summary_for_admin": None,
            "review_comment": None,
            "created_at": None,
            "updated_at": None,
            "paid_at": None,
            "reviewed_at": None,
            "sent_at": None,
        }

    monkeypatch.setattr(
        admin_claims_router,
        "update_admin_claim_status",
        fake_update_admin_claim_status,
    )
    app.dependency_overrides[require_claims_admin] = _override_claims_admin
    try:
        resp = await async_client.post(
            "/admin/claims/33/status",
            json={"status": "in_review"},
        )
    finally:
        app.dependency_overrides.pop(require_claims_admin, None)

    assert resp.status_code == 200
    assert resp.json()["status"] == "in_review"
    assert mock_session.commit.await_count == 1


async def test_post_admin_claim_status_invalid_transition_returns_409(
    async_client, mock_session, monkeypatch
):
    from product_api.main import app
    from product_api.routers import admin_claims as admin_claims_router

    async def fake_update_admin_claim_status(_session, *, claim_id, target_status):
        raise ValueError("invalid_transition")

    monkeypatch.setattr(
        admin_claims_router,
        "update_admin_claim_status",
        fake_update_admin_claim_status,
    )
    app.dependency_overrides[require_claims_admin] = _override_claims_admin
    try:
        resp = await async_client.post(
            "/admin/claims/33/status",
            json={"status": "sent"},
        )
    finally:
        app.dependency_overrides.pop(require_claims_admin, None)

    assert resp.status_code == 409
    assert resp.json()["detail"] == "invalid_transition"
    assert mock_session.commit.await_count == 0


async def test_post_admin_claim_status_sent_requires_send_action(async_client, mock_session, monkeypatch):
    from product_api.main import app
    from product_api.routers import admin_claims as admin_claims_router

    async def fake_update_admin_claim_status(_session, *, claim_id, target_status):
        raise ValueError("use_send_action")

    monkeypatch.setattr(
        admin_claims_router,
        "update_admin_claim_status",
        fake_update_admin_claim_status,
    )
    app.dependency_overrides[require_claims_admin] = _override_claims_admin
    try:
        resp = await async_client.post(
            "/admin/claims/33/status",
            json={"status": "sent"},
        )
    finally:
        app.dependency_overrides.pop(require_claims_admin, None)

    assert resp.status_code == 409
    assert resp.json()["detail"] == "use_send_action"
    assert mock_session.commit.await_count == 0


async def test_post_admin_claim_final_text_success(async_client, mock_session, monkeypatch):
    from product_api.main import app
    from product_api.routers import admin_claims as admin_claims_router

    async def fake_update_admin_claim_final_text(_session, *, claim_id, final_text):
        assert claim_id == 34
        assert final_text == "Final text"
        return {
            "id": 34,
            "status": "in_review",
            "generation_state": "ready",
            "manual_review_required": False,
            "price_rub": 990,
            "input_text": "Claim text",
            "client_email": None,
            "client_phone": None,
            "case_type": "services",
            "normalized_data": None,
            "step2": {
                "always_visible_fields": [],
                "missing_fields": [],
                "derived": {
                    "total_paid_amount": 0,
                    "remaining_debt_amount": None,
                    "overdue_days": None,
                    "is_overdue": None,
                },
                "conditional_visibility": {
                    "show_partial_payments": False,
                    "show_penalty_rate": False,
                },
            },
            "risk_flags": [],
            "allowed_blocks": [],
            "blocked_blocks": [],
            "generation_notes": None,
            "generated_preview_text": "",
            "generated_full_text": "",
            "final_text": "Final text",
            "summary_for_admin": None,
            "review_comment": None,
            "created_at": None,
            "updated_at": None,
            "paid_at": None,
            "reviewed_at": None,
            "sent_at": None,
        }

    monkeypatch.setattr(
        admin_claims_router,
        "update_admin_claim_final_text",
        fake_update_admin_claim_final_text,
    )
    app.dependency_overrides[require_claims_admin] = _override_claims_admin
    try:
        resp = await async_client.post(
            "/admin/claims/34/final-text",
            json={"final_text": "Final text"},
        )
    finally:
        app.dependency_overrides.pop(require_claims_admin, None)

    assert resp.status_code == 200
    assert resp.json()["final_text"] == "Final text"
    assert mock_session.commit.await_count == 1


async def test_get_admin_claim_files_not_found_returns_404(async_client, monkeypatch):
    from product_api.main import app
    from product_api.routers import admin_claims as admin_claims_router

    async def fake_get_admin_claim_files(_session, *, claim_id):
        raise LookupError("claim not found")

    monkeypatch.setattr(
        admin_claims_router,
        "get_admin_claim_files",
        fake_get_admin_claim_files,
    )
    app.dependency_overrides[require_claims_admin] = _override_claims_admin
    try:
        resp = await async_client.get("/admin/claims/500/files")
    finally:
        app.dependency_overrides.pop(require_claims_admin, None)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "claim not found"


async def test_post_admin_claim_send_success(async_client, mock_session, monkeypatch):
    from product_api.main import app
    from product_api.models import Claim
    from product_api.routers import admin_claims as admin_claims_router

    claim = Claim(
        id=90,
        status="in_review",
        generation_state="ready",
        price_rub=990,
        input_text="Claim text",
        edit_token_hash="hidden",
        client_email="client@example.com",
        final_text="Final result",
    )

    async def fake_get_claim_by_id(_session, claim_id):
        assert claim_id == 90
        return claim

    def fake_send_claim_final_result(_settings, *, claim_id, client_email, final_text):
        assert claim_id == 90
        assert client_email == "client@example.com"
        assert final_text == "Final result"
        return {"to_email": client_email, "final_text_length": len(final_text)}

    async def fake_send_admin_claim_final_result(_session, *, claim_id, to_email):
        assert claim_id == 90
        assert to_email == "client@example.com"
        return {
            "id": 90,
            "status": "sent",
            "generation_state": "ready",
            "manual_review_required": False,
            "price_rub": 990,
            "input_text": "Claim text",
            "client_email": "client@example.com",
            "client_phone": None,
            "case_type": "supply",
            "normalized_data": None,
            "step2": {
                "always_visible_fields": [],
                "missing_fields": [],
                "derived": {
                    "total_paid_amount": 0,
                    "remaining_debt_amount": None,
                    "overdue_days": None,
                    "is_overdue": None,
                },
                "conditional_visibility": {
                    "show_partial_payments": False,
                    "show_penalty_rate": False,
                },
            },
            "risk_flags": [],
            "allowed_blocks": [],
            "blocked_blocks": [],
            "generation_notes": None,
            "generated_preview_text": "",
            "generated_full_text": "",
            "final_text": "Final result",
            "summary_for_admin": None,
            "review_comment": None,
            "created_at": None,
            "updated_at": None,
            "paid_at": None,
            "reviewed_at": None,
            "sent_at": "2026-03-01T00:00:00+00:00",
        }

    monkeypatch.setattr(admin_claims_router, "get_claim_by_id", fake_get_claim_by_id)
    monkeypatch.setattr(admin_claims_router, "send_claim_final_result", fake_send_claim_final_result)
    monkeypatch.setattr(
        admin_claims_router,
        "send_admin_claim_final_result",
        fake_send_admin_claim_final_result,
    )

    app.dependency_overrides[require_claims_admin] = _override_claims_admin
    try:
        resp = await async_client.post("/admin/claims/90/send")
    finally:
        app.dependency_overrides.pop(require_claims_admin, None)

    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"
    assert mock_session.commit.await_count == 1


async def test_post_admin_claim_send_notification_failure_returns_502(
    async_client, mock_session, monkeypatch
):
    from product_api.main import app
    from product_api.claims.notifications import NotificationSendError
    from product_api.models import Claim
    from product_api.routers import admin_claims as admin_claims_router

    claim = Claim(
        id=91,
        status="in_review",
        generation_state="ready",
        price_rub=990,
        input_text="Claim text",
        edit_token_hash="hidden",
        client_email="client@example.com",
        final_text="Final result",
    )

    async def fake_get_claim_by_id(_session, claim_id):
        return claim

    def fake_send_claim_final_result(_settings, *, claim_id, client_email, final_text):
        raise NotificationSendError(
            "client_send_failed",
            {"to_email": client_email, "error": "smtp down"},
        )

    async def fake_append_admin_claim_send_failed_event(
        _session,
        *,
        claim_id,
        to_email,
        error_code,
        error_payload,
    ):
        assert claim_id == 91
        assert to_email == "client@example.com"
        assert error_code == "client_send_failed"
        assert error_payload["error"] == "smtp down"

    monkeypatch.setattr(admin_claims_router, "get_claim_by_id", fake_get_claim_by_id)
    monkeypatch.setattr(admin_claims_router, "send_claim_final_result", fake_send_claim_final_result)
    monkeypatch.setattr(
        admin_claims_router,
        "append_admin_claim_send_failed_event",
        fake_append_admin_claim_send_failed_event,
    )

    app.dependency_overrides[require_claims_admin] = _override_claims_admin
    try:
        resp = await async_client.post("/admin/claims/91/send")
    finally:
        app.dependency_overrides.pop(require_claims_admin, None)

    assert resp.status_code == 502
    assert resp.json()["detail"] == "client_send_failed"
    assert mock_session.commit.await_count == 1
