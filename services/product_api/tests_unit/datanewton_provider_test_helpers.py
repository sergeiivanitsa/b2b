from collections.abc import Callable

import httpx

from product_api.providers.datanewton import DataNewtonClient, DataNewtonTransport
from product_api.settings import Settings

API_KEY = "iteration-two-test-secret"


def build_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
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


async def no_sleep(_seconds: float) -> None:
    return None


def build_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    retry_count: int = 0,
    **settings_overrides: object,
) -> tuple[DataNewtonClient, DataNewtonTransport]:
    settings = build_settings(
        DATANEWTON_RETRY_COUNT=retry_count,
        **settings_overrides,
    )
    transport = DataNewtonTransport(
        timeout_seconds=settings.datanewton_timeout_seconds,
        retry_count=settings.datanewton_retry_count,
        transport=httpx.MockTransport(handler),
        sleep=no_sleep,
    )
    return DataNewtonClient(settings, transport=transport), transport

