import httpx
import pytest

from product_api.providers.datanewton import (
    DataNewtonClient,
    DataNewtonNetworkError,
    DataNewtonRateLimitError,
    DataNewtonServerError,
    DataNewtonTransport,
)
from product_api.settings import Settings


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
        "DATANEWTON_API_KEY": "transport-test-secret",
        "DATANEWTON_RETRY_COUNT": 1,
    }
    values.update(overrides)
    return Settings.model_validate(values)


async def _no_sleep(_seconds: float) -> None:
    return None


def _client_with_transport(handler, *, retry_count=1):
    settings = _build_settings(DATANEWTON_RETRY_COUNT=retry_count)
    transport = DataNewtonTransport(
        timeout_seconds=settings.datanewton_timeout_seconds,
        retry_count=settings.datanewton_retry_count,
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
    )
    return DataNewtonClient(settings, transport=transport), transport


@pytest.mark.asyncio
async def test_429_retries_and_then_succeeds_with_attempt_count():
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"cards": []})

    client, transport = _client_with_transport(handler)
    try:
        result = await client.fetch_batch_cards(["7701234567"])
    finally:
        await transport.aclose()

    assert attempts == 2
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_429_after_retry_exhaustion_has_attempt_count():
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, headers={"Retry-After": "invalid"})

    client, transport = _client_with_transport(handler, retry_count=2)
    try:
        with pytest.raises(DataNewtonRateLimitError) as error:
            await client.fetch_batch_cards(["7701234567"])
    finally:
        await transport.aclose()

    assert attempts == 3
    assert error.value.attempts == 3
    assert error.value.retryable is True


@pytest.mark.asyncio
async def test_500_retries_and_is_classified_after_exhaustion():
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500, text="raw provider failure")

    client, transport = _client_with_transport(handler)
    try:
        with pytest.raises(DataNewtonServerError) as error:
            await client.fetch_batch_cards(["7701234567"])
    finally:
        await transport.aclose()

    assert attempts == 2
    assert error.value.attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("exception_type", [httpx.ReadTimeout, httpx.ConnectError])
async def test_transport_failures_retry_and_raise_network_error(exception_type):
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise exception_type("provider unavailable", request=request)

    client, transport = _client_with_transport(handler, retry_count=2)
    try:
        with pytest.raises(DataNewtonNetworkError) as error:
            await client.fetch_batch_cards(["7701234567"], request_id="req-network")
    finally:
        await transport.aclose()

    assert attempts == 3
    assert error.value.attempts == 3
    assert error.value.request_id == "req-network"
    assert error.value.retryable is True
    assert "transport-test-secret" not in repr(error.value)


@pytest.mark.asyncio
async def test_transport_accepts_injected_async_client():
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json={})

    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = DataNewtonTransport(
        timeout_seconds=1,
        retry_count=0,
        client=async_client,
        sleep=_no_sleep,
    )
    try:
        result = await transport.request(
            method="POST",
            base_url="https://api.datanewton.ru",
            endpoint="/v1/batchCards",
            api_key="injected-client-secret",
            json_body={"source_inns_or_ogrns": ["7701234567"]},
        )
        await transport.aclose()
        assert async_client.is_closed is False
    finally:
        await async_client.aclose()

    assert attempts == 1
    assert result.attempts == 1

