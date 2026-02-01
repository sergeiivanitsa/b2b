import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

os.environ.pop("OPENAI_API_KEY", None)

_db_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
if _db_url:
    os.environ.setdefault("DATABASE_URL", _db_url)
else:
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
from product_api.main import app

TABLES = [
    "audit_log",
    "messages",
    "ledger",
    "invites",
    "sessions",
    "auth_tokens",
    "conversations",
    "users",
    "companies",
]


@pytest.fixture(scope="session")
def db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url


@pytest.fixture()
async def engine(db_url: str):
    engine = create_async_engine(db_url, future=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("Database not available")
    yield engine
    await engine.dispose()


@pytest.fixture()
async def db_session(engine) -> AsyncSession:
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture()
async def async_client(engine):
    async def _override_get_session():
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        import httpx

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
async def _clean_db(engine):
    async with engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
        )
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
        )
