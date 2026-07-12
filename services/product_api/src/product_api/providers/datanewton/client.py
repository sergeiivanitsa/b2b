from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, TypeVar

import httpx
from pydantic import ValidationError

from product_api.settings import Settings

from .cache_key import build_datanewton_cache_key
from .errors import (
    DataNewtonAuthenticationError,
    DataNewtonConfigurationError,
    DataNewtonDisabledError,
    DataNewtonInvalidResponseError,
    DataNewtonNotFoundError,
    DataNewtonRateLimitError,
    DataNewtonServerError,
    DataNewtonUnsupportedIdentifierError,
    DataNewtonValidationError,
)
from .models import (
    ARBITRATION_CASES_ENDPOINT,
    BANKRUPTCY_ENDPOINT,
    BATCH_CARDS_ENDPOINT,
    FSSP_ENDPOINT,
    TAX_INFO_ENDPOINT,
    ArbitrationCasesRequest,
    BankruptcyRequest,
    BatchCardsRequest,
    DataNewtonIdentifierType,
    DataNewtonResult,
    FsspRequest,
    SingleIdentifierRequest,
    TaxInfoRequest,
    calculate_response_hash,
)
from .transport import DataNewtonTransport, QueryParameter

logger = logging.getLogger(__name__)
RequestT = TypeVar("RequestT", bound=SingleIdentifierRequest)

_FSSP_SUPPORTED_IDENTIFIER_TYPES = {
    DataNewtonIdentifierType.LEGAL_ENTITY_INN,
    DataNewtonIdentifierType.OGRN,
}


class DataNewtonClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: DataNewtonTransport | None = None,
        http_client: httpx.AsyncClient | None = None,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if transport is not None and (http_client is not None or http_transport is not None):
            raise ValueError(
                "transport cannot be combined with http_client or http_transport"
            )
        self._settings = settings
        self._owns_transport = transport is None
        self._transport = transport or DataNewtonTransport(
            timeout_seconds=settings.datanewton_timeout_seconds,
            retry_count=settings.datanewton_retry_count,
            client=http_client,
            transport=http_transport,
        )

    async def fetch_batch_cards(
        self,
        identifiers: Sequence[str],
        *,
        request_id: str | None = None,
    ) -> DataNewtonResult:
        try:
            request = BatchCardsRequest(source_inns_or_ogrns=list(identifiers))
        except (ValidationError, DataNewtonValidationError) as exc:
            raise self._validation_error(
                dataset="batch_cards",
                endpoint=BATCH_CARDS_ENDPOINT,
                request_id=request_id,
                message="invalid batchCards identifiers",
            ) from exc

        body = request.model_dump(mode="json")
        return await self._execute(
            dataset="batch_cards",
            endpoint=BATCH_CARDS_ENDPOINT,
            method="POST",
            query_params={},
            json_body=body,
            requested_identifiers=request.source_inns_or_ogrns,
            request_parameters={},
            request_body=body,
            identifier_type=None,
            request_id=request_id,
        )

    async def fetch_tax_info(
        self,
        identifier: str,
        *,
        request_id: str | None = None,
    ) -> DataNewtonResult:
        request = self._validate_single_request(
            TaxInfoRequest,
            {"identifier": identifier},
            dataset="tax_info",
            endpoint=TAX_INFO_ENDPOINT,
            request_id=request_id,
        )
        query_params = request.identifier_query_params()
        return await self._execute(
            dataset="tax_info",
            endpoint=TAX_INFO_ENDPOINT,
            method="GET",
            query_params=query_params,
            json_body=None,
            requested_identifier=request.identifier,
            request_parameters=query_params,
            request_body=None,
            identifier_type=request.identifier_type,
            request_id=request_id,
        )

    async def fetch_arbitration_cases(
        self,
        identifier: str,
        *,
        offset: int = 0,
        limit: int = 100,
        company_role: str | None = None,
        status: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        updated_at_from: str | None = None,
        need_document: bool | None = None,
        request_id: str | None = None,
    ) -> DataNewtonResult:
        request = self._validate_single_request(
            ArbitrationCasesRequest,
            {
                "identifier": identifier,
                "offset": offset,
                "limit": limit,
                "company_role": company_role,
                "status": status,
                "start_date": start_date,
                "end_date": end_date,
                "updated_at_from": updated_at_from,
                "need_document": need_document,
            },
            dataset="arbitration_cases",
            endpoint=ARBITRATION_CASES_ENDPOINT,
            request_id=request_id,
        )
        query_params = request.query_params()
        return await self._execute(
            dataset="arbitration_cases",
            endpoint=ARBITRATION_CASES_ENDPOINT,
            method="GET",
            query_params=query_params,
            json_body=None,
            requested_identifier=request.identifier,
            request_parameters=query_params,
            request_body=None,
            identifier_type=request.identifier_type,
            request_id=request_id,
        )

    async def fetch_fssp(
        self,
        identifier: str,
        *,
        limit: int = 100,
        offset: int = 0,
        sort: str | None = None,
        order: str | None = None,
        filter: dict[str, object] | None = None,
        request_id: str | None = None,
    ) -> DataNewtonResult:
        request = self._validate_single_request(
            FsspRequest,
            {
                "identifier": identifier,
                "limit": limit,
                "offset": offset,
                "sort": sort,
                "order": order,
                "filter": filter,
            },
            dataset="fssp",
            endpoint=FSSP_ENDPOINT,
            request_id=request_id,
        )
        if request.identifier_type not in _FSSP_SUPPORTED_IDENTIFIER_TYPES:
            raise DataNewtonUnsupportedIdentifierError(
                "identifier type is not supported for the FSSP dataset",
                endpoint=FSSP_ENDPOINT,
                retryable=False,
                attempts=0,
                request_id=request_id,
                dataset="fssp",
                identifier_type=request.identifier_type.value,
            )

        body = request.body()
        return await self._execute(
            dataset="fssp",
            endpoint=FSSP_ENDPOINT,
            method="POST",
            query_params={},
            json_body=body,
            requested_identifier=request.identifier,
            request_parameters={},
            request_body=body,
            identifier_type=request.identifier_type,
            request_id=request_id,
        )

    async def fetch_bankruptcy(
        self,
        identifier: str,
        *,
        offset: int = 0,
        limit: int = 100,
        request_id: str | None = None,
    ) -> DataNewtonResult:
        request = self._validate_single_request(
            BankruptcyRequest,
            {"identifier": identifier, "offset": offset, "limit": limit},
            dataset="bankruptcy",
            endpoint=BANKRUPTCY_ENDPOINT,
            request_id=request_id,
        )
        query_params = request.query_params()
        return await self._execute(
            dataset="bankruptcy",
            endpoint=BANKRUPTCY_ENDPOINT,
            method="GET",
            query_params=query_params,
            json_body=None,
            requested_identifier=request.identifier,
            request_parameters=query_params,
            request_body=None,
            identifier_type=request.identifier_type,
            request_id=request_id,
        )

    async def _execute(
        self,
        *,
        dataset: str,
        endpoint: str,
        method: str,
        query_params: Mapping[str, QueryParameter],
        json_body: Mapping[str, Any] | None,
        requested_identifier: str | None = None,
        requested_identifiers: list[str] | None = None,
        request_parameters: Mapping[str, Any],
        request_body: Mapping[str, Any] | None,
        identifier_type: DataNewtonIdentifierType | None,
        request_id: str | None,
    ) -> DataNewtonResult:
        api_key = self._require_enabled_api_key(
            dataset=dataset,
            endpoint=endpoint,
            request_id=request_id,
        )

        # Canonicalize every request now; persistent caching is intentionally out of scope.
        build_datanewton_cache_key(
            dataset=dataset,
            base_url=self._settings.datanewton_base_url,
            method=method,
            endpoint=endpoint,
            query_params=query_params,
            body=json_body,
        )
        transport_result = await self._transport.request(
            method=method,
            base_url=self._settings.datanewton_base_url,
            endpoint=endpoint,
            api_key=api_key,
            query_params=query_params,
            json_body=json_body,
            request_id=request_id,
        )
        response = transport_result.response
        self._raise_for_status(
            dataset=dataset,
            endpoint=endpoint,
            status_code=response.status_code,
            attempts=transport_result.attempts,
            request_id=request_id,
        )
        raw_payload = self._parse_payload(
            response,
            dataset=dataset,
            endpoint=endpoint,
            attempts=transport_result.attempts,
            request_id=request_id,
        )
        response_hash = calculate_response_hash(raw_payload)
        result = DataNewtonResult(
            dataset=dataset,
            endpoint=endpoint,
            requested_identifier=requested_identifier,
            requested_identifiers=requested_identifiers or [],
            request_parameters=dict(request_parameters),
            request_body=dict(request_body) if request_body is not None else None,
            status_code=response.status_code,
            attempts=transport_result.attempts,
            duration_ms=transport_result.duration_ms,
            request_id=request_id,
            received_at=datetime.now(timezone.utc),
            raw_payload=raw_payload,
            response_hash=response_hash,
            provider_limit_metadata=_extract_provider_limit_metadata(
                raw_payload, response.headers
            ),
        )
        logger.info(
            "provider_request_completed provider=datanewton dataset=%s endpoint=%s "
            "request_id=%s status=%s attempts=%s duration_ms=%.3f "
            "identifier_type=%s response_hash_prefix=%s",
            dataset,
            endpoint,
            request_id,
            response.status_code,
            transport_result.attempts,
            transport_result.duration_ms,
            identifier_type.value if identifier_type is not None else "multiple",
            response_hash[:12],
        )
        return result

    def _require_enabled_api_key(
        self,
        *,
        dataset: str,
        endpoint: str,
        request_id: str | None,
    ) -> str:
        if not self._settings.datanewton_enabled:
            raise DataNewtonDisabledError(
                "DataNewton provider is disabled",
                endpoint=endpoint,
                request_id=request_id,
                dataset=dataset,
            )
        api_key = self._settings.datanewton_api_key
        if not api_key or not api_key.strip():
            raise DataNewtonConfigurationError(
                "DataNewton API key is not configured",
                endpoint=endpoint,
                request_id=request_id,
                dataset=dataset,
            )
        return api_key

    @classmethod
    def _validate_single_request(
        cls,
        request_type: type[RequestT],
        values: dict[str, Any],
        *,
        dataset: str,
        endpoint: str,
        request_id: str | None,
    ) -> RequestT:
        try:
            return request_type.model_validate(values)
        except (ValidationError, DataNewtonValidationError) as exc:
            raise cls._validation_error(
                dataset=dataset,
                endpoint=endpoint,
                request_id=request_id,
                message=f"invalid {dataset} request",
            ) from exc

    @staticmethod
    def _validation_error(
        *,
        dataset: str,
        endpoint: str,
        request_id: str | None,
        message: str,
    ) -> DataNewtonValidationError:
        return DataNewtonValidationError(
            message,
            endpoint=endpoint,
            retryable=False,
            attempts=0,
            request_id=request_id,
            dataset=dataset,
        )

    async def aclose(self) -> None:
        if self._owns_transport:
            await self._transport.aclose()

    async def __aenter__(self) -> DataNewtonClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    @staticmethod
    def _raise_for_status(
        *,
        dataset: str,
        endpoint: str,
        status_code: int,
        attempts: int,
        request_id: str | None,
    ) -> None:
        context = {
            "dataset": dataset,
            "endpoint": endpoint,
            "status_code": status_code,
            "attempts": attempts,
            "request_id": request_id,
        }
        if status_code in {401, 403}:
            raise DataNewtonAuthenticationError(
                "DataNewton authentication failed", retryable=False, **context
            )
        if status_code == 404:
            raise DataNewtonNotFoundError(
                "DataNewton endpoint was not found", retryable=False, **context
            )
        if status_code == 429:
            raise DataNewtonRateLimitError(
                "DataNewton rate limit exceeded", retryable=True, **context
            )
        if status_code >= 500:
            raise DataNewtonServerError(
                "DataNewton server error", retryable=True, **context
            )
        if status_code >= 400:
            raise DataNewtonValidationError(
                "DataNewton rejected the request", retryable=False, **context
            )

    @staticmethod
    def _parse_payload(
        response: httpx.Response,
        *,
        dataset: str,
        endpoint: str,
        attempts: int,
        request_id: str | None,
    ) -> dict[str, Any]:
        context = {
            "dataset": dataset,
            "endpoint": endpoint,
            "status_code": response.status_code,
            "retryable": False,
            "attempts": attempts,
            "request_id": request_id,
        }
        try:
            payload = response.json()
        except ValueError:
            raise DataNewtonInvalidResponseError(
                "DataNewton response is not valid JSON", **context
            ) from None
        if not isinstance(payload, dict):
            raise DataNewtonInvalidResponseError(
                "DataNewton response root must be an object", **context
            )
        return payload


def _extract_provider_limit_metadata(
    payload: dict[str, Any],
    headers: httpx.Headers,
) -> dict[str, Any] | None:
    metadata: dict[str, Any] = {}
    payload_limits = {
        key: value
        for key, value in payload.items()
        if "limit" in key.lower() or "quota" in key.lower()
    }
    if payload_limits:
        metadata["payload"] = payload_limits
    header_limits = {
        key.lower(): value
        for key, value in headers.items()
        if "ratelimit" in key.lower() or "rate-limit" in key.lower()
    }
    if header_limits:
        metadata["headers"] = header_limits
    return metadata or None
