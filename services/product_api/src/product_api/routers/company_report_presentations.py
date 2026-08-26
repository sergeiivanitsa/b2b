"""Default-off H2 presentation endpoints.

The route intentionally has no cohort override and checks the rollout switch
before asking for a database session. The v3 worker is not activated here.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.persistence.models import CompanyReportPresentation, CompanyReportRecord
from product_api.company_reports.persistence.presentations import PresentationAssignmentConflict, create_or_reuse_h2_presentation
from product_api.company_reports.persistence.errors import CompanyReportJobStateConflictError
from product_api.company_reports.company_card_v2.service import h2_cohort_selected
from product_api.company_reports.company_card_v2.arbitration_keyring import (
    normalize_arbitration_mask_key_id,
)
from product_api.db.session import get_session
from product_api.settings import get_settings

router = APIRouter(prefix="/company-report-presentations", tags=["company-report-presentations"])


class _CreatePresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str


def _disabled() -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": {"code": "company_public_h2_disabled", "message": "company card v2 is disabled"}}, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex,follow"})


@router.post("")
async def create_presentation(payload: _CreatePresentation, request: Request) -> JSONResponse:
    settings = get_settings()
    if not h2_cohort_selected(inn=payload.identifier, settings=settings):
        return _disabled()
    if not settings.company_card_v2_writer_enabled:
        return JSONResponse(status_code=503, content={"detail": {"code": "company_card_v2_writer_unavailable", "message": "company card v2 writer is unavailable"}})
    arbitration_enabled = settings.company_card_v2_arbitration_collection_enabled
    arbitration_key_id = (
        normalize_arbitration_mask_key_id(
            settings.company_card_v2_arbitration_mask_active_key_id
        )
        if arbitration_enabled
        else None
    )
    async for session in get_session():
        try:
            presentation, enqueued, _head = await create_or_reuse_h2_presentation(
                session, identifier=payload.identifier,
                rollout_generation=settings.company_card_v2_rollout_generation,
                arbitration_collection_enabled=arbitration_enabled,
                arbitration_mask_key_id=arbitration_key_id,
            )
            await session.commit()
            return JSONResponse(status_code=202, content={
                "presentation_id": str(presentation.id), "report_id": str(enqueued.report_id),
                "status": enqueued.lifecycle_status, "reused": enqueued.reused,
            })
        except (CompanyReportJobStateConflictError, PresentationAssignmentConflict):
            await session.rollback()
            return JSONResponse(status_code=409, content={"detail": {"code": "report_writer_profile_conflict", "message": "active report uses another writer profile"}})


@router.get("/{presentation_id}/status")
async def presentation_status(presentation_id: UUID, request: Request) -> JSONResponse:
    settings = get_settings()
    if not settings.company_card_v2_presentations_enabled:
        return _disabled()
    # Keep default-off and an unavailable lifecycle from allocating a session.
    async for session in get_session():
        record = await session.get(CompanyReportPresentation, presentation_id)
        if record is None:
            return JSONResponse(status_code=404, content={"detail": {"code": "presentation_not_found", "message": "presentation was not found"}})
        report = await session.get(CompanyReportRecord, record.report_id)
        if report is None:
            return JSONResponse(status_code=500, content={"detail": {"code": "presentation_invalid", "message": "presentation binding is invalid"}})
        return JSONResponse(content={"presentation_id": str(record.id), "report_id": str(record.report_id), "status": report.lifecycle_status})
    return JSONResponse(status_code=500, content={"detail": {"code": "presentation_unavailable", "message": "presentation is unavailable"}})


__all__ = ["router"]
