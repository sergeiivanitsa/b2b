import httpx
import pytest

from datanewton_provider_test_helpers import build_client
from product_api.providers.datanewton import (
    ARBITRATION_CASES_ENDPOINT,
    ArbitrationCasesRequest,
    DataNewtonValidationError,
    build_datanewton_cache_key,
)


@pytest.mark.asyncio
async def test_arbitration_defaults_and_optional_filters():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"cases": [], "total": 0})

    client, transport = build_client(handler)
    try:
        default_result = await client.fetch_arbitration_cases(
            "7701234567", request_id="arb-default"
        )
        filtered_result = await client.fetch_arbitration_cases(
            "1027700132195",
            offset=50,
            limit=1000,
            company_role="RESPONDENT",
            status=0,
            start_date="2024-01-01",
            end_date="2025-12-31",
            updated_at_from="2025-01-15",
            need_document=False,
            request_id="arb-filtered",
        )
    finally:
        await transport.aclose()

    assert len(captured) == 2
    first, second = captured
    assert first.method == "GET"
    assert first.url.path == ARBITRATION_CASES_ENDPOINT
    assert first.headers["X-Request-ID"] == "arb-default"
    assert dict(first.url.params).keys() == {"key", "inn", "offset", "limit"}
    assert first.url.params["offset"] == "0"
    assert first.url.params["limit"] == "100"
    assert default_result.request_parameters == {
        "inn": "7701234567",
        "offset": 0,
        "limit": 100,
    }

    assert second.url.params["ogrn"] == "1027700132195"
    assert second.url.params["offset"] == "50"
    assert second.url.params["limit"] == "1000"
    assert second.url.params["company_role"] == "RESPONDENT"
    assert second.url.params["status"] == "0"
    assert second.url.params["start_date"] == "2024-01-01"
    assert second.url.params["end_date"] == "2025-12-31"
    assert second.url.params["updated_at_from"] == "2025-01-15"
    assert second.url.params["need_document"] == "false"
    assert second.headers["X-Request-ID"] == "arb-filtered"
    assert filtered_result.dataset == "arbitration_cases"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"limit": 0},
        {"limit": 1001},
        {"offset": -1},
        {"start_date": "2025-02-30"},
        {"end_date": "2025/01/01"},
        {"updated_at_from": "01-01-2025"},
    ],
)
async def test_arbitration_rejects_invalid_pagination_and_dates_before_http(overrides):
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    client, transport = build_client(handler)
    try:
        with pytest.raises(DataNewtonValidationError) as error:
            await client.fetch_arbitration_cases("7701234567", **overrides)
    finally:
        await transport.aclose()

    assert error.value.dataset == "arbitration_cases"
    assert error.value.attempts == 0
    assert called is False


def test_arbitration_cache_key_includes_pagination_and_filters():
    base = ArbitrationCasesRequest(identifier="7701234567")
    other_page = ArbitrationCasesRequest(identifier="7701234567", offset=100, limit=50)
    filtered = ArbitrationCasesRequest(
        identifier="7701234567", company_role="PLAINTIFF", status=1
    )

    def key(request: ArbitrationCasesRequest) -> str:
        return build_datanewton_cache_key(
            dataset="arbitration_cases",
            base_url="https://api.datanewton.ru",
            method="GET",
            endpoint=ARBITRATION_CASES_ENDPOINT,
            query_params=request.query_params(),
        )

    assert key(base) != key(other_page)
    assert key(base) != key(filtered)

