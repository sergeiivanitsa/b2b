import httpx
import pytest

from datanewton_provider_test_helpers import build_client
from product_api.providers.datanewton import (
    BANKRUPTCY_ENDPOINT,
    BankruptcyRequest,
    DataNewtonValidationError,
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
async def test_bankruptcy_supports_all_identifier_types(identifier, parameter_name):
    captured = None
    payload = {"messages": [{"type_name": "RawType", "type_description": "Raw"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(200, json=payload)

    client, transport = build_client(handler)
    try:
        result = await client.fetch_bankruptcy(identifier, request_id="bankruptcy")
    finally:
        await transport.aclose()

    assert captured is not None
    assert captured.method == "GET"
    assert captured.url.path == BANKRUPTCY_ENDPOINT
    assert captured.url.params[parameter_name] == identifier
    assert captured.url.params["offset"] == "0"
    assert captured.url.params["limit"] == "100"
    assert captured.headers["X-Request-ID"] == "bankruptcy"
    assert result.raw_payload == payload
    assert result.request_parameters == {
        parameter_name: identifier,
        "offset": 0,
        "limit": 100,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [{"limit": 0}, {"limit": 1001}, {"offset": -1}],
)
async def test_bankruptcy_rejects_invalid_pagination_before_http(overrides):
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    client, transport = build_client(handler)
    try:
        with pytest.raises(DataNewtonValidationError):
            await client.fetch_bankruptcy("7701234567", **overrides)
    finally:
        await transport.aclose()

    assert called is False


def test_bankruptcy_cache_key_changes_with_pagination():
    first = BankruptcyRequest(identifier="7701234567", offset=0, limit=100)
    second = BankruptcyRequest(identifier="7701234567", offset=100, limit=1000)

    def key(request: BankruptcyRequest) -> str:
        return build_datanewton_cache_key(
            dataset="bankruptcy",
            base_url="https://api.datanewton.ru",
            method="GET",
            endpoint=BANKRUPTCY_ENDPOINT,
            query_params=request.query_params(),
        )

    assert key(first) != key(second)

