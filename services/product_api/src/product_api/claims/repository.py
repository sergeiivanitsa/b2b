from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import utcnow
from product_api.models import Claim, ClaimEvent, ClaimFile

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


async def apply_claim_contact(
    session: AsyncSession,
    claim: Claim,
    *,
    client_email_value: Any,
    client_phone_provided: bool,
    client_phone_value: Any,
) -> tuple[Claim, list[str]]:
    changed_fields: list[str] = []

    normalized_client_email = normalize_client_email(client_email_value)
    if normalized_client_email is None:
        raise ValueError("client_email is required")
    if claim.client_email != normalized_client_email:
        claim.client_email = normalized_client_email
        changed_fields.append("client_email")

    if client_phone_provided:
        normalized_client_phone = normalize_client_phone(client_phone_value)
        if claim.client_phone != normalized_client_phone:
            claim.client_phone = normalized_client_phone
            changed_fields.append("client_phone")

    claim.updated_at = utcnow()
    session.add(claim)
    await session.flush()
    return claim, changed_fields


def build_public_claim_file_snapshot(claim_file: ClaimFile) -> dict:
    return {
        "id": claim_file.id,
        "filename": claim_file.filename,
        "mime_type": claim_file.mime_type,
        "file_role": claim_file.file_role,
        "uploaded_at": _isoformat(claim_file.uploaded_at),
    }


def build_public_claim_preview_snapshot(claim: Claim) -> dict:
    normalized_data = claim.normalized_data_json if isinstance(claim.normalized_data_json, dict) else None
    step2 = build_step2_contract(normalized_data)
    return {
        "claim_id": claim.id,
        "generation_state": claim.generation_state,
        "manual_review_required": claim.generation_state == "manual_review_required",
        "risk_flags": list(claim.risk_flags_json or []),
        "allowed_blocks": list(claim.allowed_blocks_json or []),
        "blocked_blocks": list(claim.blocked_blocks_json or []),
        "generated_preview_text": claim.generated_preview_text or "",
        "missing_fields": list(step2["missing_fields"]),
    }


async def create_claim_file(
    session: AsyncSession,
    *,
    claim_id: int,
    filename: str,
    storage_path: str,
    mime_type: str,
    file_role: str,
) -> ClaimFile:
    claim_file = ClaimFile(
        claim_id=claim_id,
        filename=filename,
        storage_path=storage_path,
        mime_type=mime_type,
        file_role=file_role,
        uploaded_at=utcnow(),
    )
    session.add(claim_file)
    await session.flush()
    return claim_file


async def list_claim_files(session: AsyncSession, claim_id: int) -> list[ClaimFile]:
    result = await session.execute(
        select(ClaimFile).where(ClaimFile.claim_id == claim_id).order_by(ClaimFile.id.asc())
    )
    return list(result.scalars().all())


async def apply_claim_generation_preview(
    session: AsyncSession,
    claim: Claim,
    *,
    generation_state: str,
    risk_flags: list[str],
    allowed_blocks: list[str],
    blocked_blocks: list[str],
    generated_preview_text: str | None,
) -> Claim:
    claim.generation_state = generation_state
    claim.risk_flags_json = risk_flags
    claim.allowed_blocks_json = allowed_blocks
    claim.blocked_blocks_json = blocked_blocks
    claim.generated_preview_text = generated_preview_text
    claim.updated_at = utcnow()
    session.add(claim)
    await session.flush()
    return claim


async def apply_claim_payment_stub(
    session: AsyncSession,
    claim: Claim,
) -> tuple[Claim, list[str]]:
    if claim.generation_state == "insufficient_data":
        raise ValueError("insufficient_data")
    if claim.status in {"paid", "in_review", "sent"}:
        raise ValueError("already_paid_or_later_state")

    changed_fields: list[str] = []
    if claim.status != "paid":
        claim.status = "paid"
        changed_fields.append("status")
    if claim.paid_at is None:
        claim.paid_at = utcnow()
        changed_fields.append("paid_at")
    claim.updated_at = utcnow()
    session.add(claim)
    await session.flush()
    return claim, changed_fields
