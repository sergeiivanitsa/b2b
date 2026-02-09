import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import build_expiry, generate_raw_token, hmac_sha256, utcnow
from product_api.db.session import get_session
from product_api.models import Session, User
from product_api.repositories import get_user_by_email, write_audit_log
from product_api.settings import get_settings

settings = get_settings()

router = APIRouter()


class InviteAcceptIn(BaseModel):
    token: str


@router.post("/invites/accept")
async def invite_accept(
    payload: InviteAcceptIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    token_hash = hmac_sha256(settings.invite_token_secret, payload.token)
    now = utcnow()

    result = await session.execute(
        text(
            "UPDATE invites SET used_at = :now "
            "WHERE token_hash = :token_hash AND used_at IS NULL AND expires_at > :now "
            "RETURNING id, company_id, email, role"
        ),
        {"token_hash": token_hash, "now": now},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=401, detail="invalid or expired invite")

    invite_id = row[0]
    company_id = row[1]
    email = row[2]
    role = row[3]

    existing = await get_user_by_email(session, email)
    if existing:
        if existing.company_id != company_id:
            raise HTTPException(status_code=409, detail="email already in another company")
        if existing.role == "superadmin":
            raise HTTPException(status_code=403, detail="cannot reassign superadmin")
        existing.role = role
        existing.is_active = True
        await session.commit()
        user_id = existing.id
    else:
        user = User(email=email, role=role, is_active=True, company_id=company_id)
        session.add(user)
        await session.flush()
        user_id = user.id
        await session.commit()

    await write_audit_log(
        session=session,
        actor_user_id=user_id,
        company_id=company_id,
        action="invite.accept",
        target_type="invite",
        target_id=invite_id,
        payload_json=json.dumps({"email": email, "role": role}),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    # Auto-login after invite accept
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


@router.get("/invites/accept")
async def invite_accept_get(
    token: str, request: Request, response: Response, session: AsyncSession = Depends(get_session)
):
    return await invite_accept(InviteAcceptIn(token=token), request, response, session)
