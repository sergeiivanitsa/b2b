from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.claims.admin_auth import require_claims_admin
from product_api.claims.admin_service import (
    append_admin_claim_send_failed_event,
    get_admin_claim,
    get_admin_claim_files,
    list_admin_claims,
    prepare_admin_claim_send,
    send_admin_claim_final_result,
    update_admin_claim_final_text,
    update_admin_claim_status,
)
from product_api.claims.notifications import NotificationSendError, send_claim_final_result
from product_api.claims.repository import get_claim_by_id
from product_api.claims.schemas import Step2Out
from product_api.db.session import get_session
from product_api.settings import get_settings

settings = get_settings()
router = APIRouter()


class AdminClaimListItemOut(BaseModel):
    id: int
    status: str
    generation_state: str
    manual_review_required: bool
    case_type: str | None
    client_email: str | None
    price_rub: int
    has_final_text: bool
    created_at: str | None
    updated_at: str | None
    paid_at: str | None
    reviewed_at: str | None
    sent_at: str | None


class AdminClaimListOut(BaseModel):
    items: list[AdminClaimListItemOut]


class AdminClaimOut(BaseModel):
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
    risk_flags: list[str]
    allowed_blocks: list[str]
    blocked_blocks: list[str]
    generation_notes: dict[str, Any] | None
    generated_preview_text: str
    generated_full_text: str
    final_text: str
    summary_for_admin: str | None
    review_comment: str | None
    created_at: str | None
    updated_at: str | None
    paid_at: str | None
    reviewed_at: str | None
    sent_at: str | None


class ClaimFileOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    file_role: str
    uploaded_at: str | None


class AdminClaimStatusIn(BaseModel):
    status: str


class AdminClaimFinalTextIn(BaseModel):
    final_text: str


@router.get("/admin/claims", response_model=AdminClaimListOut)
async def get_admin_claims_list(
    status: str | None = Query(default=None),
    generation_state: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin=Depends(require_claims_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        items = await list_admin_claims(
            session,
            status=status,
            generation_state=generation_state,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"items": items}


@router.get("/admin/claims/{claim_id}", response_model=AdminClaimOut)
async def get_admin_claim_by_id(
    claim_id: int,
    _admin=Depends(require_claims_admin),
    session: AsyncSession = Depends(get_session),
):
    claim = await get_admin_claim(session, claim_id=claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="claim not found")
    return claim


@router.post("/admin/claims/{claim_id}/status", response_model=AdminClaimOut)
async def set_admin_claim_status(
    claim_id: int,
    payload: AdminClaimStatusIn,
    _admin=Depends(require_claims_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        claim = await update_admin_claim_status(
            session,
            claim_id=claim_id,
            target_status=payload.status,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="claim not found")
    except ValueError as exc:
        detail = str(exc)
        if detail == "invalid_transition":
            raise HTTPException(status_code=409, detail="invalid_transition")
        if detail == "use_send_action":
            raise HTTPException(status_code=409, detail="use_send_action")
        raise HTTPException(status_code=400, detail=detail)

    await session.commit()
    return claim


@router.post("/admin/claims/{claim_id}/final-text", response_model=AdminClaimOut)
async def set_admin_claim_final_text(
    claim_id: int,
    payload: AdminClaimFinalTextIn,
    _admin=Depends(require_claims_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        claim = await update_admin_claim_final_text(
            session,
            claim_id=claim_id,
            final_text=payload.final_text,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="claim not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await session.commit()
    return claim


@router.post("/admin/claims/{claim_id}/send", response_model=AdminClaimOut)
async def send_admin_claim_to_client(
    claim_id: int,
    _admin=Depends(require_claims_admin),
    session: AsyncSession = Depends(get_session),
):
    claim = await get_claim_by_id(session, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="claim not found")

    try:
        to_email, final_text = prepare_admin_claim_send(claim)
    except ValueError as exc:
        detail = str(exc)
        if detail in {
            "invalid_transition",
            "already_sent",
            "client_email_required",
            "final_text_required",
        }:
            raise HTTPException(status_code=409, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    try:
        send_result = send_claim_final_result(
            settings,
            claim_id=claim.id,
            client_email=to_email,
            final_text=final_text,
        )
    except NotificationSendError as exc:
        await append_admin_claim_send_failed_event(
            session,
            claim_id=claim.id,
            to_email=to_email,
            error_code=exc.code,
            error_payload=exc.payload,
        )
        await session.commit()
        raise HTTPException(status_code=502, detail=exc.code)

    snapshot = await send_admin_claim_final_result(
        session,
        claim_id=claim.id,
        to_email=send_result["to_email"],
    )
    await session.commit()
    return snapshot


@router.get("/admin/claims/{claim_id}/files", response_model=list[ClaimFileOut])
async def get_admin_claim_files_list(
    claim_id: int,
    _admin=Depends(require_claims_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        files = await get_admin_claim_files(session, claim_id=claim_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="claim not found")
    return files
