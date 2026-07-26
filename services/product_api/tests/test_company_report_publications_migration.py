from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, UniqueConstraint, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine

from product_api.company_reports.persistence.models import (
    CompanyReportPublication,
    CompanyReportPublicationBatch,
    CompanyReportPublicationBatchItem,
    CompanyReportPublicationControl,
    CompanyReportPublicationJournal,
)

_DATABASE_PREFIX = "seo_pub_test_"
_PUBLICATION_TABLES = {
    "company_report_publication_control",
    "company_report_publications",
    "company_report_publication_batches",
    "company_report_publication_batch_items",
    "company_report_publication_journal",
}

# This is the public persistence contract, intentionally independent from the
# ORM and migration implementation.  PostgreSQL Inspector values are checked
# against it after a real 0013 -> 0014 upgrade.
_EXPECTED_COLUMNS = {
    "company_report_publication_control": {
        "id": ("INTEGER", False, None), "state": ("VARCHAR(16)", False, None),
        "policy_version": ("VARCHAR(64)", False, None),
        "updated_at": ("TIMESTAMP WITH TIME ZONE", False, "now"),
    },
    "company_report_publications": {
        "id": ("UUID", False, None), "subject_id": ("UUID", False, None),
        "report_id": ("UUID", False, None), "status": ("VARCHAR(16)", False, None),
        "canonical_slug": ("VARCHAR(200)", False, None), "canonical_path": ("VARCHAR(240)", False, None),
        "snapshot_hash": ("VARCHAR(64)", True, None), "policy_version": ("VARCHAR(64)", False, None),
        "batch_generation": ("BIGINT", False, None), "indexable": ("BOOLEAN", False, "false"),
        "sufficiency_status": ("VARCHAR(64)", False, None), "published_lastmod": ("TIMESTAMP WITH TIME ZONE", True, None),
        "published_at": ("TIMESTAMP WITH TIME ZONE", False, "now"), "disabled_at": ("TIMESTAMP WITH TIME ZONE", True, None),
        "audited_at": ("TIMESTAMP WITH TIME ZONE", True, None),
    },
    "company_report_publication_batches": {
        "id": ("UUID", False, None), "generation": ("BIGINT", False, "identity"), "state": ("VARCHAR(16)", False, None),
        "requested_limit": ("INTEGER", False, None), "candidate_count": ("INTEGER", False, None),
        "next_ordinal": ("INTEGER", False, "0"), "claimed_ordinal": ("INTEGER", True, None),
        "policy_version": ("VARCHAR(64)", False, None), "safe_failure_code": ("VARCHAR(64)", True, None),
        "created_at": ("TIMESTAMP WITH TIME ZONE", False, "now"), "updated_at": ("TIMESTAMP WITH TIME ZONE", False, "now"),
        "completed_at": ("TIMESTAMP WITH TIME ZONE", True, None),
    },
    "company_report_publication_batch_items": {
        "id": ("UUID", False, None), "batch_id": ("UUID", False, None), "ordinal": ("INTEGER", False, None),
        "subject_id": ("UUID", False, None), "report_id": ("UUID", False, None), "snapshot_hash": ("VARCHAR(64)", False, None),
        "policy_version": ("VARCHAR(64)", False, None), "state": ("VARCHAR(16)", False, None),
        "claim_token": ("UUID", True, None), "claimed_at": ("TIMESTAMP WITH TIME ZONE", True, None),
        "finished_at": ("TIMESTAMP WITH TIME ZONE", True, None), "reason_code": ("VARCHAR(64)", True, None),
    },
    "company_report_publication_journal": {
        "id": ("UUID", False, None), "batch_id": ("UUID", False, None), "ordinal": ("INTEGER", False, None),
        "subject_id": ("UUID", False, None), "report_id": ("UUID", False, None), "snapshot_hash": ("VARCHAR(64)", False, None),
        "policy_version": ("VARCHAR(64)", False, None), "action": ("VARCHAR(16)", False, None),
        "reason_code": ("VARCHAR(64)", False, None), "created_at": ("TIMESTAMP WITH TIME ZONE", False, "now"),
    },
}
_EXPECTED_FKS = {
    "company_report_publications": {("subject_id", "company_report_subjects", None), ("report_id", "company_reports", None), ("batch_generation", "company_report_publication_batches", None)},
    "company_report_publication_batch_items": {("batch_id", "company_report_publication_batches", None), ("subject_id", "company_report_subjects", None), ("report_id", "company_reports", None)},
    "company_report_publication_journal": {("batch_id", "company_report_publication_batches", None), ("subject_id", "company_report_subjects", None), ("report_id", "company_reports", None)},
}
_EXPECTED_UNIQUES = {
    "company_report_publications": {"uq_company_report_publications_subject_id", "uq_company_report_publications_report_id", "uq_company_report_publications_canonical_path"},
    "company_report_publication_batches": {"uq_company_report_publication_batches_generation"},
    "company_report_publication_batch_items": {"uq_company_report_publication_batch_item_ordinal"},
    "company_report_publication_journal": {"uq_company_report_publication_journal_action", "uq_company_report_publication_journal_terminal"},
}
_EXPECTED_INDEXES = {
    "company_report_publications": {"ix_company_report_publications_sitemap"},
    "company_report_publication_batch_items": {"ix_company_report_publication_batch_item_claim"},
}
_EXPECTED_CHECKS = {
    "company_report_publication_control": {"id = 1", "state"},
    "company_report_publications": {"status", "canonical_path", "snapshot_hash", "indexable", "batch_generation > 0"},
    "company_report_publication_batches": {"state", "requested_limit", "candidate_count", "next_ordinal", "claimed_ordinal"},
    "company_report_publication_batch_items": {"state", "claim_token", "reason_code"},
    "company_report_publication_journal": {"action", "reason_code"},
}
_ORM_TABLES = {
    "company_report_publication_control": CompanyReportPublicationControl,
    "company_report_publications": CompanyReportPublication,
    "company_report_publication_batches": CompanyReportPublicationBatch,
    "company_report_publication_batch_items": CompanyReportPublicationBatchItem,
    "company_report_publication_journal": CompanyReportPublicationJournal,
}


