from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.claims.admin_auth import (
    consume_claims_admin_auth_token,
    create_claims_admin_session,
    get_or_create_claims_admin_user,
    is_claims_admin_email,
    issue_claims_admin_auth_token,
    normalize_claims_admin_email,
)
from product_api.db.session import get_session
from product_api.emailer import send_claims_admin_magic_link
from product_api.settings import get_settings

settings = get_settings()
router = APIRouter()


class ClaimsAdminRequestLinkIn(BaseModel):
    email: EmailStr


class ClaimsAdminConfirmIn(BaseModel):
    token: str


@router.post("/admin/auth/request-link")
async def request_claims_admin_link(
    payload: ClaimsAdminRequestLinkIn,
    session: AsyncSession = Depends(get_session),
):
    email = normalize_claims_admin_email(payload.email)
    if not is_claims_admin_email(settings, email):
        return {"status": "ok"}

    raw_token, expires_at = await issue_claims_admin_auth_token(
        session,
        settings,
        email=email,
    )
    await session.commit()

    link = f"{settings.app_base_url}/admin/auth/confirm?token={raw_token}"
    send_claims_admin_magic_link(settings, email, link)

    if settings.app_env.lower() == "dev":
        return {
            "status": "ok",
            "token": raw_token,
            "expires_at": expires_at.isoformat(),
            "link": link,
        }
    return {"status": "ok"}


@router.post("/admin/auth/confirm")
async def confirm_claims_admin_link(
    payload: ClaimsAdminConfirmIn,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    try:
        email = await consume_claims_admin_auth_token(
            session,
            settings,
            token=payload.token,
        )
        user = await get_or_create_claims_admin_user(session, email=email)
        raw_session, _ = await create_claims_admin_session(
            session,
            settings,
            user_id=user.id,
        )
    except ValueError as exc:
        if str(exc) == "invalid_or_expired_token":
            raise HTTPException(status_code=401, detail="invalid or expired token")
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        detail = str(exc)
        if detail == "inactive_user":
            raise HTTPException(status_code=401, detail="inactive user")
        if detail == "forbidden_admin_email":
            raise HTTPException(status_code=403, detail="forbidden")
        raise HTTPException(status_code=403, detail="forbidden")

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


@router.get("/admin/auth/confirm")
async def confirm_claims_admin_link_get(
    token: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    return await confirm_claims_admin_link(
        ClaimsAdminConfirmIn(token=token),
        response,
        session,
    )
