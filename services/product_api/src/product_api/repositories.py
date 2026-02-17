from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import utcnow
from product_api.models import (
    Company,
    Conversation,
    Invite,
    Ledger,
    Message,
    AuditLog,
    UserCreditLimit,
    User,
)


class UserLimitUpdateError(Exception):
    pass


class UserLimitUserNotFoundError(UserLimitUpdateError):
    pass


class UserLimitNegativeError(UserLimitUpdateError):
    pass


class UserLimitExceedsPoolError(UserLimitUpdateError):
    pass


class DetachUserError(Exception):
    pass


class DetachUserNotFoundError(DetachUserError):
    pass


class DetachUserForbiddenError(DetachUserError):
    pass


class ChatCreditError(Exception):
    pass


class ChatCreditsCompanyInsufficientError(ChatCreditError):
    pass


class ChatCreditsUserInsufficientError(ChatCreditError):
    pass


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
    first_name: str | None = None,
    last_name: str | None = None,
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
        first_name=first_name,
        last_name=last_name,
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


async def reserve_chat_credits(
    session: AsyncSession,
    company_id: int,
    user_id: int,
    message_id: int,
    units: int = 1,
) -> Ledger:
    if units <= 0:
        raise ValueError("units must be positive")

    company_result = await session.execute(
        select(Company).where(Company.id == company_id).with_for_update()
    )
    company = company_result.scalar_one_or_none()
    if not company:
        raise ChatCreditsCompanyInsufficientError("company not found")

    user_result = await session.execute(
        select(User)
        .where(User.id == user_id, User.company_id == company_id)
        .with_for_update()
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise ChatCreditsUserInsufficientError("user not in company")

    limit_result = await session.execute(
        select(UserCreditLimit)
        .where(
            UserCreditLimit.user_id == user_id,
            UserCreditLimit.company_id == company_id,
        )
        .with_for_update()
    )
    limit = limit_result.scalar_one_or_none()
    if not limit:
        raise ChatCreditsUserInsufficientError("user limit not found")

    user_remaining = int(limit.remaining_credits or 0)
    if user_remaining < units:
        raise ChatCreditsUserInsufficientError("insufficient user credits")

    pool_balance = await get_company_pool_balance(session, company_id)
    if pool_balance < units:
        raise ChatCreditsCompanyInsufficientError("insufficient company credits")

    limit.remaining_credits = user_remaining - units
    entry = Ledger(
        company_id=company_id,
        user_id=user_id,
        message_id=message_id,
        delta=-units,
        reason="chat_message",
        idempotency_key=f"msg:{message_id}",
    )
    session.add(entry)
    await session.flush()
    return entry


async def get_company_pool_balance(session: AsyncSession, company_id: int) -> int:
    result = await session.execute(
        select(func.coalesce(func.sum(Ledger.delta), 0)).where(Ledger.company_id == company_id)
    )
    return int(result.scalar_one() or 0)


async def get_company_allocated_total(session: AsyncSession, company_id: int) -> int:
    result = await session.execute(
        select(func.coalesce(func.sum(UserCreditLimit.remaining_credits), 0)).where(
            UserCreditLimit.company_id == company_id
        )
    )
    return int(result.scalar_one() or 0)


async def get_company_active_allocated_total(session: AsyncSession, company_id: int) -> int:
    result = await session.execute(
        select(func.coalesce(func.sum(UserCreditLimit.remaining_credits), 0))
        .select_from(UserCreditLimit)
        .join(User, User.id == UserCreditLimit.user_id)
        .where(
            UserCreditLimit.company_id == company_id,
            User.is_active.is_(True),
        )
    )
    return int(result.scalar_one() or 0)


async def get_user_credit_limit(session: AsyncSession, user_id: int) -> UserCreditLimit | None:
    result = await session.execute(
        select(UserCreditLimit).where(UserCreditLimit.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_company_user_credit_limits(
    session: AsyncSession,
    company_id: int,
) -> list[UserCreditLimit]:
    result = await session.execute(
        select(UserCreditLimit)
        .where(UserCreditLimit.company_id == company_id)
        .order_by(UserCreditLimit.user_id.asc())
    )
    return result.scalars().all()


async def ensure_user_credit_limit(
    session: AsyncSession,
    company_id: int,
    user_id: int,
    initial_remaining: int = 0,
) -> UserCreditLimit:
    current = await get_user_credit_limit(session, user_id)
    if current:
        return current

    entry = UserCreditLimit(
        company_id=company_id,
        user_id=user_id,
        remaining_credits=max(0, initial_remaining),
    )
    session.add(entry)
    await session.commit()
    return entry


async def apply_user_limit_delta(
    session: AsyncSession,
    company_id: int,
    user_id: int,
    delta: int,
) -> dict[str, object]:
    try:
        company_result = await session.execute(
            select(Company)
            .where(Company.id == company_id)
            .with_for_update()
        )
        company = company_result.scalar_one_or_none()
        if not company:
            raise UserLimitUserNotFoundError("company not found")

        user_result = await session.execute(
            select(User)
            .where(
                User.id == user_id,
                User.company_id == company_id,
            )
            .with_for_update()
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise UserLimitUserNotFoundError("user not found")

        limit_result = await session.execute(
            select(UserCreditLimit)
            .where(UserCreditLimit.user_id == user_id)
            .with_for_update()
        )
        limit = limit_result.scalar_one_or_none()
        if not limit:
            limit = UserCreditLimit(
                company_id=company_id,
                user_id=user_id,
                remaining_credits=0,
            )
            session.add(limit)
            await session.flush()

        current_remaining = int(limit.remaining_credits or 0)
        next_remaining = current_remaining + delta
        if next_remaining < 0:
            raise UserLimitNegativeError("limit cannot be negative")

        pool_balance = await get_company_pool_balance(session, company_id)
        allocated_active = await get_company_active_allocated_total(session, company_id)
        proposed_allocated_active = allocated_active + delta if user.is_active else allocated_active
        if proposed_allocated_active > pool_balance:
            raise UserLimitExceedsPoolError("allocation exceeds company pool balance")

        limit.remaining_credits = next_remaining
        await session.commit()

        allocated_total = await get_company_allocated_total(session, company_id)
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "remaining_credits": next_remaining,
            },
            "credits": {
                "pool_balance": pool_balance,
                "allocated_total": allocated_total,
                "unallocated_balance": pool_balance - allocated_total,
            },
        }
    except UserLimitUpdateError:
        await session.rollback()
        raise


async def detach_company_user(
    session: AsyncSession,
    company_id: int,
    user_id: int,
) -> dict[str, object]:
    try:
        user_result = await session.execute(
            select(User)
            .where(
                User.id == user_id,
                User.company_id == company_id,
            )
            .with_for_update()
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise DetachUserNotFoundError("user not found")
        if user.is_superadmin:
            raise DetachUserForbiddenError("cannot detach superadmin")

        limit_result = await session.execute(
            select(UserCreditLimit)
            .where(UserCreditLimit.user_id == user_id)
            .with_for_update()
        )
        limit = limit_result.scalar_one_or_none()
        released_limit = int(limit.remaining_credits or 0) if limit else 0
        if limit:
            await session.delete(limit)
            await session.flush()

        previous_company_id = user.company_id
        previous_role = user.role
        user.company_id = None
        user.role = "member"
        user.is_active = False
        user.joined_company_at = None

        await session.execute(
            text("DELETE FROM sessions WHERE user_id = :user_id"),
            {"user_id": user_id},
        )

        await session.commit()
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "company_id": user.company_id,
                "role": user.role,
                "is_active": user.is_active,
                "joined_company_at": user.joined_company_at,
            },
            "released_limit": released_limit,
            "previous_company_id": previous_company_id,
            "previous_role": previous_role,
        }
    except DetachUserError:
        await session.rollback()
        raise


async def get_company_summary_data(
    session: AsyncSession,
    company_id: int,
) -> dict[str, object] | None:
    company = await session.get(Company, company_id)
    if not company:
        return None

    pool_balance = await get_company_pool_balance(session, company_id)
    allocated_total = await get_company_allocated_total(session, company_id)

    total_users_result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.company_id == company_id)
    )
    active_users_result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.company_id == company_id, User.is_active.is_(True))
    )

    total_users = int(total_users_result.scalar_one() or 0)
    active_users = int(active_users_result.scalar_one() or 0)
    unallocated_balance = pool_balance - allocated_total

    return {
        "company": {
            "id": company.id,
            "name": company.name,
            "inn": company.inn,
            "phone": company.phone,
            "status": company.status,
        },
        "credits": {
            "pool_balance": pool_balance,
            "allocated_total": allocated_total,
            "unallocated_balance": unallocated_balance,
        },
        "users": {
            "total": total_users,
            "active": active_users,
        },
    }


