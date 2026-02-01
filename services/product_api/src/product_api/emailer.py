import logging
import smtplib
from email.message import EmailMessage

from product_api.settings import Settings

logger = logging.getLogger(__name__)


def send_magic_link(settings: Settings, to_email: str, link: str) -> None:
    if settings.app_env.lower() == "dev":
        logger.info("magic_link issued to=%s", to_email)
        return

    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST is required in production")

    msg = EmailMessage()
    msg["Subject"] = "Your login link"
    msg["From"] = settings.email_from
    msg["To"] = to_email
    msg.set_content(f"Use this link to sign in:\n\n{link}\n\nThis link expires soon.")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
