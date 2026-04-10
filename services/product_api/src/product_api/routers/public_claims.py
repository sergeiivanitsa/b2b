import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import generate_raw_token
from product_api.claims.extraction import build_extraction_event_payload, run_claim_extraction
from product_api.claims.generation import generate_claim_preview
from product_api.claims.notifications import (
    NotificationSendError,
    notify_admins_about_paid_claim,
)
from product_api.claims.rules import evaluate_claim_rules
from product_api.claims.schemas import ClaimContactIn, ClaimPatchIn, ClaimPreviewOut, Step2Out
from product_api.claims.storage import delete_claim_upload, save_claim_upload
from product_api.db.session import get_session
from product_api.gateway_client import GatewayError
from product_api.models import Claim
from product_api.settings import get_settings

from product_api.claims.repository import (
    apply_claim_contact,
    apply_claim_generation_preview,
    apply_claim_payment_stub,
    apply_claim_patch,
    apply_claim_extraction_result,
    append_claim_event,
    build_public_claim_preview_snapshot,
    build_public_claim_snapshot,
    build_public_claim_file_snapshot,
    create_claim,
    create_claim_file,
    get_claim_file,
    list_claim_files,
    remove_claim_file,
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


class ClaimFileOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    file_role: str
    uploaded_at: str | None


def _normalize_input_text(raw_value: str) -> str:
    normalized = raw_value.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="input_text is required")
    if len(normalized) > settings.max_message_chars:
        raise HTTPException(status_code=400, detail="input_text is too long")
    return normalized


def _normalize_file_role(raw_value: str) -> str:
    normalized = raw_value.strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="file_role is required")
    if len(normalized) > 32:
        raise HTTPException(status_code=400, detail="file_role is too long")
    if not re.fullmatch(r"[a-z0-9_]+", normalized):
        raise HTTPException(status_code=400, detail="invalid file_role")
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


@router.post("/claims/{claim_id}/contact", response_model=PublicClaimOut)
async def update_public_claim_contact(
    payload: ClaimContactIn,
    claim: Claim = Depends(require_claim_access),
    session: AsyncSession = Depends(get_session),
):
    try:
        _, changed_fields = await apply_claim_contact(
            session,
            claim,
            client_email_value=payload.client_email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    snapshot = build_public_claim_snapshot(claim)
    await append_claim_event(
        session,
        claim_id=claim.id,
        event_type="claim.contact_updated",
        payload_json={
            "changed_fields": changed_fields,
        },
    )
    await session.commit()
    return snapshot


@router.post("/claims/{claim_id}/generate-preview", response_model=ClaimPreviewOut)
async def generate_public_claim_preview(
    claim: Claim = Depends(require_claim_access),
    session: AsyncSession = Depends(get_session),
):
    decision = evaluate_claim_rules(
        case_type=claim.case_type,
        normalized_data=claim.normalized_data_json if isinstance(claim.normalized_data_json, dict) else None,
    )

    if decision["generation_state"] == "insufficient_data":
        await apply_claim_generation_preview(
            session,
            claim,
            generation_state=decision["generation_state"],
            risk_flags=decision["risk_flags"],
            allowed_blocks=decision["allowed_blocks"],
            blocked_blocks=decision["blocked_blocks"],
            generated_preview_text=None,
        )
        await append_claim_event(
            session,
            claim_id=claim.id,
            event_type="claim.preview_blocked_insufficient_data",
            payload_json={
                "missing_fields": decision["missing_fields"],
                "risk_flags": decision["risk_flags"],
            },
        )
        await session.commit()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "insufficient_data",
                "missing_fields": decision["missing_fields"],
            },
        )

    generation_result = await generate_claim_preview(
        settings,
        claim_id=claim.id,
        input_text=claim.input_text,
        case_type=claim.case_type,
        normalized_data=claim.normalized_data_json if isinstance(claim.normalized_data_json, dict) else None,
        decision=decision,
    )
    await apply_claim_generation_preview(
        session,
        claim,
        generation_state=decision["generation_state"],
        risk_flags=decision["risk_flags"],
        allowed_blocks=decision["allowed_blocks"],
        blocked_blocks=decision["blocked_blocks"],
        generated_preview_text=generation_result["generated_preview_text"],
    )
    await append_claim_event(
        session,
        claim_id=claim.id,
        event_type="claim.preview_generated",
        payload_json={
            "generation_state": decision["generation_state"],
            "used_fallback": generation_result["used_fallback"],
            "risk_flags": decision["risk_flags"],
            "allowed_blocks": decision["allowed_blocks"],
            "blocked_blocks": decision["blocked_blocks"],
        },
    )
    if generation_result["used_fallback"]:
        await append_claim_event(
            session,
            claim_id=claim.id,
            event_type="claim.preview_fallback",
            payload_json={"error_code": generation_result["error_code"]},
        )
    await session.commit()
    return build_public_claim_preview_snapshot(claim)


