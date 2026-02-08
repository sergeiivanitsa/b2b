import json
import logging
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import build_expiry, generate_raw_token, hmac_sha256, utcnow
from product_api.bootstrap import ensure_superadmin
from product_api.db.session import get_session
from product_api.emailer import send_magic_link
from product_api.gateway_client import GatewayError, send_chat, stream_chat
from product_api.logging_config import configure_logging
from product_api.models import AuthToken, Conversation, Ledger, Message, Session, User
from product_api.request_id import REQUEST_ID_HEADER, set_request_id
from product_api.rbac import get_current_user, require_role
from product_api.repositories import (
    add_ledger_entry,
    create_company,
    create_conversation,
    create_invite,
    get_user_by_email,
    write_audit_log,
)
from product_api.rate_limit import RateLimitConfig, RateLimiter
from product_api.settings import get_settings
from shared.constants import MODEL_GPT_5_2
from shared.schemas import ChatMessage, ChatMetadata, ChatRequest

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Product API")
rate_limiter = RateLimiter(RateLimitConfig())
chat_company_limiter = RateLimiter(
    RateLimitConfig(max_requests=settings.rate_limit_company_rpm, window_seconds=60)
)
chat_user_limiter = RateLimiter(
    RateLimitConfig(max_requests=settings.rate_limit_user_rpm, window_seconds=60)
)
chat_ip_limiter = RateLimiter(
    RateLimitConfig(max_requests=settings.rate_limit_ip_rpm, window_seconds=60)
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    set_request_id(request_id)
    if settings.app_env.lower() == "prod":
        if request.url.path in ("/docs", "/openapi.json"):
            return Response(status_code=404)
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


@app.on_event("startup")
async def startup_event():
    await ensure_superadmin()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/internal/db-ping")
async def db_ping(session: AsyncSession = Depends(get_session)):
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="db unavailable")
    return {"status": "ok"}


class RequestLinkIn(BaseModel):
    email: EmailStr


class ConfirmIn(BaseModel):
    token: str


@app.post("/auth/request-link")
async def request_link(
    payload: RequestLinkIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    ip = request.client.host if request.client else "unknown"
    key = f"{payload.email.lower()}:{ip}"
    if not rate_limiter.allow(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "rate limit"},
        )

    email = payload.email.lower()
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
    await session.commit()

    link = f"{settings.app_base_url}/auth/confirm?token={raw_token}"
    send_magic_link(settings, email, link)

    # Dev-only: return token directly.
    if settings.app_env.lower() == "dev":
        return {
            "status": "ok",
            "token": raw_token,
            "expires_at": expires_at.isoformat(),
            "link": link,
        }
    return {"status": "ok"}


@app.post("/auth/confirm")
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
        new_user = User(email=email, role="user", is_active=True, company_id=None)
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


@app.get("/auth/confirm")
async def confirm_get(token: str, response: Response, session: AsyncSession = Depends(get_session)):
    return await confirm(ConfirmIn(token=token), response, session)


@app.post("/auth/logout")
async def logout(response: Response, request: Request, session: AsyncSession = Depends(get_session)):
    raw_session = request.cookies.get(settings.session_cookie_name)
    if raw_session:
        session_hash = hmac_sha256(settings.session_secret, raw_session)
        await session.execute(
            text("DELETE FROM sessions WHERE session_hash = :session_hash"),
            {"session_hash": session_hash},
        )
        await session.commit()

    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"status": "ok"}


class CompanyCreateIn(BaseModel):
    name: str


class AdminInviteIn(BaseModel):
    email: EmailStr


class CreditsIn(BaseModel):
    amount: int
    reason: str
    idempotency_key: str | None = None


@app.post("/admin/companies")
async def admin_create_company(
    payload: CompanyCreateIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("superadmin")),
):
    company = await create_company(session, payload.name)
    await write_audit_log(
        session=session,
        actor_user_id=current_user.id,
        company_id=company.id,
        action="company.create",
        target_type="company",
        target_id=company.id,
        payload_json=json.dumps({"name": payload.name}),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"id": company.id, "name": company.name}


