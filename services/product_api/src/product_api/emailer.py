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
