from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import utcnow
from product_api.models import (
    Company,
    Conversation,
    Invite,
    Ledger,
    Message,
    AuditLog,
    User,
)


async def create_company(
    session: AsyncSession,
    name: str,
    inn: str | None = None,
    phone: str | None = None,
    status: str = "legacy",
) -> Company:
    company = Company(name=name, inn=inn, phone=phone, status=status)
    session.add(company)
    await session.commit()
    return company


async def get_company_by_inn(session: AsyncSession, inn: str) -> Company | None:
    result = await session.execute(select(Company).where(Company.inn == inn))
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_active_invite_by_email(session: AsyncSession, email: str) -> Invite | None:
    now = utcnow()
    email = email.lower()
    result = await session.execute(
        select(Invite)
        .where(
            Invite.email == email,
            Invite.used_at.is_(None),
            Invite.expires_at > now,
        )
        .order_by(Invite.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def create_invite(
    session: AsyncSession,
    company_id: int,
    email: str,
    token_hash: str,
    expires_at,
    invited_by_user_id: int | None,
    role: str = "member",
) -> Invite:
    now = utcnow()
    email = email.lower()
    await session.execute(
        text(
            "UPDATE invites SET used_at = :now "
            "WHERE email = :email AND used_at IS NULL AND expires_at <= :now"
        ),
        {"email": email, "now": now},
    )
    invite = Invite(
        company_id=company_id,
        email=email,
        token_hash=token_hash,
        expires_at=expires_at,
        invited_by_user_id=invited_by_user_id,
        role=role,
    )
    session.add(invite)
    await session.commit()
    return invite


async def write_audit_log(
    session: AsyncSession,
    actor_user_id: int | None,
    company_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None,
    payload_json: str,
    ip: str | None,
    user_agent: str | None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        company_id=company_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload_json=payload_json,
        ip=ip,
        user_agent=user_agent,
    )
    session.add(entry)
    await session.commit()
    return entry


async def add_ledger_entry(
    session: AsyncSession,
    company_id: int,
    delta: int,
    reason: str,
    idempotency_key: str,
    user_id: int | None = None,
    message_id: int | None = None,
) -> Ledger:
    entry = Ledger(
        company_id=company_id,
        user_id=user_id,
        message_id=message_id,
        delta=delta,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    session.add(entry)
    await session.commit()
    return entry


async def create_conversation(
    session: AsyncSession,
    company_id: int,
    user_id: int,
    title: str | None = None,
) -> Conversation:
    convo = Conversation(company_id=company_id, user_id=user_id, title=title)
    session.add(convo)
    await session.commit()
    return convo


async def list_conversations(session: AsyncSession, company_id: int, user_id: int):
    result = await session.execute(
        select(Conversation)
        .where(Conversation.company_id == company_id, Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return result.scalars().all()


async def add_message(
    session: AsyncSession,
    conversation_id: int,
    role: str,
    status: str,
    content: str,
    model: str | None = None,
    client_message_id: str | None = None,
    parent_message_id: int | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        status=status,
        content=content,
        model=model,
        client_message_id=client_message_id,
        parent_message_id=parent_message_id,
    )
    session.add(message)
    await session.commit()
    return message


async def list_messages(session: AsyncSession, conversation_id: int):
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return result.scalars().all()
