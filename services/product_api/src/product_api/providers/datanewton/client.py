from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from product_api.settings import Settings

from .errors import (
    DataNewtonAuthenticationError,
    DataNewtonConfigurationError,
    DataNewtonDisabledError,
    DataNewtonInvalidResponseError,
    DataNewtonNotFoundError,
    DataNewtonRateLimitError,
    DataNewtonServerError,
    DataNewtonValidationError,
)
from .models import (
    BATCH_CARDS_ENDPOINT,
    BatchCardsRequest,
    DataNewtonResult,
    calculate_response_hash,
)
from .transport import DataNewtonTransport

logger = logging.getLogger(__name__)


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
            raise DataNewtonValidationError(
                "invalid batchCards identifiers",
                endpoint=BATCH_CARDS_ENDPOINT,
                request_id=request_id,
            ) from exc

        if not self._settings.datanewton_enabled:
            raise DataNewtonDisabledError(
                "DataNewton provider is disabled",
                endpoint=BATCH_CARDS_ENDPOINT,
                request_id=request_id,
            )

        api_key = self._settings.datanewton_api_key
        if not api_key or not api_key.strip():
            raise DataNewtonConfigurationError(
                "DataNewton API key is not configured",
                endpoint=BATCH_CARDS_ENDPOINT,
                request_id=request_id,
            )

        transport_result = await self._transport.request(
            method="POST",
            base_url=self._settings.datanewton_base_url,
            endpoint=BATCH_CARDS_ENDPOINT,
            api_key=api_key,
            json_body=request.model_dump(mode="json"),
            request_id=request_id,
        )
        response = transport_result.response
        self._raise_for_status(
            status_code=response.status_code,
            attempts=transport_result.attempts,
            request_id=request_id,
        )
        raw_payload = self._parse_payload(
            response,
            attempts=transport_result.attempts,
            request_id=request_id,
        )
        response_hash = calculate_response_hash(raw_payload)
        result = DataNewtonResult(
            requested_identifiers=request.source_inns_or_ogrns,
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
            "provider_request_completed provider=datanewton dataset=batch_cards "
            "endpoint=%s request_id=%s status=%s attempts=%s duration_ms=%.3f "
            "requested_count=%s response_hash_prefix=%s",
            BATCH_CARDS_ENDPOINT,
            request_id,
            response.status_code,
            transport_result.attempts,
            transport_result.duration_ms,
            len(request.source_inns_or_ogrns),
            response_hash[:12],
        )
        return result

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
        status_code: int,
        attempts: int,
        request_id: str | None,
    ) -> None:
        context = {
            "endpoint": BATCH_CARDS_ENDPOINT,
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
        attempts: int,
        request_id: str | None,
    ) -> dict[str, Any]:
        context = {
            "endpoint": BATCH_CARDS_ENDPOINT,
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

