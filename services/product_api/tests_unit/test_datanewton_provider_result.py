from datetime import datetime, timezone

import httpx
import pytest
from pydantic import ValidationError

from datanewton_provider_test_helpers import API_KEY, build_client
from product_api.providers.datanewton import (
    DataNewtonAccessDeniedError,
    DataNewtonAuthenticationError,
    DataNewtonInvalidResponseError,
    DataNewtonNetworkError,
    DataNewtonNotFoundError,
    DataNewtonResult,
    DataNewtonValidationError,
)


def _result_values():
    return {
        "dataset": "tax_info",
        "endpoint": "/v1/taxInfo",
        "requested_identifier": "7701234567",
        "request_parameters": {"inn": "7701234567"},
        "status_code": 200,
        "attempts": 1,
        "duration_ms": 1.5,
        "received_at": datetime.now(timezone.utc),
        "raw_payload": {"private_raw_marker": True},
        "response_hash": "a" * 64,
    }


def test_result_is_safe_immutable_and_has_defaults():
    result = DataNewtonResult(**_result_values())

    assert "private_raw_marker" not in repr(result)
    assert "7701234567" not in repr(result)
    assert result.received_at.tzinfo is timezone.utc
    assert result.warnings == []
    with pytest.raises(ValidationError):
        result.dataset = "changed"


@pytest.mark.parametrize(
    ("field", "value"),
    [("attempts", 0), ("duration_ms", -0.1), ("received_at", datetime.now())],
)
def test_result_validates_attempts_duration_and_timestamp(field, value):
    values = _result_values()
    values[field] = value

    with pytest.raises(ValidationError):
        DataNewtonResult(**values)


@pytest.mark.parametrize("missing_field", ["dataset", "endpoint"])
def test_result_requires_dataset_and_endpoint(missing_field):
    values = _result_values()
    values.pop(missing_field)

    with pytest.raises(ValidationError):
        DataNewtonResult(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, content=b"not-json"), "not valid JSON"),
        (httpx.Response(200, json=[]), "root must be an object"),
    ],
)
async def test_common_result_validation_rejects_invalid_json(response, message):
    client, transport = build_client(lambda _request: response)
    try:
        with pytest.raises(DataNewtonInvalidResponseError) as error:
            await client.fetch_tax_info("7701234567")
    finally:
        await transport.aclose()

    assert message in str(error.value)
    assert error.value.attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (400, DataNewtonValidationError),
        (401, DataNewtonAuthenticationError),
        (403, DataNewtonAccessDeniedError),
        (404, DataNewtonNotFoundError),
    ],
)
async def test_common_non_retryable_http_errors(status_code, error_type):
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code, text=f"unsafe {API_KEY}")

    client, transport = build_client(handler, retry_count=3)
    try:
        with pytest.raises(error_type) as error:
            await client.fetch_tax_info("7701234567", request_id="http-error")
    finally:
        await transport.aclose()

    assert attempts == 1
    assert error.value.attempts == 1
    assert API_KEY not in str(error.value)
    assert API_KEY not in repr(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("first_status", [429, 500])
async def test_common_retryable_http_status_recovers(first_status):
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(first_status, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    client, transport = build_client(handler, retry_count=1)
    try:
        result = await client.fetch_tax_info("7701234567")
    finally:
        await transport.aclose()

    assert attempts == 2
    assert result.attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("exception_type", [httpx.ReadTimeout, httpx.ConnectError])
async def test_common_transport_error_retries_then_fails_safely(exception_type):
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise exception_type("provider unavailable", request=request)

    client, transport = build_client(handler, retry_count=1)
    try:
        with pytest.raises(DataNewtonNetworkError) as error:
            await client.fetch_tax_info("7701234567")
    finally:
        await transport.aclose()

    assert attempts == 2
    assert error.value.attempts == 2
    assert API_KEY not in repr(error.value)

