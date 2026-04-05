from hmac import compare_digest

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import hmac_sha256
from product_api.db.session import get_session
from product_api.models import Claim
from product_api.settings import get_settings

from .repository import get_claim_by_id

settings = get_settings()


def hash_claim_edit_token(raw_token: str) -> str:
    return hmac_sha256(settings.claim_edit_token_secret, raw_token)


async def require_claim_access(
    claim_id: int,
    x_claim_edit_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Claim:
    raw_token = x_claim_edit_token.strip() if x_claim_edit_token else ""
    if not raw_token:
        raise HTTPException(status_code=401, detail="claim edit token required")

    claim = await get_claim_by_id(session, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="claim not found")

    token_hash = hash_claim_edit_token(raw_token)
    if not compare_digest(token_hash, claim.edit_token_hash):
        raise HTTPException(status_code=404, detail="claim not found")

    return claim
