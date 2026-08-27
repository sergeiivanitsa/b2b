"""Default-off H2 presentation creation and exact lifecycle polling."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from product_api.company_reports.company_card_v2.arbitration_keyring import (
    normalize_arbitration_mask_key_id,
)
from product_api.company_reports.company_card_v2.service import h2_cohort_selected
from product_api.company_reports.persistence.errors import (
    CompanyReportJobStateConflictError,
    CompanyReportPersistenceError,
)
from product_api.company_reports.persistence.jobs import H2_PRESENTATION_CONTRACT
from product_api.company_reports.persistence.presentations import (
    PresentationAssignmentConflict,
    PresentationLifecycleInvalid,
    PresentationLifecycleNotFound,
    create_or_reuse_h2_presentation,
    resolve_presentation_lifecycle,
)
from product_api.company_reports.schemas import (
    CompanyReportPresentationCreateRequest,
    CompanyReportPresentationLifecycle,
)
from product_api.company_reports.service import (
    InvalidCompanyReportIdentifierError,
    validate_company_report_inn,
)
from product_api.db.session import get_session
from product_api.settings import get_settings

router = APIRouter(
    prefix="/company-report-presentations",
    tags=["company-report-presentations"],
)

_LIFECYCLE_STATUSES = frozenset(("pending", "complete", "partial", "failed"))
_SELECTOR_HEADERS = ("x-report-version", "x-writer-profile")
_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex,follow",
}


def _response(*, content: object, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=_RESPONSE_HEADERS,
    )


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return _response(
        status_code=status_code,
        content={"detail": {"code": code, "message": message}},
    )


def _guard_request(request: Request) -> JSONResponse | None:
    if request.query_params:
        return _error(
            422,
            "presentation_query_forbidden",
            "query parameters are not permitted",
        )
    if any(header in request.headers for header in _SELECTOR_HEADERS):
        return _error(
            422,
            "presentation_selector_forbidden",
            "presentation selectors are not permitted",
        )
    return None


def _disabled() -> JSONResponse:
    return _error(
        404,
        "company_public_h2_disabled",
        "company card v2 is disabled",
    )


def _lifecycle_response(
    resolved: object,
    *,
    reused: bool,
    status_code: int,
) -> JSONResponse:
    dto = CompanyReportPresentationLifecycle(
        presentation_id=getattr(resolved, "presentation_id"),
        presentation_contract=getattr(resolved, "presentation_contract"),
        report_id=getattr(resolved, "report_id"),
        lifecycle_status=getattr(resolved, "lifecycle_status"),
        public_read_path=(
            "/company-reports/"
            f"{getattr(resolved, 'normalized_identifier')}/public-h2"
        ),
        canonical_document_path=None,
        reused=reused,
    )
    return _response(
        status_code=status_code,
        content=dto.model_dump(mode="json"),
    )


def _created_binding_is_exact(
    *,
    presentation: object,
    enqueued: object,
    resolved: object,
    normalized_identifier: str,
    rollout_generation: int,
) -> bool:
    return (
        getattr(presentation, "id", None)
        == getattr(resolved, "presentation_id", None)
        and getattr(presentation, "subject_id", None)
        == getattr(enqueued, "subject_id", None)
        and getattr(presentation, "report_id", None)
        == getattr(enqueued, "report_id", None)
        == getattr(resolved, "report_id", None)
        and getattr(presentation, "presentation_contract", None)
        == getattr(resolved, "presentation_contract", None)
        == H2_PRESENTATION_CONTRACT
        and getattr(presentation, "rollout_generation", None)
        == rollout_generation
        and getattr(enqueued, "lifecycle_status", None)
        == getattr(resolved, "lifecycle_status", None)
        and getattr(resolved, "lifecycle_status", None) in _LIFECYCLE_STATUSES
        and type(getattr(enqueued, "reused", None)) is bool
        and getattr(resolved, "normalized_identifier", None)
        == normalized_identifier
    )


async def _rollback_safely(session: object) -> None:
    try:
        await getattr(session, "rollback")()
    except Exception:
        # The response remains closed even when storage is unavailable while
        # cleaning up a failed request.
        pass


@router.post(
    "",
    response_model=CompanyReportPresentationLifecycle,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_presentation(
    payload: CompanyReportPresentationCreateRequest,
    request: Request,
) -> JSONResponse:
    rejected = _guard_request(request)
    if rejected is not None:
        return rejected

    try:
        normalized_identifier = validate_company_report_inn(payload.identifier)
    except InvalidCompanyReportIdentifierError:
        return _error(422, "invalid_company_identifier", "invalid INN")

    settings = get_settings()
    if not h2_cohort_selected(inn=normalized_identifier, settings=settings):
        return _disabled()
    if not settings.company_card_v2_writer_enabled:
        return _error(
            503,
            "company_card_v2_writer_unavailable",
            "company card v2 writer is unavailable",
        )

    arbitration_enabled = settings.company_card_v2_arbitration_collection_enabled
    try:
        arbitration_key_id = (
            normalize_arbitration_mask_key_id(
                settings.company_card_v2_arbitration_mask_active_key_id
            )
            if arbitration_enabled
            else None
        )
    except (TypeError, ValueError):
        return _error(
            503,
            "presentation_unavailable",
            "presentation is unavailable",
        )

    session: object | None = None
    try:
        async for session in get_session():
            try:
                presentation, enqueued, _head = (
                    await create_or_reuse_h2_presentation(
                        session,
                        identifier=normalized_identifier,
                        rollout_generation=(
                            settings.company_card_v2_rollout_generation
                        ),
                        arbitration_collection_enabled=arbitration_enabled,
                        arbitration_mask_key_id=arbitration_key_id,
                    )
                )
                resolved = await resolve_presentation_lifecycle(
                    session,
                    presentation.id,
                )
                if not _created_binding_is_exact(
                    presentation=presentation,
                    enqueued=enqueued,
                    resolved=resolved,
                    normalized_identifier=normalized_identifier,
                    rollout_generation=(
                        settings.company_card_v2_rollout_generation
                    ),
                ):
                    await _rollback_safely(session)
                    return _error(
                        500,
                        "presentation_invalid",
                        "presentation binding is invalid",
                    )
                response = _lifecycle_response(
                    resolved,
                    reused=enqueued.reused,
                    status_code=202,
                )
                await session.commit()
                return response
            except (
                CompanyReportJobStateConflictError,
                PresentationAssignmentConflict,
            ):
                await _rollback_safely(session)
                return _error(
                    409,
                    "report_writer_profile_conflict",
                    "active report uses another writer profile",
                )
            except (PresentationLifecycleNotFound, PresentationLifecycleInvalid):
                await _rollback_safely(session)
                return _error(
                    500,
                    "presentation_invalid",
                    "presentation binding is invalid",
                )
            except (CompanyReportPersistenceError, SQLAlchemyError):
                await _rollback_safely(session)
                return _error(
                    503,
                    "presentation_unavailable",
                    "presentation is unavailable",
                )
            except (AttributeError, TypeError, ValueError, ValidationError):
                await _rollback_safely(session)
                return _error(
                    500,
                    "presentation_invalid",
                    "presentation binding is invalid",
                )
            except Exception:
                await _rollback_safely(session)
                return _error(
                    503,
                    "presentation_unavailable",
                    "presentation is unavailable",
                )
    except Exception:
        if session is not None:
            await _rollback_safely(session)
        return _error(
            503,
            "presentation_unavailable",
            "presentation is unavailable",
        )
    return _error(
        503,
        "presentation_unavailable",
        "presentation is unavailable",
    )


@router.get(
    "/{presentation_id}/status",
    response_model=CompanyReportPresentationLifecycle,
    status_code=status.HTTP_200_OK,
)
async def presentation_status(
    presentation_id: UUID,
    request: Request,
) -> JSONResponse:
    rejected = _guard_request(request)
    if rejected is not None:
        return rejected

    try:
        async for session in get_session():
            try:
                resolved = await resolve_presentation_lifecycle(
                    session,
                    presentation_id,
                )
                return _lifecycle_response(
                    resolved,
                    reused=True,
                    status_code=200,
                )
            except PresentationLifecycleNotFound:
                return _error(
                    404,
                    "presentation_not_found",
                    "presentation was not found",
                )
            except PresentationLifecycleInvalid:
                return _error(
                    500,
                    "presentation_invalid",
                    "presentation binding is invalid",
                )
            except (CompanyReportPersistenceError, SQLAlchemyError):
                return _error(
                    503,
                    "presentation_unavailable",
                    "presentation is unavailable",
                )
            except (AttributeError, TypeError, ValueError, ValidationError):
                return _error(
                    500,
                    "presentation_invalid",
                    "presentation binding is invalid",
                )
            except Exception:
                return _error(
                    503,
                    "presentation_unavailable",
                    "presentation is unavailable",
                )
    except Exception:
        return _error(
            503,
            "presentation_unavailable",
            "presentation is unavailable",
        )
    return _error(
        503,
        "presentation_unavailable",
        "presentation is unavailable",
    )


__all__ = ["router"]
