from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.schemas import (
    CompanyReportAcceptedResponse,
    CompanyReportCreateRequest,
    CompanyReportGetQuery,
    CompanyReportResponse,
    CompanyReportStatusResponse,
)
from product_api.company_reports.company_card_v2.arbitration_keyring import (
    normalize_arbitration_mask_key_id,
)
from product_api.company_reports.persistence.errors import (
    CompanyReportJobStateConflictError,
    CompanyReportPersistenceError,
)
from product_api.company_reports.persistence.presentations import (
    PresentationAssignmentConflict,
    PresentationLifecycleInvalid,
    PresentationLifecycleNotFound,
    create_or_reuse_h2_presentation,
    resolve_presentation_lifecycle,
)
from product_api.company_reports.persistence.models import (
    CompanyReportH2LifecycleHead,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.jobs import (
    H2_PRESENTATION_CONTRACT,
    H2_WRITER_PROFILE,
)
from product_api.company_reports.service import (
    CompanyReportPendingError,
    CompanyReportServiceError,
    CompanyReportServiceInternalError,
    CompanyReportServiceNotFoundError,
    CompanyReportServiceStateConflictError,
    CompanyReportServiceUnavailableError,
    InvalidCompanyReportIdentifierError,
    create_or_reuse_company_report,
    get_company_report_status,
    get_latest_company_report,
    validate_company_report_inn,
)
from product_api.company_reports.public_h1 import CompanyPublicH1Response
from product_api.company_reports.public_h1_service import (
    PublicH1Error, PublicH1FailedError, PublicH1InvalidInnError, PublicH1NotEligibleError,
    PublicH1NotFoundError, PublicH1PendingError, PublicH1UnavailableError,
    PublicProjectionInvalidError, resolve_public_h1,
)
from product_api.db.session import get_session
from product_api.rate_limit import RateLimitConfig, RateLimiter
from product_api.settings import get_settings
from product_api.company_reports.company_card_v2.service import (
    PublicH2Error,
    PublicH2Failed,
    PublicH2Invalid,
    PublicH2NotEligible,
    PublicH2NotFound,
    PublicH2Pending,
    h2_cohort_selected,
    resolve_direct_public_h2,
    resolve_public_h2,
)

router = APIRouter(prefix="/company-reports", tags=["company-reports"])
logger = logging.getLogger(__name__)
settings = get_settings()

_expensive_ip_limiter = RateLimiter(
    RateLimitConfig(max_requests=settings.rate_limit_ip_rpm, window_seconds=60)
)
_read_ip_limiter = RateLimiter(
    RateLimitConfig(max_requests=settings.rate_limit_ip_rpm, window_seconds=60)
)


@router.post(
    "",
    response_model=CompanyReportAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_company_report(
    payload: CompanyReportCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> CompanyReportAcceptedResponse:
    _enforce_report_rate_limit(
        request,
        expensive=True,
    )
    try:
        current = get_settings()
        if current.company_card_v2_direct_launch_enabled:
            return await _create_or_reuse_direct_h2(
                session,
                inn=payload.inn,
                settings=current,
            )
        return await create_or_reuse_company_report(
            session,
            inn=payload.inn,
        )
    except CompanyReportServiceError as exc:
        raise _http_error(exc) from exc
    except Exception:
        logger.error("unexpected company report create failure")
        raise _http_error(CompanyReportServiceInternalError()) from None


@router.get(
    "/{inn}/status",
    response_model=CompanyReportStatusResponse,
)
async def company_report_status(
    inn: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> CompanyReportStatusResponse:
    _reject_unexpected_query_parameters(request)
    _enforce_report_rate_limit(
        request,
        expensive=False,
    )
    try:
        current = get_settings()
        if current.company_card_v2_direct_launch_enabled:
            response = await _get_direct_h2_status(
                session,
                inn=inn,
                rollout_generation=current.company_card_v2_rollout_generation,
            )
        else:
            return await get_company_report_status(session, inn=inn)
        if response.status in {"pending", "failed"}:
            return response
        normalized = validate_company_report_inn(inn)
        try:
            await resolve_direct_public_h2(
                session,
                inn=normalized,
                rollout_generation=current.company_card_v2_rollout_generation,
            )
        except (PublicH2NotFound, PublicH2Pending, PublicH2NotEligible):
            # The H2 writer may already be final while the narrative worker is
            # still producing (or persisting) the exact saved-result binding.
            # Keep the existing SPA lifecycle pending until the SSR document
            # can be resolved without any request-time write.
            return response.model_copy(
                update={
                    "status": "pending",
                    "generated_at": None,
                    "finished_at": None,
                    "fresh_until": None,
                }
            )
        except SQLAlchemyError as exc:
            raise CompanyReportServiceUnavailableError() from exc
        except PublicH2Error as exc:
            raise CompanyReportServiceInternalError() from exc
        return response.model_copy(
            update={"public_document_path": f"/company/{normalized}"}
        )
    except CompanyReportServiceError as exc:
        raise _http_error(exc) from exc
    except Exception:
        logger.error("unexpected company report status failure")
        raise _http_error(CompanyReportServiceInternalError()) from None


async def _get_direct_h2_status(
    session: AsyncSession,
    *,
    inn: str,
    rollout_generation: int,
) -> CompanyReportStatusResponse:
    """Resolve the durable H2 lifecycle head, never the legacy H1 selector."""
    normalized = validate_company_report_inn(inn)
    if type(rollout_generation) is not int or rollout_generation <= 0:
        raise CompanyReportServiceInternalError()
    try:
        subject = await session.scalar(
            select(CompanyReportSubject).where(
                CompanyReportSubject.normalized_identifier == normalized
            )
        )
        if subject is None:
            raise CompanyReportServiceNotFoundError()
        head = await session.get(CompanyReportH2LifecycleHead, subject.id)
        if head is None:
            raise CompanyReportServiceNotFoundError()
        if head.rollout_generation != rollout_generation:
            raise CompanyReportServiceNotFoundError()
        if (
            head.subject_id != subject.id
            or head.presentation_contract != H2_PRESENTATION_CONTRACT
        ):
            raise CompanyReportServiceStateConflictError()
        resolved = await resolve_presentation_lifecycle(
            session,
            head.presentation_id,
        )
        record = await session.get(CompanyReportRecord, resolved.report_id)
        if (
            record is None
            or head.subject_id != subject.id
            or head.report_id != resolved.report_id
            or resolved.presentation_contract != H2_PRESENTATION_CONTRACT
            or resolved.normalized_identifier != normalized
            or record.id != head.report_id
            or record.subject_id != subject.id
            or record.writer_profile != H2_WRITER_PROFILE
            or record.presentation_contract != H2_PRESENTATION_CONTRACT
            or record.report_version != "3"
            or record.rollout_generation != rollout_generation
            or record.lifecycle_status != resolved.lifecycle_status
        ):
            raise CompanyReportServiceStateConflictError()
    except CompanyReportServiceError:
        raise
    except PresentationLifecycleNotFound as exc:
        raise CompanyReportServiceNotFoundError() from exc
    except PresentationLifecycleInvalid as exc:
        raise CompanyReportServiceStateConflictError() from exc
    except (CompanyReportPersistenceError, SQLAlchemyError) as exc:
        raise CompanyReportServiceUnavailableError() from exc
    return CompanyReportStatusResponse(
        report_id=record.id,
        status=record.lifecycle_status,
        started_at=record.started_at,
        generated_at=record.generated_at,
        finished_at=record.finished_at,
        fresh_until=record.fresh_until,
    )


async def _create_or_reuse_direct_h2(
    session: AsyncSession,
    *,
    inn: str,
    settings: object,
) -> CompanyReportAcceptedResponse:
    """Create the global H2 writer decision without an H1/assignment detour."""
    normalized = validate_company_report_inn(inn)
    if (
        not getattr(settings, "company_card_v2_direct_launch_enabled", False)
        or not getattr(settings, "company_card_v2_writer_enabled", False)
        or not h2_cohort_selected(inn=normalized, settings=settings)
    ):
        raise CompanyReportServiceUnavailableError()

    arbitration_enabled = bool(
        getattr(settings, "company_card_v2_arbitration_collection_enabled", False)
    )
    try:
        arbitration_key_id = (
            normalize_arbitration_mask_key_id(
                getattr(
                    settings,
                    "company_card_v2_arbitration_mask_active_key_id",
                    None,
                )
            )
            if arbitration_enabled
            else None
        )
        _presentation, enqueued, _head = await create_or_reuse_h2_presentation(
            session,
            identifier=normalized,
            rollout_generation=getattr(
                settings, "company_card_v2_rollout_generation"
            ),
            arbitration_collection_enabled=arbitration_enabled,
            arbitration_mask_key_id=arbitration_key_id,
        )
        await session.commit()
    except (CompanyReportJobStateConflictError, PresentationAssignmentConflict) as exc:
        await session.rollback()
        raise CompanyReportServiceStateConflictError() from exc
    except (CompanyReportPersistenceError, SQLAlchemyError) as exc:
        await session.rollback()
        raise CompanyReportServiceUnavailableError() from exc
    except (AttributeError, TypeError, ValueError) as exc:
        await session.rollback()
        raise CompanyReportServiceInternalError() from exc
    return CompanyReportAcceptedResponse(
        report_id=enqueued.report_id,
        status="pending",
        reused=enqueued.reused,
    )


@router.get(
    "/{inn}/public-h1",
    response_model=CompanyPublicH1Response,
)
async def public_company_report_h1(
    inn: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Anonymous and side-effect free public projection."""
    if request.query_params:
        return _h1_response(
            status_code=422,
            content={
                "detail": [
                    {
                        "type": "extra_forbidden",
                        "loc": ["query", key],
                        "msg": "Extra inputs are not permitted",
                        "input": value,
                    }
                    for key, value in request.query_params.multi_items()
                ]
            },
        )
    try:
        _enforce_report_rate_limit(request, expensive=False)
    except HTTPException:
        return _h1_error(429, "rate_limited", "rate limit")
    if not (inn.isascii() and inn.isdigit() and len(inn) in {10, 12}):
        return _h1_error(400, "invalid_inn", "invalid INN")
    current = get_settings()
    if current.company_card_v2_direct_launch_enabled:
        # Preserve the legacy SPA's create-on-404 contract without allowing a
        # reload to supersede an already-running/current H2 lifecycle.  A
        # current head is reported as pending (or failed) until SSR can own the
        # final document; only the absence of a current-generation H2 permits
        # the SPA to POST a new report.
        try:
            await resolve_direct_public_h2(
                session,
                inn=inn,
                rollout_generation=current.company_card_v2_rollout_generation,
            )
        except PublicH2NotFound:
            return _h1_error(
                404,
                "company_report_not_found",
                "company report not found",
            )
        except PublicH2Failed:
            return _h1_error(409, "report_failed", "company report failed")
        except (PublicH2Pending, PublicH2NotEligible):
            return _h1_error(409, "report_pending", "company report is pending")
        except PublicH2Error:
            return _h1_error(
                500,
                "public_projection_invalid",
                "public company projection is invalid",
            )
        except SQLAlchemyError:
            return _h1_error(
                503,
                "company_report_unavailable",
                "company report service is unavailable",
            )
        return _h1_error(409, "report_pending", "company report is pending")
    try:
        dto = await resolve_public_h1(session, inn=inn)
        # Validate again at the serialization boundary.
        dto = CompanyPublicH1Response.model_validate(dto.model_dump(mode="python"))
        return _h1_response(content=dto.model_dump(mode="json"))
    except PublicH1Error as exc:
        mapping = {
            PublicH1NotFoundError: 404,
            PublicH1InvalidInnError: 400,
            PublicH1PendingError: 409,
            PublicH1FailedError: 409,
            PublicH1NotEligibleError: 409,
            PublicH1UnavailableError: 503,
            PublicProjectionInvalidError: 500,
        }
        return _h1_error(mapping.get(type(exc), 500), exc.code, exc.message)
    except Exception:
        logger.error("unexpected public H1 read failure")
        return _h1_error(500, "public_projection_invalid", "public company projection is invalid")


@router.api_route("/{inn}/public-h2", methods=["GET", "HEAD"])
async def public_company_report_h2(
    inn: str,
    request: Request,
) -> JSONResponse:
    """Default-off, side-effect-free H2 read endpoint."""
    current = get_settings()
    headers = _h1_headers()
    if request.query_params:
        return JSONResponse(status_code=422, content={"detail": {"code": "public_h2_query_forbidden", "message": "query parameters are not permitted"}}, headers=headers)
    if not (inn.isascii() and inn.isdigit() and len(inn) in {10, 12}):
        return JSONResponse(status_code=422, content={"detail": {"code": "invalid_company_identifier", "message": "invalid INN"}}, headers=headers)
    accepted = request.headers.get("accept", "*/*")
    if not any(item.strip().split(";", 1)[0] in {"*/*", "application/json"} for item in accepted.split(",")):
        return JSONResponse(status_code=406, content={"detail": {"code": "not_acceptable", "message": "application/json is required"}}, headers=headers)
    try:
        _enforce_report_rate_limit(request, expensive=False)
    except HTTPException:
        return JSONResponse(status_code=429, content={"detail": {"code": "rate_limited", "message": "rate limit"}}, headers=headers)
    # This decision intentionally precedes any DB access and consequently
    # cannot enqueue work, evaluate signals, or consume providers.
    if not h2_cohort_selected(inn=inn, settings=current):
        return JSONResponse(status_code=404, content={"detail": {"code": "company_public_h2_disabled", "message": "company card v2 is disabled"}}, headers=headers)
    # Do not put ``get_session`` in the route signature: FastAPI resolves
    # dependencies before the handler body, which would violate default-off
    # before DB dependency resolution.  The generator is entered only after
    # the complete header/identifier/feature decision above.
    async for session in get_session():
        try:
            if current.company_card_v2_direct_launch_enabled:
                dto = await resolve_direct_public_h2(
                    session,
                    inn=inn,
                    rollout_generation=current.company_card_v2_rollout_generation,
                )
            else:
                dto = await resolve_public_h2(session, inn=inn)
            response = JSONResponse(content=dto.model_dump(mode="json"), headers=headers)
            if request.method == "HEAD":
                response.body = b""
            return response
        except PublicH2NotFound as exc:
            return JSONResponse(status_code=404, content={"detail": {"code": exc.code, "message": str(exc)}}, headers=headers)
        except PublicH2NotEligible as exc:
            return JSONResponse(status_code=409, content={"detail": {"code": exc.code, "message": "company card v2 is not eligible"}}, headers=headers)
        except PublicH2Error as exc:
            return JSONResponse(status_code=500, content={"detail": {"code": exc.code, "message": "company card v2 is unavailable"}}, headers=headers)
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": {
                        "code": "company_report_unavailable",
                        "message": "company report service is unavailable",
                    }
                },
                headers=headers,
            )
    return JSONResponse(status_code=500, content={"detail": {"code": "company_public_h2_unavailable", "message": "company card v2 is unavailable"}}, headers=headers)


@router.get(
    "/{inn}",
    response_model=CompanyReportResponse,
)
async def latest_company_report(
    inn: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> CompanyReportResponse:
    query = _parse_get_query(request)
    _enforce_report_rate_limit(
        request,
        expensive=query.include_ai_explanation,
    )
    current = get_settings()
    if current.company_card_v2_direct_launch_enabled:
        try:
            normalized = validate_company_report_inn(inn)
        except CompanyReportServiceError as exc:
            raise _http_error(exc) from exc
        # This unversioned endpoint is the legacy H1 JSON contract.  Returning
        # a historical H1 after a direct H2 POST would be split-brain.  Fail
        # closed with the additive public-document handoff used by the status
        # contract; direct-launch clients must navigate to the SSR document.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "company_report_h2_document",
                "message": "company report uses the H2 document lifecycle",
                "public_document_path": f"/company/{normalized}",
            },
        )
    try:
        return await get_latest_company_report(
            session,
            inn=inn,
            settings=settings,
            include_ai_explanation=query.include_ai_explanation,
        )
    except CompanyReportServiceError as exc:
        raise _http_error(exc) from exc
    except Exception:
        logger.error("unexpected company report read failure")
        raise _http_error(CompanyReportServiceInternalError()) from None


def _parse_get_query(request: Request) -> CompanyReportGetQuery:
    items = list(request.query_params.multi_items())
    if len(items) != len({key for key, _ in items}):
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query",),
                    "msg": "query parameters must not be repeated",
                    "input": None,
                    "ctx": {"error": "duplicate query parameter"},
                }
            ]
        )
    try:
        return CompanyReportGetQuery.model_validate(dict(items))
    except ValidationError as exc:
        errors = []
        for error in exc.errors():
            copied = dict(error)
            copied["loc"] = ("query", *tuple(error.get("loc", ())))
            errors.append(copied)
        raise RequestValidationError(errors) from exc


def _reject_unexpected_query_parameters(request: Request) -> None:
    if request.query_params:
        raise RequestValidationError(
            [
                {
                    "type": "extra_forbidden",
                    "loc": ("query", key),
                    "msg": "Extra inputs are not permitted",
                    "input": value,
                }
                for key, value in request.query_params.multi_items()
            ]
        )


def _enforce_report_rate_limit(
    request: Request,
    *,
    expensive: bool,
) -> None:
    if expensive:
        ip_limiter = _expensive_ip_limiter
        bucket = "expensive"
    else:
        ip_limiter = _read_ip_limiter
        bucket = "read"
    client_ip = request.client.host if request.client is not None else "unknown"
    ip_key = f"company-report:{bucket}:ip:{client_ip}"
    if not ip_limiter.allow(ip_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "rate limit"},
        )


def _http_error(error: CompanyReportServiceError) -> HTTPException:
    if isinstance(error, InvalidCompanyReportIdentifierError):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(error, CompanyReportServiceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(
        error,
        (CompanyReportPendingError, CompanyReportServiceStateConflictError),
    ):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(error, CompanyReportServiceUnavailableError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": error.safe_message},
    )


def _h1_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "X-Robots-Tag": "noindex,follow",
        "X-Content-Type-Options": "nosniff",
    }


def _h1_error(status_code: int, code: str, message: str) -> JSONResponse:
    return _h1_response(status_code=status_code, content={"detail": {"code": code, "message": message}})


def _h1_response(*, status_code: int = 200, content: object) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=content, headers=_h1_headers())


__all__ = ["router"]
