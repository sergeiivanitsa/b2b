from __future__ import annotations

import asyncio
import email.utils
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from .errors import DataNewtonNetworkError

SleepCallable = Callable[[float], Awaitable[None]]
QueryParameter = str | int | float | bool | Sequence[str]
_SECRET_QUERY_NAMES = {"key", "api_key", "apikey"}


@dataclass(frozen=True, slots=True)
class DataNewtonTransportResponse:
    response: httpx.Response
    attempts: int
    duration_ms: float


class DataNewtonTransport:
    _INITIAL_BACKOFF_SECONDS = 0.25
    _MAX_BACKOFF_SECONDS = 2.0
    _MAX_RETRY_AFTER_SECONDS = 5.0

    def __init__(
        self,
        *,
        timeout_seconds: float,
        retry_count: int,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: SleepCallable = asyncio.sleep,
    ) -> None:
        if client is not None and transport is not None:
            raise ValueError("client and transport are mutually exclusive")
        self._timeout_seconds = timeout_seconds
        self._retry_count = max(retry_count, 0)
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(transport=transport)

    async def request(
        self,
        *,
        method: str,
        base_url: str,
        endpoint: str,
        api_key: str,
        query_params: Mapping[str, QueryParameter] | None = None,
        json_body: Mapping[str, Any] | None = None,
        request_id: str | None = None,
    ) -> DataNewtonTransportResponse:
        url = f"{base_url.rstrip('/')}{endpoint}"
        headers = {"X-Request-ID": request_id} if request_id else None
        started_at = time.perf_counter()
        attempts = 0

        while attempts <= self._retry_count:
            attempts += 1
            try:
                safe_query_params = {
                    name: value
                    for name, value in (query_params or {}).items()
                    if name.strip().lower() not in _SECRET_QUERY_NAMES
                }
                response = await self._client.request(
                    method,
                    url,
                    params={"key": api_key, **safe_query_params},
                    json=dict(json_body) if json_body is not None else None,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            except httpx.RequestError:
                if attempts > self._retry_count:
                    raise DataNewtonNetworkError(
                        "DataNewton network request failed",
                        endpoint=endpoint,
                        retryable=True,
                        attempts=attempts,
                        request_id=request_id,
                    ) from None
                await self._sleep(self._backoff_seconds(attempts, None))
                continue

            if not self._is_retryable_status(response.status_code):
                return self._result(response, attempts, started_at)
            if attempts > self._retry_count:
                return self._result(response, attempts, started_at)

            await self._sleep(
                self._backoff_seconds(attempts, response.headers.get("Retry-After"))
            )

        raise AssertionError("unreachable")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> DataNewtonTransport:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    def _backoff_seconds(self, attempts: int, retry_after: str | None) -> float:
        parsed_retry_after = self._parse_retry_after(retry_after)
        if parsed_retry_after is not None:
            return min(parsed_retry_after, self._MAX_RETRY_AFTER_SECONDS)
        exponential = self._INITIAL_BACKOFF_SECONDS * (2 ** (attempts - 1))
        return min(exponential, self._MAX_BACKOFF_SECONDS)

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if not value:
            return None
        stripped = value.strip()
        try:
            seconds = float(stripped)
        except ValueError:
            try:
                retry_at = email.utils.parsedate_to_datetime(stripped)
            except (TypeError, ValueError, OverflowError):
                return None
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
        if seconds < 0:
            return 0.0
        return seconds

    @staticmethod
    def _result(
        response: httpx.Response,
        attempts: int,
        started_at: float,
    ) -> DataNewtonTransportResponse:
        return DataNewtonTransportResponse(
            response=response,
            attempts=attempts,
            duration_ms=(time.perf_counter() - started_at) * 1000,
        )