@app.post("/admin/companies/{company_id}/admins")
async def admin_invite_company_admin(
    company_id: int,
    payload: AdminInviteIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("superadmin")),
):
    email = payload.email.lower()
    user = await get_user_by_email(session, email)
    token = None
    if user:
        if user.role == "superadmin":
            raise HTTPException(status_code=403, detail="cannot reassign superadmin")
        if user.company_id and user.company_id != company_id:
            raise HTTPException(status_code=409, detail="email already in another company")
        user.company_id = company_id
        user.role = "company_admin"
        user.is_active = True
        await session.commit()
    else:
        raw_token = generate_raw_token()
        token_hash = hmac_sha256(settings.invite_token_secret, raw_token)
        expires_at = build_expiry(settings.invite_ttl_seconds)
        await create_invite(
            session=session,
            company_id=company_id,
            email=email,
            token_hash=token_hash,
            expires_at=expires_at,
            invited_by_user_id=current_user.id,
            role="company_admin",
        )
        invite_link = f"{settings.app_base_url}/invites/accept?token={raw_token}"
        send_magic_link(settings, email, invite_link)
        token = raw_token if settings.app_env.lower() == "dev" else None

    await write_audit_log(
        session=session,
        actor_user_id=current_user.id,
        company_id=company_id,
        action="company.admin_invite",
        target_type="user",
        target_id=user.id if user else None,
        payload_json=json.dumps({"email": email, "role": "company_admin"}),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    resp = {"status": "ok"}
    if token:
        resp["token"] = token
        resp["link"] = invite_link
    return resp


@app.post("/admin/companies/{company_id}/credits")
async def admin_add_credits(
    company_id: int,
    payload: CreditsIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("superadmin")),
):
    key = payload.idempotency_key or generate_raw_token()
    entry = await add_ledger_entry(
        session=session,
        company_id=company_id,
        user_id=None,
        delta=payload.amount,
        reason=payload.reason,
        idempotency_key=key,
    )
    await write_audit_log(
        session=session,
        actor_user_id=current_user.id,
        company_id=company_id,
        action="credits.add",
        target_type="ledger",
        target_id=entry.id,
        payload_json=json.dumps({"amount": payload.amount, "reason": payload.reason}),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"status": "ok", "id": entry.id}


@app.get("/admin/companies/{company_id}")
async def admin_get_company(
    company_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("superadmin")),
):
    result = await session.execute(text("SELECT id, name FROM companies WHERE id = :id"), {"id": company_id})
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="company not found")
    company = {"id": row[0], "name": row[1]}

    balance_result = await session.execute(
        text("SELECT COALESCE(SUM(delta),0) FROM ledger WHERE company_id = :id"),
        {"id": company_id},
    )
    balance = balance_result.scalar_one()

    last_result = await session.execute(
        text(
            "SELECT id, delta, reason, created_at FROM ledger "
            "WHERE company_id = :id ORDER BY created_at DESC LIMIT 1"
        ),
        {"id": company_id},
    )
    last_row = last_result.first()
    last_entry = (
        {
            "id": last_row[0],
            "delta": last_row[1],
            "reason": last_row[2],
            "created_at": last_row[3].isoformat(),
        }
        if last_row
        else None
    )

    await write_audit_log(
        session=session,
        actor_user_id=current_user.id,
        company_id=company_id,
        action="company.view",
        target_type="company",
        target_id=company_id,
        payload_json=json.dumps({}),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"company": company, "balance": balance, "last_ledger_entry": last_entry}


class InviteIn(BaseModel):
    email: EmailStr


class CompanyCreditsIn(BaseModel):
    amount: int
    reason: str
    idempotency_key: str | None = None
    user_id: int | None = None


class InviteAcceptIn(BaseModel):
    token: str


class ChatIn(BaseModel):
    conversation_id: int | None = None
    client_message_id: str
    content: str
    stream: bool = False


def _require_company_id(current_user: User) -> int:
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="company_id required")
    return current_user.company_id


