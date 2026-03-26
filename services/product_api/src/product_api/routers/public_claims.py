from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import generate_raw_token
from product_api.db.session import get_session
from product_api.models import Claim
from product_api.settings import get_settings

from product_api.claims.repository import (
    append_claim_event,
    build_public_claim_snapshot,
    create_claim,
)
from product_api.claims.security import hash_claim_edit_token, require_claim_access

settings = get_settings()
router = APIRouter()


class ClaimCreateIn(BaseModel):
    input_text: str


class PublicClaimOut(BaseModel):
    id: int
    status: str
    generation_state: str
    manual_review_required: bool
    price_rub: int
    input_text: str
    client_email: str | None
    client_phone: str | None
    case_type: str | None
    normalized_data: dict[str, Any] | None
    created_at: str | None
    updated_at: str | None
    paid_at: str | None
    reviewed_at: str | None
    sent_at: str | None


class ClaimCreateOut(BaseModel):
    claim_id: int
    edit_token: str
    claim: PublicClaimOut


def _normalize_input_text(raw_value: str) -> str:
    normalized = raw_value.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="input_text is required")
    if len(normalized) > settings.max_message_chars:
        raise HTTPException(status_code=400, detail="input_text is too long")
    return normalized


@router.post("/claims", response_model=ClaimCreateOut)
async def create_public_claim(
    payload: ClaimCreateIn,
    session: AsyncSession = Depends(get_session),
):
    input_text = _normalize_input_text(payload.input_text)
    raw_token = generate_raw_token()
    token_hash = hash_claim_edit_token(raw_token)

    claim = await create_claim(
        session,
        price_rub=settings.claims_price_rub,
        input_text=input_text,
        edit_token_hash=token_hash,
    )
    await append_claim_event(
        session,
        claim_id=claim.id,
        event_type="claim.created",
        payload_json={
            "status": claim.status,
            "generation_state": claim.generation_state,
            "input_text_length": len(input_text),
        },
    )
    await session.commit()

    return {
        "claim_id": claim.id,
        "edit_token": raw_token,
        "claim": build_public_claim_snapshot(claim),
    }


@router.get("/claims/{claim_id}", response_model=PublicClaimOut)
async def get_public_claim(
    claim: Claim = Depends(require_claim_access),
):
    return build_public_claim_snapshot(claim)
