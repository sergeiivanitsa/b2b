from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import generate_raw_token
from product_api.claims.extraction import build_extraction_event_payload, run_claim_extraction
from product_api.claims.schemas import ClaimPatchIn, Step2Out
from product_api.db.session import get_session
from product_api.gateway_client import GatewayError
from product_api.models import Claim
from product_api.settings import get_settings

from product_api.claims.repository import (
    apply_claim_patch,
    apply_claim_extraction_result,
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
    step2: Step2Out
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


@router.post("/claims/{claim_id}/extract", response_model=PublicClaimOut)
async def extract_public_claim(
    claim: Claim = Depends(require_claim_access),
    session: AsyncSession = Depends(get_session),
):
    try:
        result = await run_claim_extraction(
            settings,
            claim_id=claim.id,
            input_text=claim.input_text,
        )
    except GatewayError:
        await append_claim_event(
            session,
            claim_id=claim.id,
            event_type="claim.extract_failed",
            payload_json={"error_code": "gateway_error"},
        )
        await session.commit()
        raise HTTPException(status_code=502, detail="gateway error")

    await apply_claim_extraction_result(
        session,
        claim,
        case_type=result["case_type"],
        normalized_data=result["normalized_data"],
    )
    await append_claim_event(
        session,
        claim_id=claim.id,
        event_type="claim.extract_fallback"
        if result["error_code"]
        else "claim.extract_succeeded",
        payload_json=build_extraction_event_payload(result),
    )
    await session.commit()
    return build_public_claim_snapshot(claim)


@router.patch("/claims/{claim_id}", response_model=PublicClaimOut)
async def update_public_claim(
    payload: ClaimPatchIn,
    claim: Claim = Depends(require_claim_access),
    session: AsyncSession = Depends(get_session),
):
    normalized_patch_fields: set[str] = set()
    normalized_patch_values: dict[str, Any] = {}
    if payload.normalized_data is not None:
        normalized_patch_fields = set(payload.normalized_data.model_fields_set)
        normalized_patch_values = payload.normalized_data.model_dump(exclude_unset=True)

    payload_fields = set(payload.model_fields_set)
    try:
        _, changed_fields = await apply_claim_patch(
            session,
            claim,
            case_type_provided="case_type" in payload_fields,
            case_type_value=payload.case_type,
            client_email_provided="client_email" in payload_fields,
            client_email_value=payload.client_email,
            client_phone_provided="client_phone" in payload_fields,
            client_phone_value=payload.client_phone,
            normalized_patch_values=normalized_patch_values,
            normalized_patch_fields=normalized_patch_fields,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    snapshot = build_public_claim_snapshot(claim)
    await append_claim_event(
        session,
        claim_id=claim.id,
        event_type="claim.step2_updated",
        payload_json={
            "changed_fields": changed_fields,
            "missing_fields_count": len(snapshot["step2"]["missing_fields"]),
            "generation_state": claim.generation_state,
            "derived": snapshot["step2"]["derived"],
        },
    )
    await session.commit()
    return snapshot
