from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.schemas import (
    CompanyReportAcceptedResponse,
    CompanyReportCreateRequest,
    CompanyReportGetQuery,
    CompanyReportResponse,
    CompanyReportStatusResponse,
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
from product_api.company_reports.company_card_v2.service import PublicH2Error, PublicH2Invalid, PublicH2NotEligible, PublicH2NotFound, h2_cohort_selected, resolve_public_h2

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
        return await get_company_report_status(session, inn=inn)
    except CompanyReportServiceError as exc:
        raise _http_error(exc) from exc
    except Exception:
        logger.error("unexpected company report status failure")
        raise _http_error(CompanyReportServiceInternalError()) from None


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
