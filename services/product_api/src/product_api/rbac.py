from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import clear_cookie_header, hmac_sha256, utcnow
from product_api.db.session import get_session
from product_api.models import Session, User
from product_api.settings import get_settings

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"


async def _get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _ensure_user(
    session: AsyncSession,
    email: str,
    role: str | None,
    company_id: int | None = None,
    is_superadmin: bool = False,
) -> User:
    if is_superadmin:
        role = None
        company_id = None
    user = await _get_user_by_email(session, email)
    if user:
        updated = False
        if user.role != role:
            user.role = role
            updated = True
        if user.is_superadmin != is_superadmin:
            user.is_superadmin = is_superadmin
            updated = True
        if not user.is_active:
            user.is_active = True
            updated = True
        if user.company_id != company_id:
            user.company_id = company_id
            updated = True
        if updated:
            await session.commit()
        return user

    user = User(
        email=email,
        role=role,
        is_active=True,
        company_id=company_id,
        is_superadmin=is_superadmin,
    )
    session.add(user)
    await session.commit()
    return user


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    settings = get_settings()
    raw_session = request.cookies.get(settings.session_cookie_name)
    if not raw_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    session_hash = hmac_sha256(settings.session_secret, raw_session)
    now = utcnow()
    result = await session.execute(
        select(Session).where(
            Session.session_hash == session_hash,
            Session.expires_at > now,
        )
    )
    session_row = result.scalar_one_or_none()
    if not session_row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
            headers=clear_cookie_header(settings),
        )

    user = await session.get(User, session_row.user_id)
    if not user or not user.is_active:
        await session.delete(session_row)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="inactive user",
            headers=clear_cookie_header(settings),
        )
    return user


def require_role(*roles: str):
    async def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.is_superadmin:
            return current_user
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return current_user

    return _dependency


def require_superadmin():
    async def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.is_superadmin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return current_user

    return _dependency


async def require_company_member(
    company_id: int,
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.is_superadmin:
        return current_user
    if current_user.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return current_user