async def _get_or_create_assistant_stub(
    session: AsyncSession, conversation_id: int, parent_message_id: int
) -> Message:
    result = await session.execute(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.parent_message_id == parent_message_id,
            Message.role == "assistant",
        )
    )
    assistant_message = result.scalar_one_or_none()
    if assistant_message:
        return assistant_message

    assistant_message = Message(
        conversation_id=conversation_id,
        parent_message_id=parent_message_id,
        role="assistant",
        status="pending",
        model=MODEL_GPT_5_2,
        content="",
    )
    session.add(assistant_message)
    await session.commit()
    return assistant_message


async def _load_chat_context(
    session: AsyncSession, conversation_id: int, limit: int
) -> list[ChatMessage]:
    result = await session.execute(
        text(
            "SELECT role, content FROM messages "
            "WHERE conversation_id = :cid AND status = 'completed' "
            "ORDER BY created_at DESC LIMIT :limit"
        ),
        {"cid": conversation_id, "limit": limit},
    )
    rows = list(result.fetchall())
    messages = [ChatMessage(role=row[0], content=row[1]) for row in reversed(rows)]
    return messages


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/company/users")
async def company_users(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("company_admin")),
):
    company_id = _require_company_id(current_user)
    result = await session.execute(select(User).where(User.company_id == company_id))
    users = [
        {
            "id": u.id,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
        }
        for u in result.scalars().all()
    ]
    await write_audit_log(
        session=session,
        actor_user_id=current_user.id,
        company_id=company_id,
        action="company.users.list",
        target_type="company",
        target_id=company_id,
        payload_json=json.dumps({}),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"users": users}


@app.post("/company/invites")
async def company_invite_user(
    payload: InviteIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("company_admin")),
):
    company_id = _require_company_id(current_user)
    email = payload.email.lower()
    existing = await get_user_by_email(session, email)
    if existing:
        if existing.role == "superadmin":
            raise HTTPException(status_code=403, detail="cannot reassign superadmin")
        if existing.company_id and existing.company_id != company_id:
            raise HTTPException(status_code=409, detail="email already in another company")
    raw_token = generate_raw_token()
    token_hash = hmac_sha256(settings.invite_token_secret, raw_token)
    expires_at = build_expiry(settings.invite_ttl_seconds)
    try:
        await create_invite(
            session=session,
            company_id=company_id,
            email=email,
            token_hash=token_hash,
            expires_at=expires_at,
            invited_by_user_id=current_user.id,
            role="user",
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="active invite already exists")

    invite_link = f"{settings.app_base_url}/invites/accept?token={raw_token}"
    send_magic_link(settings, email, invite_link)

    await write_audit_log(
        session=session,
        actor_user_id=current_user.id,
        company_id=company_id,
        action="invite.create",
        target_type="invite",
        target_id=None,
        payload_json=json.dumps({"email": email, "role": "user"}),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    resp = {"status": "ok"}
    if settings.app_env.lower() == "dev":
        resp["token"] = raw_token
        resp["link"] = invite_link
    return resp


@app.get("/company/invites")
async def company_invites(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("company_admin")),
):
    company_id = _require_company_id(current_user)
    now = utcnow()
    result = await session.execute(
        text(
            "SELECT id, email, role, expires_at, created_at "
            "FROM invites WHERE company_id = :cid AND used_at IS NULL AND expires_at > :now "
            "ORDER BY created_at DESC"
        ),
        {"cid": company_id, "now": now},
    )
    invites = [
        {
            "id": row[0],
            "email": row[1],
            "role": row[2],
            "expires_at": row[3].isoformat(),
            "created_at": row[4].isoformat(),
        }
        for row in result.fetchall()
    ]
    await write_audit_log(
        session=session,
        actor_user_id=current_user.id,
        company_id=company_id,
        action="company.invites.list",
        target_type="company",
        target_id=company_id,
        payload_json=json.dumps({}),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"invites": invites}


@app.post("/invites/accept")
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


