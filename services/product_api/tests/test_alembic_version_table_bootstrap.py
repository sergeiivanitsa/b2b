from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

_PRODUCT_ROOT = Path(__file__).parents[1]
_DATABASE_PREFIX = "alembic_bootstrap_test_"
_LEGACY_REVISION = "0006_chat_api_v1"
_PERSISTENCE_REVISION = "0012_company_report_persistence"
_VERSION_LENGTH_MARGIN = 16
_VERSION_LENGTH_GRANULARITY = 16
_MIN_VERSION_LENGTH = 64


def test_fresh_database_bootstrap_upgrade_current_idempotency_and_round_trip():
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")

    admin = _validated_test_admin_url(admin_url)
    database_name = f"{_DATABASE_PREFIX}{uuid4().hex}"
    target = admin.set(database=database_name)
    admin_connection_url = admin.render_as_string(hide_password=False)
    target_connection_url = target.render_as_string(hide_password=False)
    asyncio.run(_create_database(admin_connection_url, database_name))
    try:
        initial = asyncio.run(_inspect_database(target_connection_url))
        assert not initial["version_table_exists"]

        _run_alembic_cli(target_connection_url, "upgrade", "head")
        current = _run_alembic_cli(target_connection_url, "current")

        head = _head_revision()
        assert head in current.stdout + current.stderr
        upgraded = asyncio.run(_inspect_database(target_connection_url))
        assert upgraded["version_rows"] == (head,)
        assert upgraded["version_length"] == _required_version_length()
        assert upgraded["version_length"] >= _longest_revision_length() + 16

        _run_alembic_cli(target_connection_url, "upgrade", "head")
        repeated = asyncio.run(_inspect_database(target_connection_url))
        assert repeated == upgraded

        _run_alembic_cli(
            target_connection_url,
            "downgrade",
            _PERSISTENCE_REVISION,
        )
        downgraded = asyncio.run(_inspect_database(target_connection_url))
        assert downgraded["version_rows"] == (_PERSISTENCE_REVISION,)
        assert "company_report_subjects" in downgraded["tables"]
        assert "company_report_jobs" not in downgraded["tables"]
        assert "company_report_publications" not in downgraded["tables"]

        _run_alembic_cli(target_connection_url, "upgrade", "head")
        restored = asyncio.run(_inspect_database(target_connection_url))
        assert restored["version_rows"] == (head,)
        assert restored["version_length"] == _required_version_length()
        assert restored["schema_fingerprint"] == upgraded["schema_fingerprint"]
    finally:
        asyncio.run(_drop_database(admin_connection_url, database_name))


def test_existing_varchar_32_preserves_revision_and_application_state():
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")

    admin = _validated_test_admin_url(admin_url)
    database_name = f"{_DATABASE_PREFIX}{uuid4().hex}"
    target = admin.set(database=database_name)
    admin_connection_url = admin.render_as_string(hide_password=False)
    target_connection_url = target.render_as_string(hide_password=False)
    asyncio.run(_create_database(admin_connection_url, database_name))
    try:
        _run_alembic_cli(
            target_connection_url,
            "upgrade",
            _LEGACY_REVISION,
        )
        asyncio.run(_prepare_legacy_version_table(target_connection_url))

        legacy = asyncio.run(_inspect_database(target_connection_url))
        assert legacy["version_rows"] == (_LEGACY_REVISION,)
        assert legacy["version_length"] == 32
        legacy_application_schema = legacy["application_schema_fingerprint"]

        current = _run_alembic_cli(target_connection_url, "current")
        assert _LEGACY_REVISION in current.stdout + current.stderr

        bootstrapped = asyncio.run(_inspect_database(target_connection_url))
        assert bootstrapped["version_rows"] == (_LEGACY_REVISION,)
        assert bootstrapped["version_row_count"] == 1
        assert bootstrapped["version_length"] == _required_version_length()
        assert (
            bootstrapped["application_schema_fingerprint"]
            == legacy_application_schema
        )
        assert bootstrapped["sentinel_rows"] == ((1, "preserve-me"),)

        _run_alembic_cli(target_connection_url, "upgrade", "head")
        first_head = asyncio.run(_inspect_database(target_connection_url))
        head = _head_revision()
        assert first_head["version_rows"] == (head,)
        assert first_head["sentinel_rows"] == ((1, "preserve-me"),)

        current_head = _run_alembic_cli(target_connection_url, "current")
        assert head in current_head.stdout + current_head.stderr
        _run_alembic_cli(target_connection_url, "upgrade", "head")

        repeated_head = asyncio.run(_inspect_database(target_connection_url))
        assert repeated_head == first_head
    finally:
        asyncio.run(_drop_database(admin_connection_url, database_name))


