import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "services" / "product_api" / "src"
for path in (str(SRC), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.append(path)

os.environ.pop("OPENAI_API_KEY", None)
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://app:app@postgres:5432/app")
os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("GATEWAY_URL", "http://gateway_api:8001")
os.environ.setdefault("GATEWAY_SHARED_SECRET", "test-shared-secret")
os.environ.setdefault("AUTH_TOKEN_SECRET", "test-auth-secret")
os.environ.setdefault("INVITE_TOKEN_SECRET", "test-invite-secret")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("EMAIL_FROM", "no-reply@example.com")

from product_api import settings as settings_module

settings_module.get_settings.cache_clear()

from product_api.db.session import get_session
from product_api.main import app as fastapi_app


@pytest.fixture()
def mock_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture()
def make_result():
    class DummyResult:
        def __init__(self, first_value):
            self._first_value = first_value

        def first(self):
            return self._first_value

    return DummyResult


@pytest.fixture()
async def async_client(mock_session):
    async def _override_get_session():
        yield mock_session

    fastapi_app.dependency_overrides[get_session] = _override_get_session
    try:
        import httpx

        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        fastapi_app.dependency_overrides.clear()
