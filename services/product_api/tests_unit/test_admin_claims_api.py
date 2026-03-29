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