@app.get("/invites/accept")
async def invite_accept_get(token: str, request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    return await invite_accept(InviteAcceptIn(token=token), request, response, session)


@app.post("/v1/chat")
async def chat_v1(
    payload: ChatIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    company_id = _require_company_id(current_user)
    logger.info(
        "chat request company_id=%s user_id=%s conversation_id=%s client_message_id=%s stream=%s",
        company_id,
        current_user.id,
        payload.conversation_id,
        payload.client_message_id,
        payload.stream,
    )
    ip = request.client.host if request.client else "unknown"
    if not chat_company_limiter.allow(f"company:{company_id}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "rate limit"},
        )
    if not chat_user_limiter.allow(f"user:{current_user.id}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "rate limit"},
        )
    if not chat_ip_limiter.allow(f"ip:{ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "rate limit"},
        )
    conversation_id = payload.conversation_id
    balance_checked = False
    content_checked = False

    if conversation_id is not None:
        result = await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.company_id == company_id,
                Conversation.user_id == current_user.id,
            )
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="conversation not found")
    else:
        if len(payload.content) > settings.max_message_chars:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "content_too_long", "message": "content too long"},
            )
        content_checked = True
        balance_result = await session.execute(
            text("SELECT COALESCE(SUM(delta),0) FROM ledger WHERE company_id = :cid"),
            {"cid": company_id},
        )
        balance = balance_result.scalar_one()
        if balance <= 0:
            raise HTTPException(status_code=402, detail="insufficient credits")
        balance_checked = True

        conversation = await create_conversation(
            session=session,
            company_id=company_id,
            user_id=current_user.id,
        )
        conversation_id = conversation.id

    existing = await session.execute(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.client_message_id == payload.client_message_id,
        )
    )
    user_message = existing.scalar_one_or_none()
    if user_message:
        assistant_message = await _get_or_create_assistant_stub(
            session=session,
            conversation_id=conversation_id,
            parent_message_id=user_message.id,
        )
        if assistant_message.status == "completed":
            if payload.stream:
                async def single_final():
                    yield _format_sse(
                        "final",
                        {
                            "text": assistant_message.content,
                            "usage": assistant_message.usage_json,
                        },
                    )
                return StreamingResponse(single_final(), media_type="text/event-stream")
            return {
                "conversation_id": conversation_id,
                "user_message_id": user_message.id,
                "assistant_message_id": assistant_message.id,
                "assistant_status": assistant_message.status,
                "client_message_id": payload.client_message_id,
            }
    else:
        if not content_checked and len(payload.content) > settings.max_message_chars:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "content_too_long", "message": "content too long"},
            )
        if not balance_checked:
            balance_result = await session.execute(
                text("SELECT COALESCE(SUM(delta),0) FROM ledger WHERE company_id = :cid"),
                {"cid": company_id},
            )
            balance = balance_result.scalar_one()
            if balance <= 0:
                raise HTTPException(status_code=402, detail="insufficient credits")

        try:
            user_message = Message(
                conversation_id=conversation_id,
                role="user",
                status="completed",
                model=None,
                content=payload.content,
                client_message_id=payload.client_message_id,
            )
            session.add(user_message)
            await session.flush()

            assistant_message = Message(
                conversation_id=conversation_id,
                parent_message_id=user_message.id,
                role="assistant",
                status="pending",
                model=MODEL_GPT_5_2,
                content="",
            )
            session.add(assistant_message)

            ledger_entry = Ledger(
                company_id=company_id,
                user_id=current_user.id,
                message_id=user_message.id,
                delta=-1,
                reason="chat_message",
                idempotency_key=f"msg:{user_message.id}",
            )
            session.add(ledger_entry)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await session.execute(
                select(Message).where(
                    Message.conversation_id == conversation_id,
                    Message.client_message_id == payload.client_message_id,
                )
            )
            user_message = existing.scalar_one_or_none()
            if not user_message:
                raise HTTPException(status_code=409, detail="message conflict")
            assistant_message = await _get_or_create_assistant_stub(
                session=session,
                conversation_id=conversation_id,
                parent_message_id=user_message.id,
            )

    messages = await _load_chat_context(
        session=session,
        conversation_id=conversation_id,
        limit=settings.chat_context_limit,
    )
    request_payload = ChatRequest(
        messages=messages,
        model=MODEL_GPT_5_2,
        stream=payload.stream,
        timeout=settings.gateway_timeout_seconds,
        metadata=ChatMetadata(
            company_id=company_id,
            user_id=current_user.id,
            conversation_id=conversation_id,
            message_id=user_message.id,
        ),
    )
    if payload.stream:
        async def event_stream():
            buffer_text = ""
            try:
                async for event, data in stream_chat(settings, request_payload):
                    if await request.is_disconnected():
                        assistant_message.status = "error"
                        assistant_message.content = buffer_text
                        await session.commit()
                        return
                    if event == "delta":
                        delta_text = data.get("text", "")
                        if delta_text:
                            buffer_text += delta_text
                        yield _format_sse("delta", {"text": delta_text})
                    elif event == "final":
                        final_text = data.get("text") or buffer_text
                        usage = data.get("usage")
                        assistant_message.status = "completed"
                        assistant_message.content = final_text
                        assistant_message.model = request_payload.model
                        assistant_message.usage_json = usage
                        await session.commit()
                        yield _format_sse("final", {"text": final_text, "usage": usage})
                        return
                    elif event == "error":
                        assistant_message.status = "error"
                        await session.commit()
                        yield _format_sse("error", data)
                        return
                if buffer_text:
                    assistant_message.status = "completed"
                    assistant_message.content = buffer_text
                    assistant_message.model = request_payload.model
                    await session.commit()
                    yield _format_sse("final", {"text": buffer_text, "usage": None})
            except GatewayError as exc:
                assistant_message.status = "error"
                await session.commit()
                yield _format_sse(
                    "error",
                    {"code": "gateway_error", "message": str(exc), "retryable": True},
                )

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        gw_response = await send_chat(settings, request_payload)
        assistant_message.status = "completed"
        assistant_message.content = gw_response.text
        assistant_message.model = request_payload.model
        assistant_message.usage_json = gw_response.usage
        await session.commit()
    except GatewayError:
        assistant_message.status = "error"
        await session.commit()
        raise HTTPException(status_code=502, detail="gateway error")

    return {
        "conversation_id": conversation_id,
        "user_message_id": user_message.id,
        "assistant_message_id": assistant_message.id,
        "assistant_status": assistant_message.status,
        "client_message_id": payload.client_message_id,
    }


