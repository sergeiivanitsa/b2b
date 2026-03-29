import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.auth import generate_raw_token
from product_api.claims.extraction import build_extraction_event_payload, run_claim_extraction
from product_api.claims.schemas import ClaimContactIn, ClaimPatchIn, Step2Out
from product_api.claims.storage import delete_claim_upload, save_claim_upload
from product_api.db.session import get_session
from product_api.gateway_client import GatewayError
from product_api.models import Claim
from product_api.settings import get_settings

from product_api.claims.repository import (
    apply_claim_contact,
    apply_claim_patch,
    apply_claim_extraction_result,
    append_claim_event,
    build_public_claim_snapshot,
    build_public_claim_file_snapshot,
    create_claim,
    create_claim_file,
    list_claim_files,
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


@router.post("/claims/{claim_id}/contact", response_model=PublicClaimOut)
async def update_public_claim_contact(
    payload: ClaimContactIn,
    claim: Claim = Depends(require_claim_access),
    session: AsyncSession = Depends(get_session),
):
    payload_fields = set(payload.model_fields_set)
    try:
        _, changed_fields = await apply_claim_contact(
            session,
            claim,
            client_email_value=payload.client_email,
            client_phone_provided="client_phone" in payload_fields,
            client_phone_value=payload.client_phone,
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
        raise HTTPException(status_code=400, detail=str(exc))
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
