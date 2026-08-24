import asyncio
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


_DATABASE_PREFIX = "company_card_v2_migration_"


async def test_company_card_v2_foundation_tables_and_legacy_defaults(engine) -> None:
    async with engine.connect() as connection:
        names = set((await connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname=current_schema()"))).scalars())
        assert {
            "company_report_presentations",
            "company_report_presentation_pins",
            "company_report_h2_lifecycle_heads",
            "company_report_presentation_staged_pointers",
            "company_report_presentation_assignments",
            "company_report_presentation_assignment_journal",
        } <= names
        columns = set((await connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='company_reports'"))).scalars())
        assert {"writer_profile", "presentation_contract", "rollout_generation"} <= columns
        pin_columns = set((await connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='company_report_presentation_pins'"))).scalars())
        assert "id" not in pin_columns
        assert {"subject_id", "presentation_contract", "generation"} <= pin_columns
        constraints = set((await connection.execute(text("SELECT conname FROM pg_constraint WHERE conrelid='company_report_presentation_pins'::regclass"))).scalars())
        assert "pk_company_report_presentation_pins" in constraints
        assert "fk_company_report_presentation_pins_report_subject" in constraints


def test_company_card_v2_clean_0015_upgrade_downgrade_reupgrade(monkeypatch) -> None:
    """Exercise 0016 from historical data, then prove the round-trip is stable."""
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    admin = _validated_test_admin_url(admin_url)
    database_name = f"{_DATABASE_PREFIX}{uuid4().hex}"
    target = admin.set(database=database_name)
    rendered_admin = admin.render_as_string(hide_password=False)
    rendered_target = target.render_as_string(hide_password=False)
    asyncio.run(_create_database(rendered_admin, database_name))
    try:
        # The repository Alembic environment gives DATABASE_URL precedence
        # over config.ini. Point that process-local setting at this uniquely
        # named disposable database, never the runbook's main test database.
        monkeypatch.setenv("DATABASE_URL", rendered_target)
        config = _alembic_config(rendered_target)
        command.upgrade(config, "0015_claims_company_report_handoff")
        expected = asyncio.run(_seed_valid_active_h1(rendered_target))
        command.upgrade(config, "0016_company_card_v2_foundation")
        assert asyncio.run(_read_h1_import(rendered_target)) == expected
        assert asyncio.run(_revision(rendered_target)) == "0016_company_card_v2_foundation"
        command.downgrade(config, "0015_claims_company_report_handoff")
        assert asyncio.run(_revision(rendered_target)) == "0015_claims_company_report_handoff"
        assert asyncio.run(_table_absent(rendered_target, "company_report_presentation_pins"))
        command.upgrade(config, "0016_company_card_v2_foundation")
        assert asyncio.run(_read_h1_import(rendered_target)) == expected
    finally:
        asyncio.run(_drop_database(rendered_admin, database_name))


@pytest.mark.parametrize("corrupt_kind", ("cross_subject", "policy", "slug_path"))
def test_company_card_v2_corrupt_h1_import_aborts_atomically(monkeypatch, corrupt_kind: str) -> None:
    """A malformed active publication cannot leave a partially-upgraded schema."""
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    admin = _validated_test_admin_url(admin_url)
    database_name = f"{_DATABASE_PREFIX}{uuid4().hex}"
    target = admin.set(database=database_name)
    rendered_admin = admin.render_as_string(hide_password=False)
    rendered_target = target.render_as_string(hide_password=False)
    asyncio.run(_create_database(rendered_admin, database_name))
    try:
        monkeypatch.setenv("DATABASE_URL", rendered_target)
        config = _alembic_config(rendered_target)
        command.upgrade(config, "0015_claims_company_report_handoff")
        asyncio.run(_seed_valid_active_h1(rendered_target, corrupt_kind=corrupt_kind))
        with pytest.raises(RuntimeError, match="cannot import corrupt active H1 publication"):
            command.upgrade(config, "0016_company_card_v2_foundation")
        assert asyncio.run(_revision(rendered_target)) == "0015_claims_company_report_handoff"
        assert asyncio.run(_table_absent(rendered_target, "company_report_presentation_pins"))
        assert asyncio.run(_column_absent(rendered_target, "company_reports", "writer_profile"))
        assert asyncio.run(_count_active_publications(rendered_target)) == 1
    finally:
        asyncio.run(_drop_database(rendered_admin, database_name))


def _validated_test_admin_url(value: str):
    parsed = make_url(value)
    host, database = (parsed.host or "").lower(), (parsed.database or "").lower()
    if parsed.get_backend_name() != "postgresql" or host not in {"localhost", "127.0.0.1", "::1", "postgres"} or database != "postgres":
        raise ValueError("TEST_POSTGRES_ADMIN_URL must name local disposable postgres")
    return parsed.set(drivername="postgresql+asyncpg") if parsed.drivername == "postgresql" else parsed


def _alembic_config(target_url: str) -> Config:
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", target_url.replace("%", "%%"))
    return config


async def _create_database(admin_url: str, name: str) -> None:
    _validate_database_name(name)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await engine.dispose()


async def _drop_database(admin_url: str, name: str) -> None:
    _validate_database_name(name)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :name AND pid <> pg_backend_pid()"), {"name": name})
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    finally:
        await engine.dispose()


async def _seed_valid_active_h1(url: str, *, corrupt_kind: str | None = None) -> tuple[str, str, str, int]:
    subject_id, report_id, batch_id, publication_id = uuid4(), uuid4(), uuid4(), uuid4()
    inn = "7701234567"
    name = "ООО Миграция"
    slug = "ooo-migraciya"
    snapshot = {"report_id": str(report_id), "report_version": "2", "target_identifier": inn, "counterparty": {"inn": inn, "full_name": name}}
    snapshot_hash = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    publication_subject_id = subject_id
    path = f"/company/{inn}-{slug}"
    policy = "publication_sufficiency_v1"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("INSERT INTO company_report_subjects (id, normalized_identifier, identifier_type) VALUES (:id, :inn, 'legal_entity_inn')"), {"id": subject_id, "inn": inn})
            if corrupt_kind == "cross_subject":
                # 0015 has independent subject/report FKs, so this is valid
                # historical storage but must be rejected atomically by 0016.
                publication_subject_id = uuid4()
                corrupt_inn = "7701234568"
                path = f"/company/{corrupt_inn}-{slug}"
                await connection.execute(text("INSERT INTO company_report_subjects (id, normalized_identifier, identifier_type) VALUES (:id, :inn, 'legal_entity_inn')"), {"id": publication_subject_id, "inn": corrupt_inn})
            elif corrupt_kind == "policy":
                policy = "publication_sufficiency_v999"
            elif corrupt_kind == "slug_path":
                slug = "wrong-slug"
                path = f"/company/{inn}-{slug}"
            await connection.execute(text("INSERT INTO company_reports (id, subject_id, report_version, lifecycle_status, started_at, generated_at, normalized_snapshot, snapshot_hash, warnings_snapshot, usable_for_public_page, usable_for_future_scoring) VALUES (:id, :subject, '2', 'complete', now(), now(), CAST(:snapshot AS json), :hash, CAST('[]' AS json), true, false)"), {"id": report_id, "subject": subject_id, "snapshot": json.dumps(snapshot), "hash": snapshot_hash})
            generation = await connection.scalar(text("INSERT INTO company_report_publication_batches (id, state, requested_limit, candidate_count, policy_version, next_ordinal) VALUES (:id, 'completed', 1, 1, 'publication_sufficiency_v1', 1) RETURNING generation"), {"id": batch_id})
            await connection.execute(text("INSERT INTO company_report_publications (id, subject_id, report_id, status, canonical_slug, canonical_path, snapshot_hash, policy_version, batch_generation, indexable, sufficiency_status, published_lastmod) VALUES (:id, :subject, :report, 'active', :slug, :path, :hash, :policy, :generation, true, 'sufficient', now())"), {"id": publication_id, "subject": publication_subject_id, "report": report_id, "slug": slug, "path": path, "hash": snapshot_hash, "policy": policy, "generation": generation})
    finally:
        await engine.dispose()
    return str(subject_id), str(report_id), snapshot_hash, generation


async def _read_h1_import(url: str) -> tuple[str, str, str, int]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            row = (await connection.execute(text("SELECT subject_id::text, report_id::text, snapshot_hash, generation FROM company_report_presentation_pins WHERE presentation_contract='company_public_h1_v1'"))).one()
            return row[0], row[1], row[2], row[3]
    finally:
        await engine.dispose()


async def _revision(url: str) -> str:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()


async def _table_absent(url: str, table: str) -> bool:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return not bool(await connection.scalar(text("SELECT to_regclass(:table)"), {"table": table}))
    finally:
        await engine.dispose()


async def _column_absent(url: str, table: str, column: str) -> bool:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return not bool(await connection.scalar(text("SELECT 1 FROM information_schema.columns WHERE table_name=:table AND column_name=:column"), {"table": table, "column": column}))
    finally:
        await engine.dispose()


async def _count_active_publications(url: str) -> int:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT count(*) FROM company_report_publications WHERE status='active'"))
    finally:
        await engine.dispose()


def _validate_database_name(value: str) -> None:
    suffix = value.removeprefix(_DATABASE_PREFIX)
    if not value.startswith(_DATABASE_PREFIX) or len(suffix) != 32 or any(char not in "0123456789abcdef" for char in suffix):
        raise ValueError("refusing to mutate an unmanaged database")