@app.post("/company/users/{user_id}/deactivate")
async def company_deactivate_user(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("company_admin")),
):
    company_id = _require_company_id(current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="cannot deactivate self")

    user = await session.get(User, user_id)
    if not user or user.company_id != company_id:
        raise HTTPException(status_code=404, detail="user not found")
    if user.role == "superadmin":
        raise HTTPException(status_code=403, detail="cannot deactivate superadmin")

    user.is_active = False
    await session.commit()

    await write_audit_log(
        session=session,
        actor_user_id=current_user.id,
        company_id=company_id,
        action="user.deactivate",
        target_type="user",
        target_id=user_id,
        payload_json=json.dumps({}),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"status": "ok"}


@app.post("/company/credits")
async def company_add_credits(
    payload: CompanyCreditsIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("company_admin")),
):
    company_id = _require_company_id(current_user)
    if payload.user_id:
        user = await session.get(User, payload.user_id)
        if not user or user.company_id != company_id:
            raise HTTPException(status_code=404, detail="user not found")

    key = payload.idempotency_key or generate_raw_token()
    try:
        entry = await add_ledger_entry(
            session=session,
            company_id=company_id,
            user_id=payload.user_id,
            delta=payload.amount,
            reason=payload.reason,
            idempotency_key=key,
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="duplicate idempotency_key")

    await write_audit_log(
        session=session,
        actor_user_id=current_user.id,
        company_id=company_id,
        action="credits.add",
        target_type="ledger",
        target_id=entry.id,
        payload_json=json.dumps({"amount": payload.amount, "reason": payload.reason}),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"status": "ok", "id": entry.id}


@app.get("/internal/whoami")
async def whoami(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "company_id": current_user.company_id,
        "is_active": current_user.is_active,
    }


@app.get("/internal/admin-only")
async def admin_only(current_user: User = Depends(require_role("superadmin"))):
    return {"status": "ok"}
