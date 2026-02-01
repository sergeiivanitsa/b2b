import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.db.session import AsyncSessionMaker
from product_api.models import User
from product_api.rbac import ROLE_SUPERADMIN
from product_api.settings import get_settings

logger = logging.getLogger(__name__)


async def ensure_superadmin() -> None:
    settings = get_settings()
    if not settings.superadmin_email:
        return

    async with AsyncSessionMaker() as session:
        await _upsert_superadmin(session, settings.superadmin_email)


async def _upsert_superadmin(session: AsyncSession, email: str) -> None:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        updated = False
        if user.role != ROLE_SUPERADMIN:
            user.role = ROLE_SUPERADMIN
            updated = True
        if not user.is_active:
            user.is_active = True
            updated = True
        if user.company_id is not None:
            user.company_id = None
            updated = True
        if updated:
            await session.commit()
            logger.info("superadmin updated")
        return

    user = User(email=email, role=ROLE_SUPERADMIN, is_active=True, company_id=None)
    session.add(user)
    await session.commit()
    logger.info("superadmin created")
