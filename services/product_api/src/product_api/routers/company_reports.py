from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
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
from product_api.db.session import get_session
from product_api.rate_limit import RateLimitConfig, RateLimiter
from product_api.settings import get_settings

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


__all__ = ["router"]