def _alembic_config() -> Config:
    config = Config(str(_PRODUCT_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(_PRODUCT_ROOT / "alembic"),
    )
    return config


def _head_revision() -> str:
    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    assert head is not None
    return head


def _longest_revision_length() -> int:
    revisions = ScriptDirectory.from_config(_alembic_config()).walk_revisions()
    return max(len(revision.revision) for revision in revisions)


def _required_version_length() -> int:
    padded = _longest_revision_length() + _VERSION_LENGTH_MARGIN
    rounded = (
        padded + _VERSION_LENGTH_GRANULARITY - 1
    ) // _VERSION_LENGTH_GRANULARITY * _VERSION_LENGTH_GRANULARITY
    return max(_MIN_VERSION_LENGTH, rounded)


def _run_alembic_cli(
    target_url: str,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = target_url
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            *arguments,
        ],
        cwd=_PRODUCT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, (
        f"Alembic CLI failed: {' '.join(arguments)}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    return result


def _validated_test_admin_url(value: str):
    parsed = make_url(value)
    if parsed.get_backend_name() != "postgresql":
        raise ValueError("TEST_POSTGRES_ADMIN_URL must use PostgreSQL")
    if parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+asyncpg")
    elif parsed.drivername != "postgresql+asyncpg":
        raise ValueError(
            "TEST_POSTGRES_ADMIN_URL must use the asyncpg PostgreSQL driver"
        )
    if (
        (parsed.host or "").lower()
        not in {"localhost", "127.0.0.1", "::1", "postgres"}
        or (parsed.database or "").lower() != "postgres"
    ):
        raise ValueError(
            "TEST_POSTGRES_ADMIN_URL must name disposable local PostgreSQL"
        )
    return parsed


async def _create_database(admin_url: str, database_name: str) -> None:
    _validate_generated_database_name(database_name)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(f'CREATE DATABASE "{database_name}"')
            )
    finally:
        await engine.dispose()


async def _prepare_legacy_version_table(target_url: str) -> None:
    engine = create_async_engine(target_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "ALTER TABLE alembic_version "
                    "ALTER COLUMN version_num TYPE VARCHAR(32)"
                )
            )
            await connection.execute(
                text(
                    "CREATE TABLE bootstrap_sentinel ("
                    "id INTEGER PRIMARY KEY, "
                    "payload TEXT NOT NULL"
                    ")"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO bootstrap_sentinel (id, payload) "
                    "VALUES (1, 'preserve-me')"
                )
            )
    finally:
        await engine.dispose()


async def _inspect_database(url: str) -> dict[str, object]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            version_table_exists = bool(
                await connection.scalar(
                    text(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = current_schema() "
                        "AND table_name = 'alembic_version'"
                        ")"
                    )
                )
            )
            tables = tuple(
                (
                    await connection.execute(
                        text(
                            "SELECT table_name "
                            "FROM information_schema.tables "
                            "WHERE table_schema = current_schema() "
                            "AND table_type = 'BASE TABLE' "
                            "ORDER BY table_name"
                        )
                    )
                ).scalars()
            )
            schema_fingerprint = tuple(
                (
                    await connection.execute(
                        text(
                            "SELECT table_name, column_name, data_type, "
                            "character_maximum_length, is_nullable, "
                            "column_default "
                            "FROM information_schema.columns "
                            "WHERE table_schema = current_schema() "
                            "ORDER BY table_name, ordinal_position"
                        )
                    )
                ).tuples()
            )
            application_schema_fingerprint = tuple(
                column
                for column in schema_fingerprint
                if column[0] != "alembic_version"
            )

            version_rows: tuple[str, ...] = ()
            version_length = None
            if version_table_exists:
                version_rows = tuple(
                    (
                        await connection.execute(
                            text(
                                "SELECT version_num "
                                "FROM alembic_version "
                                "ORDER BY version_num"
                            )
                        )
                    ).scalars()
                )
                version_length = await connection.scalar(
                    text(
                        "SELECT character_maximum_length "
                        "FROM information_schema.columns "
                        "WHERE table_schema = current_schema() "
                        "AND table_name = 'alembic_version' "
                        "AND column_name = 'version_num'"
                    )
                )

            sentinel_rows: tuple[tuple[int, str], ...] = ()
            if "bootstrap_sentinel" in tables:
                sentinel_rows = tuple(
                    (
                        await connection.execute(
                            text(
                                "SELECT id, payload "
                                "FROM bootstrap_sentinel "
                                "ORDER BY id"
                            )
                        )
                    ).tuples()
                )

            return {
                "version_table_exists": version_table_exists,
                "version_rows": version_rows,
                "version_row_count": len(version_rows),
                "version_length": version_length,
                "tables": tables,
                "schema_fingerprint": schema_fingerprint,
                "application_schema_fingerprint": (
                    application_schema_fingerprint
                ),
                "sentinel_rows": sentinel_rows,
            }
    finally:
        await engine.dispose()


async def _drop_database(admin_url: str, database_name: str) -> None:
    _validate_generated_database_name(database_name)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name "
                    "AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            await connection.execute(
                text(f'DROP DATABASE IF EXISTS "{database_name}"')
            )
    finally:
        await engine.dispose()


def _validate_generated_database_name(value: str) -> None:
    if not value.startswith(_DATABASE_PREFIX):
        raise ValueError("refusing to mutate a database not created by this test")
    suffix = value.removeprefix(_DATABASE_PREFIX)
    if len(suffix) != 32 or any(
        character not in "0123456789abcdef" for character in suffix
    ):
        raise ValueError("generated test database name is invalid")
