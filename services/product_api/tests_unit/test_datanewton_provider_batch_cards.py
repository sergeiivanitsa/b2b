import logging

import httpx
import pytest

from product_api.providers.datanewton import (
    DataNewtonAccessDeniedError,
    DataNewtonAuthenticationError,
    DataNewtonClient,
    DataNewtonConfigurationError,
    DataNewtonDisabledError,
    DataNewtonInvalidResponseError,
    DataNewtonNotFoundError,
    DataNewtonValidationError,
    calculate_response_hash,
)
from product_api.settings import Settings

API_KEY = "unit-test-datanewton-secret"


def _build_settings(**overrides) -> Settings:
    values = {
        "DATABASE_URL": "postgresql+asyncpg://app:app@postgres:5432/app",
        "GATEWAY_URL": "http://gateway_api:8001",
        "GATEWAY_SHARED_SECRET": "test-shared-secret",
        "AUTH_TOKEN_SECRET": "test-auth-secret",
        "CLAIM_EDIT_TOKEN_SECRET": "test-claim-edit-secret",
        "CLAIMS_UPLOAD_DIR": "C:/tmp/claims",
        "INVITE_TOKEN_SECRET": "test-invite-secret",
        "SESSION_SECRET": "test-session-secret",
        "EMAIL_FROM": "no-reply@example.com",
        "DATANEWTON_ENABLED": True,
        "DATANEWTON_API_KEY": API_KEY,
        "DATANEWTON_RETRY_COUNT": 0,
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.mark.asyncio
async def test_disabled_mode_does_not_make_request():
    called = False

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    client = DataNewtonClient(
        _build_settings(DATANEWTON_ENABLED=False),
        http_transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(DataNewtonDisabledError) as error:
            await client.fetch_batch_cards(["7701234567"], request_id="req-disabled")
        assert error.value.attempts == 0
        assert called is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_missing_api_key_is_configuration_error_without_request():
    client = DataNewtonClient(
        _build_settings(DATANEWTON_API_KEY=None),
        http_transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
    )
    try:
        with pytest.raises(DataNewtonConfigurationError) as error:
            await client.fetch_batch_cards(["7701234567"])
        assert error.value.attempts == 0
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_successful_batch_cards_preserves_raw_payload_and_request_contract(caplog):
    captured_request = None
    payload = {
        "cards": [{"inn": "7701234567", "unmodeled_block": {"value": "сохранено"}}],
        "rateLimit": {"remaining": 42},
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json=payload, headers={"X-RateLimit-Remaining": "42"})

    caplog.set_level(logging.INFO)
    client = DataNewtonClient(
        _build_settings(),
        http_transport=httpx.MockTransport(handler),
    )
    try:
        result = await client.fetch_batch_cards(
            ["77 01-23-45-67", "7701234567", "1027700132195"],
            request_id="req-123",
        )
    finally:
        await client.aclose()

    assert captured_request is not None
    assert captured_request.method == "POST"
    assert captured_request.url.path == "/v1/batchCards"
    assert captured_request.url.params["key"] == API_KEY
    assert captured_request.headers["X-Request-ID"] == "req-123"
    assert captured_request.read() == (
        b'{"source_inns_or_ogrns":["7701234567","1027700132195"]}'
    )
    assert result.raw_payload == payload
    assert result.requested_identifiers == ["7701234567", "1027700132195"]
    assert result.status_code == 200
    assert result.attempts == 1
    assert result.response_hash == calculate_response_hash(payload)
    assert result.provider_limit_metadata == {
        "payload": {"rateLimit": {"remaining": 42}},
        "headers": {"x-ratelimit-remaining": "42"},
    }
    combined_logs = "\n".join(record.getMessage() for record in caplog.records)
    safe_representations = f"{result!r}\n{client!r}"
    assert API_KEY not in combined_logs
    assert API_KEY not in safe_representations
    assert "7701234567" not in combined_logs


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
async def test_non_retryable_http_errors_are_safely_classified(status_code, error_type):
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code, text=f"unsafe raw body {API_KEY}")

    client = DataNewtonClient(
        _build_settings(DATANEWTON_RETRY_COUNT=3),
        http_transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(error_type) as error:
            await client.fetch_batch_cards(["7701234567"], request_id="req-error")
    finally:
        await client.aclose()

    assert attempts == 1
    assert error.value.attempts == 1
    assert error.value.status_code == status_code
    assert error.value.retryable is False
    assert API_KEY not in str(error.value)
    assert API_KEY not in repr(error.value)
    assert "unsafe raw body" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected_message"),
    [
        (httpx.Response(200, content=b"not-json"), "not valid JSON"),
        (httpx.Response(200, json=[{"inn": "7701234567"}]), "root must be an object"),
    ],
)
async def test_invalid_response_shape_raises_typed_error(response, expected_message):
    client = DataNewtonClient(
        _build_settings(),
        http_transport=httpx.MockTransport(lambda _request: response),
    )
    try:
        with pytest.raises(DataNewtonInvalidResponseError) as error:
            await client.fetch_batch_cards(["7701234567"])
    finally:
        await client.aclose()

    assert expected_message in str(error.value)
    assert error.value.attempts == 1
