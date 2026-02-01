import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from product_api.settings import Settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hmac_sha256(secret: str, value: str) -> str:
    return hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def build_expiry(seconds: int) -> datetime:
    return utcnow() + timedelta(seconds=seconds)


def clear_cookie_header(settings: Settings) -> dict[str, str]:
    samesite = settings.cookie_samesite.capitalize()
    parts = [
        f"{settings.session_cookie_name}=",
        "Path=/",
        "Max-Age=0",
        "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
        "HttpOnly",
        f"SameSite={samesite}",
    ]
    if settings.cookie_secure:
        parts.append("Secure")
    return {"Set-Cookie": "; ".join(parts)}