@router.get("/claims/{claim_id}/preview", response_model=ClaimPreviewOut)
async def get_public_claim_preview(
    claim: Claim = Depends(require_claim_access),
):
    preview = build_public_claim_preview_snapshot(claim)
    if claim.generation_state == "insufficient_data":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "insufficient_data",
                "missing_fields": preview["missing_fields"],
            },
        )
    if not preview["generated_preview_text"]:
        raise HTTPException(status_code=404, detail="preview not generated")
    return preview


@router.post("/claims/{claim_id}/pay", response_model=PublicClaimOut)
async def pay_public_claim(
    claim: Claim = Depends(require_claim_access),
    session: AsyncSession = Depends(get_session),
):
    try:
        _, changed_fields = await apply_claim_payment_stub(session, claim)
    except ValueError as exc:
        detail = str(exc)
        if detail == "insufficient_data":
            raise HTTPException(status_code=409, detail="insufficient_data")
        if detail == "already_paid_or_later_state":
            raise HTTPException(status_code=409, detail="already_paid_or_later_state")
        raise HTTPException(status_code=400, detail=detail)

    snapshot = build_public_claim_snapshot(claim)
    await append_claim_event(
        session,
        claim_id=claim.id,
        event_type="claim.paid_stub",
        payload_json={
            "payment_mode": "stub",
            "changed_fields": changed_fields,
            "status": claim.status,
            "generation_state": claim.generation_state,
        },
    )

    try:
        notification_payload = notify_admins_about_paid_claim(
            settings,
            claim_id=claim.id,
            case_type=claim.case_type,
            client_email=claim.client_email,
            price_rub=claim.price_rub,
        )
    except NotificationSendError as exc:
        await append_claim_event(
            session,
            claim_id=claim.id,
            event_type="claim.admin_paid_notification_failed",
            payload_json={
                "error_code": exc.code,
                "error_payload": exc.payload,
            },
        )
    else:
        await append_claim_event(
            session,
            claim_id=claim.id,
            event_type="claim.admin_paid_notification_sent",
            payload_json=notification_payload,
        )

    await session.commit()
    return snapshot


@router.post("/claims/{claim_id}/files", response_model=ClaimFileOut)
async def upload_public_claim_file(
    claim: Claim = Depends(require_claim_access),
    session: AsyncSession = Depends(get_session),
    file: UploadFile = File(...),
    file_role: str = Form(default="supporting_document"),
):
    normalized_file_role = _normalize_file_role(file_role)
    stored_upload = None
    try:
        stored_upload = await save_claim_upload(
            settings,
            claim_id=claim.id,
            upload_file=file,
        )
        claim_file = await create_claim_file(
            session,
            claim_id=claim.id,
            filename=stored_upload.filename,
            storage_path=stored_upload.storage_path,
            mime_type=stored_upload.mime_type,
            file_role=normalized_file_role,
        )
        await append_claim_event(
            session,
            claim_id=claim.id,
            event_type="claim.file_uploaded",
            payload_json={
                "file_id": claim_file.id,
                "file_role": claim_file.file_role,
                "mime_type": claim_file.mime_type,
                "size_bytes": stored_upload.size_bytes,
            },
        )
        await session.commit()
        return build_public_claim_file_snapshot(claim_file)
    except ValueError as exc:
        if stored_upload is not None:
            delete_claim_upload(settings, stored_upload.storage_path)
        detail = str(exc)
        status_code = 413 if detail == "file is too large" else 400
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception:
        if stored_upload is not None:
            delete_claim_upload(settings, stored_upload.storage_path)
        raise
    finally:
        await file.close()


@router.get("/claims/{claim_id}/files", response_model=list[ClaimFileOut])
async def get_public_claim_files(
    claim: Claim = Depends(require_claim_access),
    session: AsyncSession = Depends(get_session),
):
    files = await list_claim_files(session, claim.id)
    return [build_public_claim_file_snapshot(item) for item in files]


@router.delete("/claims/{claim_id}/files/{file_id}", status_code=204)
async def delete_public_claim_file(
    file_id: int,
    claim: Claim = Depends(require_claim_access),
    session: AsyncSession = Depends(get_session),
):
    if file_id <= 0:
        raise HTTPException(status_code=400, detail="invalid file_id")

    claim_file = await get_claim_file(session, claim.id, file_id)
    if claim_file is None:
        raise HTTPException(status_code=404, detail="file not found")

    storage_path = claim_file.storage_path
    await remove_claim_file(session, claim_file)
    await append_claim_event(
        session,
        claim_id=claim.id,
        event_type="claim.file_deleted",
        payload_json={
            "file_id": file_id,
        },
    )
    await session.commit()

    delete_claim_upload(settings, storage_path)
    return Response(status_code=204)
