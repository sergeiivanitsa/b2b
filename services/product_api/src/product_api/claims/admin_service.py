from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import utcnow
from product_api.models import Claim

from .normalization import build_step2_contract
from .repository import (
    append_claim_event,
    build_public_claim_file_snapshot,
    get_claim_by_id,
    list_claim_files,
)

CLAIM_STATUS_VALUES = {"draft", "preview_ready", "paid", "in_review", "sent"}
CLAIM_GENERATION_STATE_VALUES = {"ready", "manual_review_required", "insufficient_data"}
ADMIN_TARGET_STATUSES = {"in_review", "sent"}


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _normalize_filter_value(
    value: str | None,
    *,
    field_name: str,
    allowed_values: set[str],
) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized not in allowed_values:
        raise ValueError(f"invalid {field_name}")
    return normalized


def normalize_claim_status_filter(value: str | None) -> str | None:
    return _normalize_filter_value(
        value,
        field_name="status filter",
        allowed_values=CLAIM_STATUS_VALUES,
    )


def normalize_claim_generation_state_filter(value: str | None) -> str | None:
    return _normalize_filter_value(
        value,
        field_name="generation_state filter",
        allowed_values=CLAIM_GENERATION_STATE_VALUES,
    )


def normalize_admin_target_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ADMIN_TARGET_STATUSES:
        raise ValueError("invalid status")
    return normalized


def normalize_final_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("final_text is required")
    normalized = value.strip()
    if not normalized:
        raise ValueError("final_text is required")
    return normalized


def build_admin_claim_list_snapshot(claim: Claim) -> dict[str, Any]:
    return {
        "id": claim.id,
        "status": claim.status,
        "generation_state": claim.generation_state,
        "manual_review_required": claim.generation_state == "manual_review_required",
        "case_type": claim.case_type,
        "client_email": claim.client_email,
        "price_rub": claim.price_rub,
        "has_final_text": bool((claim.final_text or "").strip()),
        "created_at": _isoformat(claim.created_at),
        "updated_at": _isoformat(claim.updated_at),
        "paid_at": _isoformat(claim.paid_at),
        "reviewed_at": _isoformat(claim.reviewed_at),
        "sent_at": _isoformat(claim.sent_at),
    }


def build_admin_claim_detail_snapshot(claim: Claim) -> dict[str, Any]:
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
        "risk_flags": list(claim.risk_flags_json or []),
        "allowed_blocks": list(claim.allowed_blocks_json or []),
        "blocked_blocks": list(claim.blocked_blocks_json or []),
        "generation_notes": claim.generation_notes_json if isinstance(claim.generation_notes_json, dict) else None,
        "generated_preview_text": claim.generated_preview_text or "",
        "generated_full_text": claim.generated_full_text or "",
        "final_text": claim.final_text or "",
        "summary_for_admin": claim.summary_for_admin,
        "review_comment": claim.review_comment,
        "created_at": _isoformat(claim.created_at),
        "updated_at": _isoformat(claim.updated_at),
        "paid_at": _isoformat(claim.paid_at),
        "reviewed_at": _isoformat(claim.reviewed_at),
        "sent_at": _isoformat(claim.sent_at),
    }


def apply_admin_status_transition(claim: Claim, *, target_status: str) -> tuple[str, list[str]]:
    normalized_target = normalize_admin_target_status(target_status)
    from_status = claim.status
    changed_fields: list[str] = []

    if normalized_target == "in_review":
        if claim.status != "paid":
            raise ValueError("invalid_transition")
        claim.status = "in_review"
        changed_fields.append("status")
        if claim.reviewed_at is None:
            claim.reviewed_at = utcnow()
            changed_fields.append("reviewed_at")
        return from_status, changed_fields

    if claim.status != "in_review":
        raise ValueError("invalid_transition")
    claim.status = "sent"
    changed_fields.append("status")
    if claim.sent_at is None:
        claim.sent_at = utcnow()
        changed_fields.append("sent_at")
    return from_status, changed_fields


def apply_admin_final_text(claim: Claim, *, final_text: Any) -> list[str]:
    normalized_final_text = normalize_final_text(final_text)
    changed_fields: list[str] = []
    if claim.final_text != normalized_final_text:
        claim.final_text = normalized_final_text
        changed_fields.append("final_text")
    return changed_fields


async def list_admin_claims(
    session: AsyncSession,
    *,
    status: str | None,
    generation_state: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    if limit < 1 or limit > 200:
        raise ValueError("invalid limit")
    if offset < 0:
        raise ValueError("invalid offset")

    normalized_status = normalize_claim_status_filter(status)
    normalized_generation_state = normalize_claim_generation_state_filter(generation_state)

    query = select(Claim).order_by(Claim.id.desc()).limit(limit).offset(offset)
    if normalized_status:
        query = query.where(Claim.status == normalized_status)
    if normalized_generation_state:
        query = query.where(Claim.generation_state == normalized_generation_state)

    result = await session.execute(query)
    claims = list(result.scalars().all())
    return [build_admin_claim_list_snapshot(item) for item in claims]


async def get_admin_claim(
    session: AsyncSession,
    *,
    claim_id: int,
) -> dict[str, Any] | None:
    claim = await get_claim_by_id(session, claim_id)
    if not claim:
        return None
    return build_admin_claim_detail_snapshot(claim)


async def update_admin_claim_status(
    session: AsyncSession,
    *,
    claim_id: int,
    target_status: str,
) -> dict[str, Any]:
    claim = await get_claim_by_id(session, claim_id)
    if not claim:
        raise LookupError("claim not found")

    from_status, changed_fields = apply_admin_status_transition(claim, target_status=target_status)
    claim.updated_at = utcnow()
    session.add(claim)
    await append_claim_event(
        session,
        claim_id=claim.id,
        event_type="claim.admin_status_updated",
        payload_json={
            "from_status": from_status,
            "to_status": claim.status,
            "changed_fields": changed_fields,
            "generation_state": claim.generation_state,
        },
    )
    await session.flush()
    return build_admin_claim_detail_snapshot(claim)


async def update_admin_claim_final_text(
    session: AsyncSession,
    *,
    claim_id: int,
    final_text: Any,
) -> dict[str, Any]:
    claim = await get_claim_by_id(session, claim_id)
    if not claim:
        raise LookupError("claim not found")

    changed_fields = apply_admin_final_text(claim, final_text=final_text)
    claim.updated_at = utcnow()
    session.add(claim)
    if changed_fields:
        await append_claim_event(
            session,
            claim_id=claim.id,
            event_type="claim.admin_final_text_updated",
            payload_json={
                "changed_fields": changed_fields,
                "final_text_length": len(claim.final_text or ""),
            },
        )
    await session.flush()
    return build_admin_claim_detail_snapshot(claim)


async def get_admin_claim_files(
    session: AsyncSession,
    *,
    claim_id: int,
) -> list[dict[str, Any]]:
    claim = await get_claim_by_id(session, claim_id)
    if not claim:
        raise LookupError("claim not found")
    files = await list_claim_files(session, claim.id)
    return [build_public_claim_file_snapshot(item) for item in files]
