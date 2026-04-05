import pytest

from product_api.claims.notifications import (
    NotificationSendError,
    notify_admins_about_paid_claim,
    send_claim_final_result,
)
from product_api.settings import get_settings

pytestmark = pytest.mark.asyncio


async def test_notify_admins_about_paid_claim_success(monkeypatch):
    sent: list[str] = []
    settings = get_settings().model_copy(
        update={"claims_admin_emails": ["claims-admin@example.com", "CLAIMS-ADMIN@example.com"]}
    )

    def fake_send_claim_paid_admin_notification(
        _settings, *, to_email, claim_id, case_type, client_email, price_rub
    ):
        sent.append(to_email)

    monkeypatch.setattr(
        "product_api.claims.notifications.send_claim_paid_admin_notification",
        fake_send_claim_paid_admin_notification,
    )

    payload = notify_admins_about_paid_claim(
        settings,
        claim_id=101,
        case_type="supply",
        client_email="client@example.com",
        price_rub=990,
    )

    assert payload["recipients"] == ["claims-admin@example.com"]
    assert payload["sent_recipients"] == ["claims-admin@example.com"]
    assert payload["failed_recipients"] == []
    assert sent == ["claims-admin@example.com"]


async def test_notify_admins_about_paid_claim_raises_on_failure(monkeypatch):
    settings = get_settings().model_copy(
        update={"claims_admin_emails": ["claims-admin@example.com"]}
    )

    def fake_send_claim_paid_admin_notification(
        _settings, *, to_email, claim_id, case_type, client_email, price_rub
    ):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(
        "product_api.claims.notifications.send_claim_paid_admin_notification",
        fake_send_claim_paid_admin_notification,
    )

    with pytest.raises(NotificationSendError, match="admin_notification_failed"):
        notify_admins_about_paid_claim(
            settings,
            claim_id=101,
            case_type="supply",
            client_email="client@example.com",
            price_rub=990,
        )


async def test_send_claim_final_result_success(monkeypatch):
    settings = get_settings()

    def fake_send_claim_final_result_to_client(_settings, *, to_email, claim_id, final_text):
        return None

    monkeypatch.setattr(
        "product_api.claims.notifications.send_claim_final_result_to_client",
        fake_send_claim_final_result_to_client,
    )

    payload = send_claim_final_result(
        settings,
        claim_id=202,
        client_email="client@example.com",
        final_text="Final text",
    )

    assert payload["to_email"] == "client@example.com"
    assert payload["final_text_length"] == len("Final text")


async def test_send_claim_final_result_failure_raises(monkeypatch):
    settings = get_settings()

    def fake_send_claim_final_result_to_client(_settings, *, to_email, claim_id, final_text):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(
        "product_api.claims.notifications.send_claim_final_result_to_client",
        fake_send_claim_final_result_to_client,
    )

    with pytest.raises(NotificationSendError, match="client_send_failed"):
        send_claim_final_result(
            settings,
            claim_id=202,
            client_email="client@example.com",
            final_text="Final text",
        )
