from datetime import datetime

from fastapi import Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import build_expiry, generate_raw_token, hmac_sha256, utcnow
from product_api.models import AuthToken, Session, User
from product_api.rbac import get_current_user
from product_api.settings import Settings, get_settings


def normalize_claims_admin_email(email: str) -> str:
    return email.strip().lower()


def is_claims_admin_email(settings: Settings, email: str) -> bool:
    normalized_email = normalize_claims_admin_email(email)
    return normalized_email in set(settings.claims_admin_emails)


async def require_claims_admin(
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> User:
    if not is_claims_admin_email(settings, current_user.email):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return current_user


async def issue_claims_admin_auth_token(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
) -> tuple[str, datetime]:
    raw_token = generate_raw_token()
    token_hash = hmac_sha256(settings.auth_token_secret, raw_token)
    expires_at = build_expiry(settings.auth_token_ttl_seconds)
    session.add(
        AuthToken(
            email=email,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    await session.flush()
    return raw_token, expires_at


async def consume_claims_admin_auth_token(
    session: AsyncSession,
    settings: Settings,
    *,
    token: str,
) -> str:
    token_hash = hmac_sha256(settings.auth_token_secret, token)
    now = utcnow()
    result = await session.execute(
        text(
            "UPDATE auth_tokens "
            "SET used_at = :now "
            "WHERE token_hash = :token_hash AND used_at IS NULL AND expires_at > :now "
            "RETURNING email"
        ),
        {"token_hash": token_hash, "now": now},
    )
    row = result.first()
    if not row:
        raise ValueError("invalid_or_expired_token")

    email = normalize_claims_admin_email(row[0])
    if not is_claims_admin_email(settings, email):
        raise PermissionError("forbidden_admin_email")
    return email


async def get_or_create_claims_admin_user(
    session: AsyncSession,
    *,
    email: str,
) -> User:
    result = await session.execute(
        select(User).where(User.email == email).limit(1)
    )
    user = result.scalar_one_or_none()
    if user:
        if not user.is_active:
            raise PermissionError("inactive_user")
        return user

    user = User(
        email=email,
        role=None,
        is_active=True,
        company_id=None,
        is_superadmin=False,
    )
    session.add(user)
    await session.flush()
    return user


async def create_claims_admin_session(
    session: AsyncSession,
    settings: Settings,
    *,
    user_id: int,
) -> tuple[str, datetime]:
    raw_session = generate_raw_token()
    session_hash = hmac_sha256(settings.session_secret, raw_session)
    expires_at = build_expiry(settings.session_ttl_seconds)
    session.add(
        Session(
            user_id=user_id,
            session_hash=session_hash,
            expires_at=expires_at,
        )
    )
    await session.flush()
    return raw_session, expires_at
