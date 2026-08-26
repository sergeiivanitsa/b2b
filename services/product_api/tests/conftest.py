import asyncio
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
os.environ.setdefault("CLAIM_EDIT_TOKEN_SECRET", "test-claim-edit-secret")
os.environ.setdefault("CLAIMS_PRICE_RUB", "990")
os.environ.setdefault("DATANEWTON_ENABLED", "false")
os.environ.setdefault("DATANEWTON_BASE_URL", "https://api.datanewton.ru")
os.environ.setdefault("DATANEWTON_API_KEY", "")
os.environ.setdefault("DATANEWTON_TIMEOUT_SECONDS", "10")
os.environ.setdefault("DATANEWTON_RETRY_COUNT", "1")
os.environ.setdefault("DATANEWTON_COUNTERPARTY_FILTERS", "MANAGER_BLOCK,ADDRESS_BLOCK")
os.environ.setdefault("DATANEWTON_CACHE_TTL_SECONDS", "300")
os.environ.setdefault(
    "CLAIMS_UPLOAD_DIR", str((ROOT / ".tmp" / "product_api_claims").as_posix())
)
os.environ.setdefault("CLAIMS_MAX_FILE_SIZE_BYTES", "10485760")
os.environ.setdefault(
    "CLAIMS_ALLOWED_UPLOAD_MIME_TYPES",
    '["application/pdf","application/msword","application/vnd.openxmlformats-officedocument.wordprocessingml.document","application/rtf","text/rtf","image/jpeg","image/png"]',
)
os.environ.setdefault(
    "CLAIMS_ADMIN_EMAILS",
    '["claims-admin@example.com"]',
)
os.environ.setdefault("INVITE_TOKEN_SECRET", "test-invite-secret")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("EMAIL_FROM", "no-reply@example.com")

from product_api import settings as settings_module

settings_module.get_settings.cache_clear()

from product_api.db.session import get_session
from product_api.main import app

TABLES = [
    "company_card_narrative_outbox",
    "company_card_narrative_budget_reservations",
    "company_card_narrative_budget_windows",
    "company_card_narrative_artifacts",
    "company_card_narrative_jobs",
    "company_card_narrative_runtime_control",
    "company_report_publication_journal",
    "company_report_publication_batch_items",
    "company_report_publication_batches",
    "company_report_publications",
    "company_report_publication_control",
    "company_report_presentation_pins",
    "company_report_presentations",
    "company_report_presentation_assignment_journal",
    "company_report_presentation_assignments",
    "company_report_presentation_staged_pointers",
    "company_report_jobs",
    "company_report_provider_requests",
    "company_report_datasets",
    "company_reports",
    "company_report_subjects",
    "claim_events",
    "claim_files",
    "claims",
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

SELF_MANAGED_DATABASE_TESTS = {
    "test_company_report_jobs_upgrade_inspect_and_downgrade",
    "test_company_report_publications_upgrade_inspect_and_downgrade",
    "test_fresh_database_bootstrap_upgrade_current_idempotency_and_round_trip",
    "test_existing_varchar_32_preserves_revision_and_application_state",
    "test_company_card_v2_clean_0015_upgrade_downgrade_reupgrade",
    "test_company_card_v2_corrupt_h1_import_aborts_atomically",
    "test_company_card_narrative_clean_0016_upgrade_downgrade_reupgrade",
    "test_company_card_narrative_populated_legacy_backfill_and_downgrade_refusal",
    "test_company_card_narrative_corrupt_backfill_aborts_atomically",
    "test_company_card_narrative_resolved_pin_refuses_downgrade",
    "test_iteration24_active_h2_guard_is_independent_and_pre_ddl",
    "test_iteration24_terminal_defaults_checks_and_round_trip",
}


@pytest.fixture(scope="session")
def db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url


@pytest.fixture()
async def engine(db_url: str, request):
    if request.node.name in SELF_MANAGED_DATABASE_TESTS:
        yield None
        return
    engine = create_async_engine(db_url, future=True)
    try:
        async def _probe():
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_probe(), timeout=3)
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
async def _clean_db(engine, request):
    if request.node.name in SELF_MANAGED_DATABASE_TESTS:
        yield
        return
    async with engine.begin() as conn:
        existing = (
            await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = current_schema() "
                    "AND tablename = ANY(CAST(:tables AS text[]))"
                ),
                {"tables": TABLES},
            )
        ).scalars().all()
        if existing:
            await conn.execute(
                text(f"TRUNCATE {', '.join(existing)} RESTART IDENTITY CASCADE")
            )
            if "company_report_publication_control" in existing:
                await conn.execute(
                    text(
                        "INSERT INTO company_report_publication_control "
                        "(id, state, policy_version) VALUES "
                        "(1, 'paused', 'publication_sufficiency_v1')"
                    )
                )
            if "company_card_narrative_runtime_control" in existing:
                await conn.execute(
                    text(
                        "INSERT INTO company_card_narrative_runtime_control "
                        "(singleton_id) VALUES (1)"
                    )
                )
    yield
    async with engine.begin() as conn:
        existing = (
            await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = current_schema() "
                    "AND tablename = ANY(CAST(:tables AS text[]))"
                ),
                {"tables": TABLES},
            )
        ).scalars().all()
        if existing:
            await conn.execute(
                text(f"TRUNCATE {', '.join(existing)} RESTART IDENTITY CASCADE")
            )
            if "company_report_publication_control" in existing:
                await conn.execute(
                    text(
                        "INSERT INTO company_report_publication_control "
                        "(id, state, policy_version) VALUES "
                        "(1, 'paused', 'publication_sufficiency_v1')"
                    )
                )
            if "company_card_narrative_runtime_control" in existing:
                await conn.execute(
                    text(
                        "INSERT INTO company_card_narrative_runtime_control "
                        "(singleton_id) VALUES (1)"
                    )
                )
