import logging

import httpx
import pytest

from datanewton_provider_test_helpers import API_KEY, build_client
from product_api.providers.datanewton import (
    FINANCE_ENDPOINT,
    DataNewtonAccessDeniedError,
    FinanceRequest,
    build_datanewton_cache_key,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("identifier", "parameter_name"),
    [
        ("7701234567", "inn"),
        ("500100000001", "inn"),
        ("1027700132195", "ogrn"),
        ("304500000000001", "ogrn"),
    ],
)
async def test_finance_supports_all_identifier_types(identifier, parameter_name):
    captured = None
    payload = {
        "balances": [{"year": 2025, "values": {"raw_code": 100}}],
        "fin_results": {"unmodeled": True},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(200, json=payload)

    client, transport = build_client(handler)
    try:
        result = await client.fetch_finance(identifier, request_id="finance-request")
    finally:
        await transport.aclose()

    assert captured is not None
    assert captured.method == "GET"
    assert captured.url.path == FINANCE_ENDPOINT
    assert captured.url.params[parameter_name] == identifier
    assert captured.url.params["key"] == API_KEY
    assert result.dataset == "finance"
    assert result.raw_payload == payload


def test_finance_cache_key_is_stable_and_excludes_api_key():
    request = FinanceRequest(identifier="77 01-23-45-67")

    def key(secret: str) -> str:
        return build_datanewton_cache_key(
            dataset="finance",
            base_url="https://api.datanewton.ru/",
            method="GET",
            endpoint=FINANCE_ENDPOINT,
            query_params={**request.identifier_query_params(), "key": secret},
        )

    assert key(API_KEY) == key("different-secret")
    assert API_KEY not in key(API_KEY)


@pytest.mark.asyncio
async def test_finance_403_is_non_retryable_safe_access_denied(caplog):
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(403, text=f"unsafe body {API_KEY}")

    caplog.set_level(logging.INFO)
    client, transport = build_client(handler, retry_count=3)
    try:
        with pytest.raises(DataNewtonAccessDeniedError) as error:
            await client.fetch_finance("7701234567", request_id="finance-denied")
    finally:
        await transport.aclose()

    assert attempts == 1
    assert error.value.status_code == 403
    assert error.value.endpoint == FINANCE_ENDPOINT
    assert error.value.dataset == "finance"
    assert error.value.attempts == 1
    assert error.value.request_id == "finance-denied"
    assert error.value.retryable is False
    assert "7701234567" not in str(error.value)
    assert API_KEY not in str(error.value)
    assert API_KEY not in repr(error.value)
    assert "unsafe body" not in str(error.value)
    assert API_KEY not in "\n".join(record.getMessage() for record in caplog.records)