def test_company_report_publications_upgrade_inspect_and_downgrade(monkeypatch):
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    admin = _validated_test_admin_url(admin_url)
    database_name = f"{_DATABASE_PREFIX}{uuid4().hex}"
    target = admin.set(database=database_name)
    admin_url, target_url = admin.render_as_string(hide_password=False), target.render_as_string(hide_password=False)
    asyncio.run(_create_database(admin_url, database_name))
    try:
        monkeypatch.setenv("DATABASE_URL", target_url)
        config = _alembic_config(target_url)
        command.upgrade(config, "0013_company_report_jobs")
        command.upgrade(config, "0014_company_report_publications")
        asyncio.run(_assert_live_schema_contract(target_url))
        asyncio.run(_exercise_live_constraints(target_url))
        command.downgrade(config, "0013_company_report_jobs")
        assert asyncio.run(_version_and_tables(target_url)) == ("0013_company_report_jobs", set())
        command.upgrade(config, "0014_company_report_publications")
        asyncio.run(_assert_live_schema_contract(target_url))
    finally:
        asyncio.run(_drop_database(admin_url, database_name))


async def _assert_live_schema_contract(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            actual = await connection.run_sync(_inspect_contract)
    finally:
        await engine.dispose()
    assert set(actual) == _PUBLICATION_TABLES
    for table, expected_columns in _EXPECTED_COLUMNS.items():
        assert actual[table]["columns"] == expected_columns
        assert actual[table]["pk"] == {"id"}
        assert actual[table]["fks"] == _EXPECTED_FKS.get(table, set())
        assert actual[table]["uniques"] == _EXPECTED_UNIQUES.get(table, set())
        assert actual[table]["indexes"] == _EXPECTED_INDEXES.get(table, set())
        check_sql = {" ".join(value.lower().split()) for value in actual[table]["checks"].values()}
        assert len(check_sql) == len(_EXPECTED_CHECKS[table])
        for required in _EXPECTED_CHECKS[table]:
            assert any(required in value for value in check_sql)
        orm = _ORM_TABLES[table].__table__
        assert {column.name for column in orm.columns} == set(expected_columns)
        assert {column.name: _orm_type(column) for column in orm.columns} == {name: value[0] for name, value in expected_columns.items()}
        assert {column.name: column.nullable for column in orm.columns} == {name: value[1] for name, value in expected_columns.items()}
        assert {column.name: _orm_default(column) for column in orm.columns} == {name: value[2] for name, value in expected_columns.items()}
        assert {column.name for column in orm.primary_key.columns} == {"id"}
        assert _orm_fks(orm) == _EXPECTED_FKS.get(table, set())
        assert {constraint.name for constraint in orm.constraints if isinstance(constraint, UniqueConstraint)} == _EXPECTED_UNIQUES.get(table, set())
        assert {index.name for index in orm.indexes if not index.unique} == _EXPECTED_INDEXES.get(table, set())
        orm_checks = {" ".join(str(constraint.sqltext).lower().split()) for constraint in orm.constraints if isinstance(constraint, CheckConstraint)}
        assert len(orm_checks) == len(_EXPECTED_CHECKS[table])
        for required in _EXPECTED_CHECKS[table]:
            assert any(required in value for value in orm_checks)


def _inspect_contract(connection):
    inspector = inspect(connection)
    actual = {}
    for table in _PUBLICATION_TABLES:
        columns = {}
        for column in inspector.get_columns(table):
            default = str(column["default"] or "").lower()
            marker = "identity" if column.get("identity") else ("now" if "now" in default else "false" if default == "false" else "0" if default == "0" else None)
            columns[column["name"]] = (_inspected_type(column), column["nullable"], marker)
        actual[table] = {
            "columns": columns,
            "pk": set(inspector.get_pk_constraint(table)["constrained_columns"]),
            "fks": {(fk["constrained_columns"][0], fk["referred_table"], fk.get("options", {}).get("ondelete")) for fk in inspector.get_foreign_keys(table)},
            "uniques": {item["name"] for item in inspector.get_unique_constraints(table)},
            "indexes": {item["name"] for item in inspector.get_indexes(table) if not item.get("unique")},
            "checks": {item["name"]: str(item["sqltext"]) for item in inspector.get_check_constraints(table)},
        }
    return actual


def _orm_type(column) -> str:
    rendered = str(column.type.compile(dialect=make_url("postgresql+asyncpg://").get_dialect()())).upper()
    return "TIMESTAMP WITH TIME ZONE" if rendered == "TIMESTAMP" and getattr(column.type, "timezone", False) else rendered


def _inspected_type(column) -> str:
    rendered = str(column["type"]).upper()
    return "TIMESTAMP WITH TIME ZONE" if rendered == "TIMESTAMP" and getattr(column["type"], "timezone", False) else rendered


def _orm_default(column) -> str | None:
    if column.identity is not None:
        return "identity"
    if column.server_default is None:
        return None
    value = str(column.server_default.arg).lower()
    return "now" if "now" in value else "false" if value == "false" else "0" if value == "0" else value


def _orm_fks(table) -> set[tuple[str, str, str | None]]:
    return {
        (column.name, foreign_key.column.table.name, foreign_key.ondelete)
        for column in table.columns
        for foreign_key in column.foreign_keys
    }


async def _exercise_live_constraints(url: str) -> None:
    engine = create_async_engine(url)
    subject_id, report_id, batch_id, publication_id = uuid4(), uuid4(), uuid4(), uuid4()
    try:
        async with engine.begin() as connection:
            await connection.execute(text("INSERT INTO company_report_subjects (id, normalized_identifier, identifier_type) VALUES (:id, '0000000000', 'legal_entity')"), {"id": subject_id})
            await connection.execute(text("INSERT INTO company_reports (id, subject_id, report_version, lifecycle_status, started_at) VALUES (:id, :subject, 'v1', 'complete', now())"), {"id": report_id, "subject": subject_id})
            generation = await connection.scalar(text("INSERT INTO company_report_publication_batches (id, state, requested_limit, candidate_count, policy_version) VALUES (:id, 'running', 1, 1, 'publication_sufficiency_v1') RETURNING generation"), {"id": batch_id})
            with pytest.raises(ProgrammingError):
                async with connection.begin_nested():
                    await connection.execute(text("UPDATE company_report_publication_batches SET generation = generation + 1 WHERE id = :id"), {"id": batch_id})
            await connection.execute(text("INSERT INTO company_report_publications (id, subject_id, report_id, status, canonical_slug, canonical_path, snapshot_hash, policy_version, batch_generation, indexable, sufficiency_status, published_lastmod) VALUES (:id, :subject, :report, 'active', 'test', '/company/0000000000-test', :hash, 'publication_sufficiency_v1', :generation, true, 'sufficient', now())"), {"id": publication_id, "subject": subject_id, "report": report_id, "hash": "a" * 64, "generation": generation})
            item_id = uuid4()
            await connection.execute(text("INSERT INTO company_report_publication_batch_items (id, batch_id, ordinal, subject_id, report_id, snapshot_hash, policy_version, state) VALUES (:id, :batch, 0, :subject, :report, :hash, 'publication_sufficiency_v1', 'pending')"), {"id": item_id, "batch": batch_id, "subject": subject_id, "report": report_id, "hash": "a" * 64})
            await connection.execute(text("INSERT INTO company_report_publication_journal (id, batch_id, ordinal, subject_id, report_id, snapshot_hash, policy_version, action, reason_code) VALUES (:id, :batch, 0, :subject, :report, :hash, 'publication_sufficiency_v1', 'published', 'sufficient')"), {"id": uuid4(), "batch": batch_id, "subject": subject_id, "report": report_id, "hash": "a" * 64})
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(text("INSERT INTO company_report_publications (id, subject_id, report_id, status, canonical_slug, canonical_path, snapshot_hash, policy_version, batch_generation, indexable, sufficiency_status, published_lastmod) VALUES (:id, :subject, :report, 'active', 'other', '/company/0000000000-other', :hash, 'publication_sufficiency_v1', 0, true, 'sufficient', now())"), {"id": uuid4(), "subject": subject_id, "report": uuid4(), "hash": "b" * 64})
            other_subject, other_report = uuid4(), uuid4()
            await connection.execute(text("INSERT INTO company_report_subjects (id, normalized_identifier, identifier_type) VALUES (:id, '0000000001', 'legal_entity')"), {"id": other_subject})
            await connection.execute(text("INSERT INTO company_reports (id, subject_id, report_version, lifecycle_status, started_at) VALUES (:id, :subject, 'v1', 'complete', now())"), {"id": other_report, "subject": other_subject})
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(text("INSERT INTO company_report_publications (id, subject_id, report_id, status, canonical_slug, canonical_path, snapshot_hash, policy_version, batch_generation, indexable, sufficiency_status, published_lastmod) VALUES (:id, :subject, :report, 'active', 'other', '/company/0000000001-other', :hash, 'publication_sufficiency_v1', :generation, true, 'sufficient', now())"), {"id": uuid4(), "subject": other_subject, "report": other_report, "hash": "b" * 64, "generation": generation + 1000})
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(text("INSERT INTO company_report_publication_batch_items (id, batch_id, ordinal, subject_id, report_id, snapshot_hash, policy_version, state) VALUES (:id, :batch, 0, :subject, :report, :hash, 'publication_sufficiency_v1', 'pending')"), {"id": uuid4(), "batch": batch_id, "subject": subject_id, "report": report_id, "hash": "a" * 64})
            assert await connection.scalar(text("SELECT count(*) FROM company_report_publications")) == 1
    finally:
        await engine.dispose()


async def _version_and_tables(url: str) -> tuple[str, set[str]]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            tables = set((await connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema() AND tablename = ANY(:tables)"), {"tables": list(_PUBLICATION_TABLES)})).scalars())
            return version, tables
    finally:
        await engine.dispose()


def _validated_test_admin_url(value: str):
    parsed = make_url(value)
    if parsed.get_backend_name() != "postgresql" or (parsed.host or "").lower() not in {"localhost", "127.0.0.1", "::1", "postgres"} or (parsed.database or "").lower() != "postgres":
        raise ValueError("TEST_POSTGRES_ADMIN_URL must name the disposable local postgres database")
    return parsed.set(drivername="postgresql+asyncpg") if parsed.drivername == "postgresql" else parsed


def _alembic_config(target_url: str) -> Config:
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", target_url.replace("%", "%%"))
    return config


async def _create_database(admin_url: str, database_name: str) -> None:
    _validate_database_name(database_name)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        await engine.dispose()


async def _drop_database(admin_url: str, database_name: str) -> None:
    _validate_database_name(database_name)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :name AND pid <> pg_backend_pid()"), {"name": database_name})
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
    finally:
        await engine.dispose()


def _validate_database_name(value: str) -> None:
    if not value.startswith(_DATABASE_PREFIX) or len(value.removeprefix(_DATABASE_PREFIX)) != 32:
        raise ValueError("refusing to mutate a database not generated by this test")
