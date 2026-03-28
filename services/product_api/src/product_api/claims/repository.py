from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import utcnow
from product_api.models import Claim, ClaimEvent

from .normalization import (
    build_step2_contract,
    merge_normalized_data_patch,
    normalize_case_type,
    normalize_client_email,
    normalize_client_phone,
)


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def build_public_claim_snapshot(claim: Claim) -> dict:
    normalized_data = claim.normalized_data_json if isinstance(claim.normalized_data_json, dict) else None
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
        "normalized_data": normalized_data,
        "step2": build_step2_contract(normalized_data),
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


def derive_generation_state_for_extract(normalized_data: dict[str, Any]) -> str:
    return derive_generation_state_from_normalized_data(normalized_data)


def derive_generation_state_from_normalized_data(normalized_data: dict[str, Any]) -> str:
    missing_fields = normalized_data.get("missing_fields")
    if isinstance(missing_fields, list) and len(missing_fields) == 0:
        return "ready"
    return "insufficient_data"


async def apply_claim_extraction_result(
    session: AsyncSession,
    claim: Claim,
    *,
    case_type: str | None,
    normalized_data: dict[str, Any],
) -> Claim:
    claim.case_type = case_type
    claim.normalized_data_json = normalized_data
    if claim.generation_state != "manual_review_required":
        claim.generation_state = derive_generation_state_from_normalized_data(normalized_data)
    claim.updated_at = utcnow()
    session.add(claim)
    await session.flush()
    return claim


async def apply_claim_patch(
    session: AsyncSession,
    claim: Claim,
    *,
    case_type_provided: bool,
    case_type_value: Any,
    client_email_provided: bool,
    client_email_value: Any,
    client_phone_provided: bool,
    client_phone_value: Any,
    normalized_patch_values: dict[str, Any],
    normalized_patch_fields: set[str],
) -> tuple[Claim, list[str]]:
    changed_fields: list[str] = []

    if case_type_provided:
        normalized_case_type = normalize_case_type(case_type_value)
        if claim.case_type != normalized_case_type:
            claim.case_type = normalized_case_type
            changed_fields.append("case_type")

    if client_email_provided:
        normalized_client_email = normalize_client_email(client_email_value)
        if claim.client_email != normalized_client_email:
            claim.client_email = normalized_client_email
            changed_fields.append("client_email")

    if client_phone_provided:
        normalized_client_phone = normalize_client_phone(client_phone_value)
        if claim.client_phone != normalized_client_phone:
            claim.client_phone = normalized_client_phone
            changed_fields.append("client_phone")

    merged_normalized_data, normalized_changed_fields = merge_normalized_data_patch(
        claim.normalized_data_json if isinstance(claim.normalized_data_json, dict) else None,
        normalized_patch_values,
        normalized_patch_fields,
    )
    if normalized_changed_fields or claim.normalized_data_json is None:
        claim.normalized_data_json = merged_normalized_data
        changed_fields.extend(f"normalized_data.{field_name}" for field_name in normalized_changed_fields)

    if claim.generation_state != "manual_review_required":
        next_generation_state = derive_generation_state_from_normalized_data(merged_normalized_data)
        if claim.generation_state != next_generation_state:
            claim.generation_state = next_generation_state
            changed_fields.append("generation_state")

    claim.updated_at = utcnow()
    session.add(claim)
    await session.flush()
    return claim, changed_fields
