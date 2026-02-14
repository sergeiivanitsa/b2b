from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import build_expiry, generate_raw_token, hmac_sha256, utcnow
from product_api.db.session import get_session
from product_api.models import Session, User
from product_api.settings import get_settings

settings = get_settings()

router = APIRouter()


class ConfirmIn(BaseModel):
    token: str


@router.post("/auth/confirm")
async def confirm(payload: ConfirmIn, response: Response, session: AsyncSession = Depends(get_session)):
    token_hash = hmac_sha256(settings.auth_token_secret, payload.token)
    now = utcnow()

    result = await session.execute(
        text(
            "UPDATE auth_tokens "
            "SET used_at = :now "
            "WHERE token_hash = :token_hash AND used_at IS NULL AND expires_at > :now "
            "RETURNING id, email"
        ),
        {"token_hash": token_hash, "now": now},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    email = row[1]

    result_user = await session.execute(
        text("SELECT id, is_active FROM users WHERE email = :email LIMIT 1"),
        {"email": email},
    )
    user_row = result_user.first()
    if user_row:
        user_id = user_row[0]
        is_active = user_row[1]
    else:
        new_user = User(email=email, role=None, is_active=True, company_id=None)
        session.add(new_user)
        await session.flush()
        user_id = new_user.id
        is_active = True

    if not is_active:
        raise HTTPException(status_code=401, detail="inactive user")

    raw_session = generate_raw_token()
    session_hash = hmac_sha256(settings.session_secret, raw_session)
    session_expires = build_expiry(settings.session_ttl_seconds)
    session.add(
        Session(
            user_id=user_id,
            session_hash=session_hash,
            expires_at=session_expires,
        )
    )
    await session.commit()

    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_session,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return {"status": "ok"}


@router.get("/auth/confirm")
async def confirm_get(token: str, response: Response, session: AsyncSession = Depends(get_session)):
    return await confirm(ConfirmIn(token=token), response, session)
