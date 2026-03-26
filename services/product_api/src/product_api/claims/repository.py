from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import utcnow
from product_api.models import Claim, ClaimEvent


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def build_public_claim_snapshot(claim: Claim) -> dict:
    return {
        "id": claim.id,
        "status": claim.status,
        "generation_state": claim.generation_state,
        "manual_review_required": claim.generation_state == "manual_review_required",
        "price_rub": claim.price_rub,
        "input_text": claim.input_text,
        "client_email": claim.client_email,
        "client_phone": claim.client_phone,
        "case_type": claim.case_type,
        "normalized_data": claim.normalized_data_json,
        "created_at": _isoformat(claim.created_at),
        "updated_at": _isoformat(claim.updated_at),
        "paid_at": _isoformat(claim.paid_at),
        "reviewed_at": _isoformat(claim.reviewed_at),
        "sent_at": _isoformat(claim.sent_at),
    }


async def create_claim(
    session: AsyncSession,
    *,
    price_rub: int,
    input_text: str,
    edit_token_hash: str,
) -> Claim:
    now = utcnow()
    claim = Claim(
        status="draft",
        generation_state="insufficient_data",
        price_rub=price_rub,
        input_text=input_text,
        edit_token_hash=edit_token_hash,
        created_at=now,
        updated_at=now,
    )
    session.add(claim)
    await session.flush()
    return claim


async def get_claim_by_id(session: AsyncSession, claim_id: int) -> Claim | None:
    result = await session.execute(select(Claim).where(Claim.id == claim_id))
    return result.scalar_one_or_none()


async def append_claim_event(
    session: AsyncSession,
    *,
    claim_id: int,
    event_type: str,
    payload_json: dict,
) -> ClaimEvent:
    event = ClaimEvent(
        claim_id=claim_id,
        event_type=event_type,
        payload_json=payload_json,
        created_at=utcnow(),
    )
    session.add(event)
    return event
