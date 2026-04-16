import pytest

from product_api.claims.datanewton_client import DataNewtonClient, DataNewtonError
from product_api.settings import Settings


def _build_settings(**overrides) -> Settings:
    base = {
        "DATABASE_URL": "postgresql+asyncpg://app:app@postgres:5432/app",
        "GATEWAY_URL": "http://gateway_api:8001",
        "GATEWAY_SHARED_SECRET": "test-shared-secret",
        "AUTH_TOKEN_SECRET": "test-auth-secret",
        "CLAIM_EDIT_TOKEN_SECRET": "test-claim-edit-secret",
        "CLAIMS_UPLOAD_DIR": "C:/tmp/claims",
        "INVITE_TOKEN_SECRET": "test-invite-secret",
        "SESSION_SECRET": "test-session-secret",
        "EMAIL_FROM": "no-reply@example.com",
    }
    base.update(overrides)
    return Settings.model_validate(base)


@pytest.mark.asyncio
async def test_datanewton_client_returns_none_when_disabled(monkeypatch):
    settings = _build_settings(DATANEWTON_ENABLED=False)
    client = DataNewtonClient(settings)

    called = False

    async def fake_request(_inn: str):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(client, "_request_counterparty", fake_request)

    payload = await client.fetch_party_by_inn("7701234567")
    assert payload is None
    assert called is False


@pytest.mark.asyncio
async def test_datanewton_client_retries_and_recovers(monkeypatch):
    settings = _build_settings(
        DATANEWTON_ENABLED=True,
        DATANEWTON_API_KEY="test-key",
        DATANEWTON_RETRY_COUNT=1,
    )
    client = DataNewtonClient(settings)

    attempts = 0

    async def fake_request_once(_inn: str):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise DataNewtonError("temporary")
        return {
            "kind": "legal_entity",
            "company_name": "ООО «Вектор»",
            "position_raw": "директор",
            "person_name": "Иванов Иван Иванович",
            "address": None,
        }

    monkeypatch.setattr(client, "_request_counterparty_once", fake_request_once)

    payload = await client.fetch_party_by_inn("7701234567")

    assert attempts == 2
    assert payload is not None
    assert payload["company_name"] == "ООО «Вектор»"


@pytest.mark.asyncio
async def test_datanewton_client_uses_cache(monkeypatch):
    settings = _build_settings(
        DATANEWTON_ENABLED=True,
        DATANEWTON_API_KEY="test-key",
        DATANEWTON_CACHE_TTL_SECONDS=60,
    )
    client = DataNewtonClient(settings)
    calls = 0

    async def fake_request_once(_inn: str):
        nonlocal calls
        calls += 1
        return {
            "kind": "legal_entity",
            "company_name": "ООО «Альфа»",
            "position_raw": "директор",
            "person_name": "Петров Петр Петрович",
            "address": None,
        }

    monkeypatch.setattr(client, "_request_counterparty_once", fake_request_once)

    first = await client.fetch_party_by_inn("7701234567")
    second = await client.fetch_party_by_inn("7701234567")

    assert calls == 1
    assert first == second


@pytest.mark.asyncio
async def test_datanewton_client_sends_filters_to_all_candidate_paths(monkeypatch):
    settings = _build_settings(
        DATANEWTON_ENABLED=True,
        DATANEWTON_API_KEY="test-key",
        DATANEWTON_CACHE_TTL_SECONDS=0,
        DATANEWTON_COUNTERPARTY_FILTERS="MANAGER_BLOCK,ADDRESS_BLOCK",
    )
    client = DataNewtonClient(settings)
    requests: list[dict] = []

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self) -> dict:
            return self._payload

    responses = [
        FakeResponse(404, {"detail": "not_found"}),
        FakeResponse(
            200,
            {
                "data": {
                    "company": {
                        "company_names": {"short_name": "Vector LLC"},
                        "managers": [
                            {
                                "fio": "Ivanov Ivan Ivanovich",
                                "position": "general director",
                            }
                        ],
                        "address": {"line_address": "Moscow"},
                    }
                }
            },
        ),
    ]

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, params=None):
            requests.append({"url": url, "params": dict(params or {})})
            return responses.pop(0)

    monkeypatch.setattr(
        "product_api.claims.datanewton_client.httpx.AsyncClient",
        FakeAsyncClient,
    )

    payload = await client.fetch_party_by_inn("7701234567")

    assert payload is not None
    assert payload["company_name"] == "Vector LLC"
    assert payload["person_name"] == "Ivanov Ivan Ivanovich"
    assert payload["position_raw"] == "general director"
    assert len(requests) == 2
    assert requests[0]["url"].endswith("/v1/counterparty")
    assert requests[1]["url"].endswith("/api_ext/v1/counterparty")
    for request in requests:
        assert request["params"]["filters"] == "MANAGER_BLOCK,ADDRESS_BLOCK"
