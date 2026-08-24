"""Read-only H2 adapter shared by SSR/crawler callers.

It intentionally delegates to the exact persistence resolver and contains no
writer, queue, provider, AI or fallback-renderer dependency.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from .service import resolve_public_h2
from .public_h2_models import CompanyPublicH2Response


async def resolve_public_h2_ssr(session: AsyncSession, *, inn: str) -> CompanyPublicH2Response:
    return await resolve_public_h2(session, inn=inn)
