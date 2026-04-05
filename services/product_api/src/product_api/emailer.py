import logging
import smtplib
from email.message import EmailMessage

from product_api.settings import Settings

logger = logging.getLogger(__name__)


def _send_email_message(settings: Settings, message: EmailMessage) -> None:
    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST is required in production")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)


def send_magic_link(settings: Settings, to_email: str, link: str) -> None:
    if settings.app_env.lower() == "dev":
        logger.info("magic_link issued to=%s", to_email)
        return

    msg = EmailMessage()
    msg["Subject"] = "Your login link"
    msg["From"] = settings.email_from
    msg["To"] = to_email
    msg.set_content(f"Use this link to sign in:\n\n{link}\n\nThis link expires soon.")

    _send_email_message(settings, msg)


def send_claims_admin_magic_link(settings: Settings, to_email: str, link: str) -> None:
    if settings.app_env.lower() == "dev":
        logger.info("claims_admin_magic_link issued to=%s", to_email)
        return

    msg = EmailMessage()
    msg["Subject"] = "Claims admin login link"
    msg["From"] = settings.email_from
    msg["To"] = to_email
    msg.set_content(
        "Use this link to sign in to claims admin:\n\n"
        f"{link}\n\n"
        "This link expires soon."
    )

    _send_email_message(settings, msg)


def send_claim_paid_admin_notification(
    settings: Settings,
    *,
    to_email: str,
    claim_id: int,
    case_type: str | None,
    client_email: str | None,
    price_rub: int,
) -> None:
    if settings.app_env.lower() == "dev":
        logger.info("claims_paid_notification issued to=%s claim_id=%s", to_email, claim_id)
        return

    msg = EmailMessage()
    msg["Subject"] = f"New paid claim #{claim_id}"
    msg["From"] = settings.email_from
    msg["To"] = to_email
    msg.set_content(
        "A new paid claim is ready for review.\n\n"
        f"Claim ID: {claim_id}\n"
        f"Case type: {case_type or 'unknown'}\n"
        f"Client email: {client_email or 'not provided'}\n"
        f"Price (RUB): {price_rub}\n"
    )

    _send_email_message(settings, msg)


def send_claim_final_result_to_client(
    settings: Settings,
    *,
    to_email: str,
    claim_id: int,
    final_text: str,
) -> None:
    if settings.app_env.lower() == "dev":
        logger.info("claims_final_result sent to=%s claim_id=%s", to_email, claim_id)
        return

    msg = EmailMessage()
    msg["Subject"] = f"Final claim result #{claim_id}"
    msg["From"] = settings.email_from
    msg["To"] = to_email
    msg.set_content(
        "Your final pre-trial claim result is ready.\n\n"
        f"Claim ID: {claim_id}\n\n"
        f"{final_text}\n"
    )

    _send_email_message(settings, msg)
