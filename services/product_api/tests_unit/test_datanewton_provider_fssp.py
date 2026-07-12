import json

import httpx
import pytest

from datanewton_provider_test_helpers import API_KEY, build_client
from product_api.providers.datanewton import (
    FSSP_ENDPOINT,
    DataNewtonUnsupportedIdentifierError,
    DataNewtonValidationError,
    FsspRequest,
    build_datanewton_cache_key,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("identifier", "identifier_field"),
    [("7701234567", "inn"), ("1027700132195", "ogrn")],
)
async def test_fssp_body_matches_openapi_schema(identifier, identifier_field):
    captured = None
    original_filter = {"company_role": "Должник", "amount_due_min": 1000.0}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(200, json={"items": [], "total": 0})

    client, transport = build_client(handler)
    try:
        result = await client.fetch_fssp(
            identifier,
            limit=0,
            offset=5,
            sort="date",
            order="desc",
            filter=original_filter,
            request_id="fssp-request",
        )
    finally:
        await transport.aclose()

    assert captured is not None
    assert captured.method == "POST"
    assert captured.url.path == FSSP_ENDPOINT
    assert dict(captured.url.params) == {"key": API_KEY}
    assert captured.headers["X-Request-ID"] == "fssp-request"
    body = json.loads(captured.content)
    assert body == {
        identifier_field: identifier,
        "limit": 0,
        "offset": 5,
        "sort": "date",
        "order": "desc",
        "filter": original_filter,
    }
    assert ("ogrn" if identifier_field == "inn" else "inn") not in body
    assert original_filter == {"company_role": "Должник", "amount_due_min": 1000.0}
    assert result.request_body == body
    assert result.raw_payload == {"items": [], "total": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("identifier", "identifier_type"),
    [
        ("500100000001", "individual_entrepreneur_inn"),
        ("304500000000001", "ogrnip"),
    ],
)
async def test_fssp_rejects_unconfirmed_ip_identifiers_before_http(
    identifier,
    identifier_type,
):
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    client, transport = build_client(handler)
    try:
        with pytest.raises(DataNewtonUnsupportedIdentifierError) as error:
            await client.fetch_fssp(identifier, request_id="unsupported")
    finally:
        await transport.aclose()

    assert called is False
    assert error.value.dataset == "fssp"
    assert error.value.endpoint == FSSP_ENDPOINT
    assert error.value.identifier_type == identifier_type
    assert error.value.retryable is False
    assert error.value.attempts == 0
    assert identifier not in str(error.value)
    assert identifier not in repr(error.value)
    assert API_KEY not in repr(error.value)


@pytest.mark.asyncio
async def test_fssp_rejects_negative_offset_before_http():
    client, transport = build_client(lambda _request: httpx.Response(200, json={}))
    try:
        with pytest.raises(DataNewtonValidationError):
            await client.fetch_fssp("7701234567", offset=-1)
    finally:
        await transport.aclose()


def test_fssp_cache_key_changes_with_filter_without_mutating_filter():
    first_filter = {"status": "OPEN", "amount_due_min": 1000}
    second_filter = {"status": "CLOSE", "amount_due_min": 1000}
    first_request = FsspRequest(identifier="7701234567", filter=first_filter)
    second_request = FsspRequest(identifier="7701234567", filter=second_filter)

    def key(request: FsspRequest) -> str:
        return build_datanewton_cache_key(
            dataset="fssp",
            base_url="https://api.datanewton.ru",
            method="POST",
            endpoint=FSSP_ENDPOINT,
            body=request.body(),
        )

    assert key(first_request) != key(second_request)
    assert first_filter == {"status": "OPEN", "amount_due_min": 1000}

