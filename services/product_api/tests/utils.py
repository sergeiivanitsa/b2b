from datetime import datetime, timedelta, timezone

from product_api.auth import build_expiry, generate_raw_token, hmac_sha256, utcnow
from product_api.models import Company, Conversation, Invite, Ledger, Message, Session, User
from product_api.settings import get_settings


async def create_company(
    session,
    name: str,
    inn: str | None = None,
    phone: str | None = None,
    status: str = "legacy",
) -> Company:
    company = Company(name=name, inn=inn, phone=phone, status=status)
    session.add(company)
    await session.commit()
    return company


async def create_user(
    session,
    email: str,
    role: str | None,
    company_id: int | None = None,
    is_active: bool = True,
    is_superadmin: bool = False,
) -> User:
    if is_superadmin:
        role = None
        company_id = None
    user = User(
        email=email,
        role=role,
        is_active=is_active,
        company_id=company_id,
        is_superadmin=is_superadmin,
    )
    session.add(user)
    await session.commit()
    return user


async def create_session_cookie(session, user_id: int) -> str:
    settings = get_settings()
    raw = generate_raw_token()
    session_hash = hmac_sha256(settings.session_secret, raw)
    expires_at = build_expiry(settings.session_ttl_seconds)
    record = Session(user_id=user_id, session_hash=session_hash, expires_at=expires_at)
    session.add(record)
    await session.commit()
    return raw


async def add_credits(session, company_id: int, amount: int, reason: str = "test") -> Ledger:
    entry = Ledger(
        company_id=company_id,
        user_id=None,
        message_id=None,
        delta=amount,
        reason=reason,
        idempotency_key=generate_raw_token(),
    )
    session.add(entry)
    await session.commit()
    return entry


async def create_invite(
    session,
    company_id: int,
    email: str,
    role: str = "member",
    expires_at: datetime | None = None,
) -> tuple[str, Invite]:
    settings = get_settings()
    raw = generate_raw_token()
    token_hash = hmac_sha256(settings.invite_token_secret, raw)
    invite = Invite(
        company_id=company_id,
        email=email,
        role=role,
        token_hash=token_hash,
        expires_at=expires_at or build_expiry(3600),
        invited_by_user_id=None,
    )
    session.add(invite)
    await session.commit()
    return raw, invite


async def create_conversation(session, company_id: int, user_id: int) -> Conversation:
    convo = Conversation(company_id=company_id, user_id=user_id, title=None)
    session.add(convo)
    await session.commit()
    return convo


async def add_message(
    session,
    conversation_id: int,
    role: str,
    content: str,
    status: str = "completed",
    created_at: datetime | None = None,
    client_message_id: str | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        status=status,
        content=content,
        model=None,
        client_message_id=client_message_id,
        created_at=created_at or utcnow(),
    )
    session.add(message)
    await session.commit()
    return message


def utc_at(offset_seconds: int) -> datetime:
    return utcnow() + timedelta(seconds=offset_seconds)
