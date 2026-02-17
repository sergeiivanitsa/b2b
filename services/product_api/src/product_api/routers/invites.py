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


def _normalize_invite_role(role: str) -> str:
    if role == "company_admin":
        return "admin"
    if role == "user":
        return "member"
    return role


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
            "RETURNING id, company_id, email, first_name, last_name, role"
        ),
        {"token_hash": token_hash, "now": now},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=401, detail="invalid or expired invite")

   # invite_id = row[0]
   # company_id = row[1]
   # email = row[2]
   # first_name = row[3].strip() if isinstance(row[3], str) and row[3].strip() else None
   # last_name = row[4].strip() if isinstance(row[4], str) and row[4].strip() else None
   # role = _normalize_invite_role(row[5])

    invite_id = row[0]
    company_id = row[1]
    email = row[2]

    # Support legacy test/mocks where row shape was: (id, company_id, email, role)
    if len(row) >= 6:
        first_name_raw = row[3]
        last_name_raw = row[4]
        role_raw = row[5]
    else:
        first_name_raw = None
        last_name_raw = None
        role_raw = row[3]

    first_name = first_name_raw.strip() if isinstance(first_name_raw, str) and first_name_raw.strip() else None
    last_name = last_name_raw.strip() if isinstance(last_name_raw, str) and last_name_raw.strip() else None
    role = _normalize_invite_role(role_raw)


    if role not in ("owner", "admin", "member"):
        raise HTTPException(status_code=400, detail="invalid invite role")

    existing = await get_user_by_email(session, email)
    if existing:
        if existing.is_superadmin:
            raise HTTPException(status_code=403, detail="cannot reassign superadmin")
        if existing.company_id is not None:
            raise HTTPException(status_code=409, detail="email already in a company")
        existing.company_id = company_id
        existing.role = role
        existing.is_active = True
        existing.joined_company_at = now
        if first_name is not None:
            existing.first_name = first_name
        if last_name is not None:
            existing.last_name = last_name
        await session.commit()
        user_id = existing.id
    else:
        user = User(
            email=email,
            role=role,
            is_active=True,
            company_id=company_id,
            first_name=first_name,
            last_name=last_name,
            joined_company_at=now,
        )
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
        payload_json=json.dumps(
            {
                "email": email,
                "role": role,
                "first_name": first_name,
                "last_name": last_name,
            }
        ),
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
