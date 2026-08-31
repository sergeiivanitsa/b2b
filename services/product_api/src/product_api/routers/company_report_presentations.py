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

from product_api.company_reports.persistence.models import CompanyReportPresentation
from product_api.company_reports.company_card_v2.service import h2_cohort_selected
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
    # The only shipped writer profile is deliberately unreachable until a
    # later, separately approved activation iteration.
    return JSONResponse(status_code=503, content={"detail": {"code": "company_card_v2_writer_unavailable", "message": "company card v2 writer is unavailable"}})


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
        return JSONResponse(content={"presentation_id": str(record.id), "report_id": str(record.report_id), "status": "bound"})
    return JSONResponse(status_code=500, content={"detail": {"code": "presentation_unavailable", "message": "presentation is unavailable"}})


__all__ = ["router"]
