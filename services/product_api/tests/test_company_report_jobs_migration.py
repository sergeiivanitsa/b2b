from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from product_api.company_reports.persistence.models import CompanyReportJob

_DATABASE_PREFIX = "company_report_jobs_test_"
_EXISTING_TABLES = {
    "company_report_subjects",
    "company_reports",
    "company_report_datasets",
    "company_report_provider_requests",
}


def test_company_report_jobs_upgrade_inspect_and_downgrade(monkeypatch):
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    parsed_admin = _validated_test_admin_url(admin_url)
    database_name = f"{_DATABASE_PREFIX}{uuid4().hex}"
    target_url = parsed_admin.set(database=database_name)
    admin_connection_url = parsed_admin.render_as_string(hide_password=False)
    target_connection_url = target_url.render_as_string(hide_password=False)
    asyncio.run(_create_database(admin_connection_url, database_name))
    try:
        monkeypatch.setenv("DATABASE_URL", target_connection_url)
        config = _alembic_config(target_connection_url)
        command.upgrade(config, "0013_company_report_jobs")

        upgraded = asyncio.run(_inspect_database(target_connection_url))
        assert _EXISTING_TABLES | {"company_report_jobs"} <= upgraded["tables"]
        assert upgraded["columns"] == {
            "id": False,
            "report_id": False,
            "subject_id": False,
            "state": False,
            "worker_token": True,
            "attempt_count": False,
            "claimed_at": True,
            "heartbeat_at": True,
            "lease_expires_at": True,
            "finished_at": True,
            "safe_failure_code": True,
            "created_at": False,
            "updated_at": False,
        }
        assert upgraded["foreign_keys"] == {
            ("report_id", "company_reports", "CASCADE"),
            ("subject_id", "company_report_subjects", "CASCADE"),
        }
        assert "uq_company_report_jobs_report_id" in upgraded["unique_constraints"]
        assert {
            "company_report_job_state",
            "company_report_job_attempt_count",
            "company_report_job_state_shape",
        } <= {
            name.removeprefix("ck_company_report_jobs_")
            for name in upgraded["check_constraints"]
        }
        assert {
            "uq_company_report_jobs_active_subject",
            "ix_company_report_jobs_queued_claim",
            "ix_company_report_jobs_running_lease",
        } <= upgraded["indexes"]
        assert set(upgraded["columns"]) == {
            column.name for column in CompanyReportJob.__table__.columns
        }

        command.downgrade(config, "0012_company_report_persistence")
        downgraded = asyncio.run(_inspect_database(target_connection_url))
        assert "company_report_jobs" not in downgraded["tables"]
        assert _EXISTING_TABLES <= downgraded["tables"]
        assert downgraded["alembic_version"] == "0012_company_report_persistence"
    finally:
        asyncio.run(_drop_database(admin_connection_url, database_name))


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
    host = (parsed.host or "").lower()
    database = (parsed.database or "").lower()
    safe_host = host in {"localhost", "127.0.0.1", "::1", "postgres"} or any(
        marker in host for marker in ("test", "ci")
    )
    safe_database = database == "postgres" or "test" in database
    if not safe_host or not safe_database:
        raise ValueError(
            "TEST_POSTGRES_ADMIN_URL is not an explicitly safe test administrator target"
        )
    return parsed


def _alembic_config(target_url: str) -> Config:
    product_root = Path(__file__).parents[1]
    config = Config(str(product_root / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(product_root / "alembic"),
    )
    config.set_main_option("sqlalchemy.url", target_url.replace("%", "%%"))
    return config


async def _create_database(admin_url: str, database_name: str) -> None:
    _validate_generated_database_name(database_name)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
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


async def _inspect_database(url: str) -> dict[str, object]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            metadata = await connection.run_sync(_sync_inspect_database)
            version = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            metadata["alembic_version"] = version
            return metadata
    finally:
        await engine.dispose()


def _sync_inspect_database(connection) -> dict[str, object]:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if "company_report_jobs" not in tables:
        return {
            "tables": tables,
            "columns": {},
            "foreign_keys": set(),
            "unique_constraints": set(),
            "check_constraints": set(),
            "indexes": set(),
        }
    columns = {
        column["name"]: column["nullable"]
        for column in inspector.get_columns("company_report_jobs")
    }
    foreign_keys = {
        (
            constraint["constrained_columns"][0],
            constraint["referred_table"],
            str(constraint.get("options", {}).get("ondelete", "")).upper(),
        )
        for constraint in inspector.get_foreign_keys("company_report_jobs")
    }
    return {
        "tables": tables,
        "columns": columns,
        "foreign_keys": foreign_keys,
        "unique_constraints": {
            constraint["name"]
            for constraint in inspector.get_unique_constraints(
                "company_report_jobs"
            )
        },
        "check_constraints": {
            constraint["name"]
            for constraint in inspector.get_check_constraints(
                "company_report_jobs"
            )
        },
        "indexes": {
            index["name"]
            for index in inspector.get_indexes("company_report_jobs")
        },
    }


def _validate_generated_database_name(value: str) -> None:
    if not value.startswith(_DATABASE_PREFIX):
        raise ValueError("refusing to mutate a database not created by this test")
    suffix = value.removeprefix(_DATABASE_PREFIX)
    if len(suffix) != 32 or any(character not in "0123456789abcdef" for character in suffix):
        raise ValueError("generated test database name is invalid")
