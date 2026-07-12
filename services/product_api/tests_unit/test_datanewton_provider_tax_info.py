import logging

import httpx
import pytest

from datanewton_provider_test_helpers import API_KEY, build_client
from product_api.providers.datanewton import (
    TAX_INFO_ENDPOINT,
    TaxInfoRequest,
    build_datanewton_cache_key,
    calculate_response_hash,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("identifier", "parameter_name", "identifier_type"),
    [
        ("7701234567", "inn", "legal_entity_inn"),
        ("500100000001", "inn", "individual_entrepreneur_inn"),
        ("1027700132195", "ogrn", "ogrn"),
        ("304500000000001", "ogrn", "ogrnip"),
    ],
)
async def test_tax_info_supports_all_identifier_types(
    identifier,
    parameter_name,
    identifier_type,
    caplog,
):
    captured = None
    payload = {"paid_taxes": [{"year": 2025}], "unmodeled": {"kept": True}}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(
            200,
            json=payload,
            headers={"X-RateLimit-Remaining": "17"},
        )

    caplog.set_level(logging.INFO)
    client, transport = build_client(handler)
    try:
        result = await client.fetch_tax_info(identifier, request_id="tax-request")
    finally:
        await transport.aclose()

    assert captured is not None
    assert captured.method == "GET"
    assert captured.url.path == TAX_INFO_ENDPOINT
    assert captured.url.params["key"] == API_KEY
    assert captured.url.params[parameter_name] == identifier
    assert len(captured.url.params) == 2
    assert captured.headers["X-Request-ID"] == "tax-request"
    assert result.dataset == "tax_info"
    assert result.endpoint == TAX_INFO_ENDPOINT
    assert result.requested_identifier == identifier
    assert result.request_parameters == {parameter_name: identifier}
    assert result.raw_payload == payload
    assert result.response_hash == calculate_response_hash(payload)
    assert result.attempts == 1
    assert result.duration_ms >= 0
    assert result.provider_limit_metadata == {
        "headers": {"x-ratelimit-remaining": "17"}
    }
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert f"identifier_type={identifier_type}" in logs
    assert identifier not in logs
    assert API_KEY not in logs
    assert API_KEY not in repr(result)


def test_tax_info_cache_key_excludes_api_key():
    request = TaxInfoRequest(identifier="77 01-23-45-67")
    cache_key = build_datanewton_cache_key(
        dataset="tax_info",
        base_url="https://api.datanewton.ru/",
        method="GET",
        endpoint=TAX_INFO_ENDPOINT,
        query_params={**request.identifier_query_params(), "key": API_KEY},
    )

    assert cache_key.startswith("datanewton:tax_info:v1:")
    assert API_KEY not in cache_key

