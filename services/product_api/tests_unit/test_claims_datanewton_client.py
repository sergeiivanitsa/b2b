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