async def list_company_users_with_stats(
    session: AsyncSession,
    company_id: int,
) -> list[dict[str, object]]:
    spent_subquery = (
        select(
            Ledger.user_id.label("user_id"),
            func.coalesce(func.sum(-Ledger.delta), 0).label("spent_all_time"),
        )
        .where(
            Ledger.company_id == company_id,
            Ledger.user_id.is_not(None),
            Ledger.delta < 0,
            Ledger.reason == "chat_message",
        )
        .group_by(Ledger.user_id)
        .subquery()
    )

    result = await session.execute(
        select(
            User.id,
            User.first_name,
            User.last_name,
            User.email,
            User.role,
            User.is_active,
            User.joined_company_at,
            User.created_at,
            func.coalesce(UserCreditLimit.remaining_credits, 0).label("remaining_credits"),
            func.coalesce(spent_subquery.c.spent_all_time, 0).label("spent_all_time"),
        )
        .select_from(User)
        .outerjoin(UserCreditLimit, UserCreditLimit.user_id == User.id)
        .outerjoin(spent_subquery, spent_subquery.c.user_id == User.id)
        .where(User.company_id == company_id)
        .order_by(User.id.asc())
    )

    users: list[dict[str, object]] = []
    for row in result.fetchall():
        joined_at = row[6] or row[7]
        users.append(
            {
                "id": row[0],
                "first_name": row[1],
                "last_name": row[2],
                "email": row[3],
                "role": row[4],
                "is_active": row[5],
                "joined_company_at": joined_at.isoformat() if joined_at else None,
                "remaining_credits": int(row[8] or 0),
                "spent_all_time": int(row[9] or 0),
            }
        )

    return users


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
