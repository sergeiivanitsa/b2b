import logging

import httpx
import pytest

from datanewton_provider_test_helpers import API_KEY, build_client
from product_api.providers.datanewton import (
    COUNTERPARTY_ENDPOINT,
    CounterpartyRequest,
    build_datanewton_cache_key,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("identifier", "parameter_name"),
    [("7701234567", "inn"), ("1027700132195", "ogrn")],
)
async def test_counterparty_request_contract_and_filter_normalization(
    identifier,
    parameter_name,
    caplog,
):
    captured = None
    original_filters = (
        " MANAGER_BLOCK ",
        "",
        "ADDRESS_BLOCK",
        "MANAGER_BLOCK",
        "Future_Block",
    )
    payload = {"company": {"raw_nested": {"preserved": True}}}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(200, json=payload)

    caplog.set_level(logging.INFO)
    client, transport = build_client(handler)
    try:
        result = await client.fetch_counterparty(
            identifier,
            filters=original_filters,
            kpp="123456789",
            request_id="counterparty-request",
        )
    finally:
        await transport.aclose()

    assert captured is not None
    assert captured.method == "GET"
    assert captured.url.path == COUNTERPARTY_ENDPOINT
    assert captured.url.params[parameter_name] == identifier
    assert captured.url.params["filters"] == (
        "MANAGER_BLOCK,ADDRESS_BLOCK,Future_Block"
    )
    assert captured.url.params["kpp"] == "123456789"
    assert captured.url.params["key"] == API_KEY
    assert original_filters == (
        " MANAGER_BLOCK ",
        "",
        "ADDRESS_BLOCK",
        "MANAGER_BLOCK",
        "Future_Block",
    )
    assert result.dataset == "counterparty"
    assert result.raw_payload == payload
    assert result.request_parameters == {
        parameter_name: identifier,
        "filters": "MANAGER_BLOCK,ADDRESS_BLOCK,Future_Block",
        "kpp": "123456789",
    }
    assert result.warnings == ["unknown counterparty filters passed: count=1"]
    assert API_KEY not in repr(result)
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert API_KEY not in logs
    assert identifier not in logs


def test_counterparty_filters_change_cache_key_and_key_is_excluded():
    first = CounterpartyRequest(
        identifier="7701234567", filters=["MANAGER_BLOCK", "ADDRESS_BLOCK"]
    )
    second = CounterpartyRequest(
        identifier="7701234567", filters=["MANAGER_BLOCK"]
    )

    def key(request: CounterpartyRequest) -> str:
        return build_datanewton_cache_key(
            dataset="counterparty",
            base_url="https://api.datanewton.ru",
            method="GET",
            endpoint=COUNTERPARTY_ENDPOINT,
            query_params={**request.query_params(), "key": API_KEY},
        )

    assert key(first) != key(second)
    assert API_KEY not in key(first)

