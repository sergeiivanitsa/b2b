from dataclasses import dataclass
from typing import Any

from product_api.emailer import (
    send_claim_final_result_to_client,
    send_claim_paid_admin_notification,
)
from product_api.settings import Settings


@dataclass
class NotificationSendError(Exception):
    code: str
    payload: dict[str, Any]

    def __str__(self) -> str:
        return self.code


def _dedupe_emails(emails: list[str]) -> list[str]:
    deduped: list[str] = []
    for item in emails:
        normalized = item.strip().lower()
        if not normalized:
            continue
        if normalized not in deduped:
            deduped.append(normalized)
    return deduped


def notify_admins_about_paid_claim(
    settings: Settings,
    *,
    claim_id: int,
    case_type: str | None,
    client_email: str | None,
    price_rub: int,
) -> dict[str, Any]:
    recipients = _dedupe_emails(settings.claims_admin_emails)
    if not recipients:
        return {
            "recipients": [],
            "sent_recipients": [],
            "failed_recipients": [],
        }

    sent_recipients: list[str] = []
    failed_recipients: list[dict[str, str]] = []
    for recipient in recipients:
        try:
            send_claim_paid_admin_notification(
                settings,
                to_email=recipient,
                claim_id=claim_id,
                case_type=case_type,
                client_email=client_email,
                price_rub=price_rub,
            )
            sent_recipients.append(recipient)
        except Exception as exc:  # pragma: no cover - exercised via monkeypatch/tests
            failed_recipients.append(
                {
                    "email": recipient,
                    "error": str(exc),
                }
            )

    payload = {
        "recipients": recipients,
        "sent_recipients": sent_recipients,
        "failed_recipients": failed_recipients,
    }
    if failed_recipients:
        raise NotificationSendError("admin_notification_failed", payload)
    return payload


def send_claim_final_result(
    settings: Settings,
    *,
    claim_id: int,
    client_email: str,
    final_text: str,
) -> dict[str, Any]:
    try:
        send_claim_final_result_to_client(
            settings,
            to_email=client_email,
            claim_id=claim_id,
            final_text=final_text,
        )
    except Exception as exc:  # pragma: no cover - exercised via monkeypatch/tests
        raise NotificationSendError(
            "client_send_failed",
            {
                "to_email": client_email,
                "error": str(exc),
            },
        ) from exc

    return {
        "to_email": client_email,
        "final_text_length": len(final_text),
    }
