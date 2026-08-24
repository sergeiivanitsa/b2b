"""PostgreSQL contract checks for revision 0017.

The disposable runbook upgrades an empty database before this module runs, so
these assertions inspect the actual PostgreSQL schema rather than ORM metadata.
"""
from __future__ import annotations

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
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeRuntimeControl,
)


@pytest.mark.asyncio
async def test_narrative_tables_and_fail_closed_control_are_created(engine):
    required = {
        "company_card_narrative_outbox",
        "company_card_narrative_runtime_control",
        "company_card_narrative_budget_windows",
        "company_card_narrative_budget_reservations",
        "company_card_narrative_jobs",
        "company_card_narrative_artifacts",
    }
    async with engine.connect() as connection:
        tables = set(
            (await connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")
            )).scalars()
        )
        control = (await connection.execute(text(
            "SELECT enabled, kill_switch, daily_limit, monthly_limit, concurrency_limit, leased_count "
            "FROM company_card_narrative_runtime_control WHERE singleton_id = 1"
        ))).one()

    assert required <= tables
    assert tuple(control) == (False, True, 0, 0, 0, 0)


@pytest.mark.asyncio
async def test_narrative_generation_key_and_outbox_event_are_unique(engine):
    async with engine.connect() as connection:
        indexes = set((await connection.execute(text(
            "SELECT indexname FROM pg_indexes WHERE schemaname=current_schema() "
            "AND tablename IN ('company_card_narrative_jobs','company_card_narrative_outbox')"
        ))).scalars())
    assert "ix_company_card_narrative_jobs_ready_selection" in indexes
    assert "ix_company_card_narrative_jobs_expired_selection" in indexes
    assert "ix_company_card_narrative_outbox_pending_selection" in indexes
    assert any("generation_key" in index for index in indexes)
    assert any("outbox" in index and "event" in index for index in indexes)


@pytest.mark.asyncio
async def test_narrative_hash_columns_indexes_and_runtime_cap_match_orm_contract(engine):
    expected_hash_columns = {
        ("company_card_narrative_outbox", "snapshot_hash"),
        ("company_card_narrative_outbox", "generation_key"),
        ("company_card_narrative_jobs", "snapshot_hash"),
        ("company_card_narrative_jobs", "generation_key"),
        ("company_card_narrative_budget_reservations", "generation_key"),
        ("company_card_narrative_artifacts", "snapshot_hash"),
        ("company_card_narrative_artifacts", "generation_key"),
        ("company_card_narrative_artifacts", "binding_key"),
        ("company_card_narrative_artifacts", "artifact_identity"),
        ("company_card_narrative_artifacts", "fallback_identity"),
        ("company_card_narrative_artifacts", "validated_render_plan_bytes_sha256"),
        ("company_card_narrative_artifacts", "rendered_output_bytes_sha256"),
    }
    orm_runtime_check = next(
        constraint
        for constraint in CompanyCardNarrativeRuntimeControl.__table__.constraints
        if constraint.name.endswith("company_card_narrative_runtime_nonnegative")
    )
    physical_constraint_name = (
        postgresql.dialect()
        .identifier_preparer
        .truncate_and_render_constraint_name(orm_runtime_check.name)
    )
    async with engine.connect() as connection:
        rows = (await connection.execute(text(
            "SELECT table_name, column_name, data_type, character_maximum_length "
            "FROM information_schema.columns WHERE table_schema=current_schema() "
            "AND table_name LIKE 'company_card_narrative_%'"
        ))).all()
        index_names = set((await connection.execute(text(
            "SELECT indexname FROM pg_indexes WHERE schemaname=current_schema() "
            "AND tablename='company_card_narrative_artifacts'"
        ))).scalars())
        runtime_check = await connection.scalar(text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='company_card_narrative_runtime_control'::regclass "
            "AND conname=:constraint_name"
        ), {"constraint_name": physical_constraint_name})
    by_column = {(row[0], row[1]): (row[2], row[3]) for row in rows}
    assert expected_hash_columns <= by_column.keys()
    assert all(by_column[key] == ("character", 64) for key in expected_hash_columns)
    assert "ix_company_card_narrative_artifacts_exact_lookup" in index_names
    assert runtime_check is not None
    assert "concurrency_limit = 0" in runtime_check
    assert "concurrency_limit >= leased_count" in runtime_check


_DATABASE_PREFIX = "i21_narrative_migration_"


def test_company_card_narrative_clean_0016_upgrade_downgrade_reupgrade(monkeypatch) -> None:
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    admin, database_name, target = _disposable_target(admin_url)
    asyncio.run(_create_database(admin, database_name))
    try:
        monkeypatch.setenv("DATABASE_URL", target)
        config = _alembic_config(target)
        command.upgrade(config, "0016_company_card_v2_foundation")
        command.upgrade(config, "0017_company_card_v2_ai_narrative")
        assert asyncio.run(_revision(target)) == "0017_company_card_v2_ai_narrative"
        assert asyncio.run(_runtime_defaults(target)) == (False, True, 0, 0, 0, 0)
        command.downgrade(config, "0016_company_card_v2_foundation")
        assert asyncio.run(_revision(target)) == "0016_company_card_v2_foundation"
        assert asyncio.run(_table_absent(target, "company_card_narrative_jobs"))
        command.upgrade(config, "0017_company_card_v2_ai_narrative")
        assert asyncio.run(_revision(target)) == "0017_company_card_v2_ai_narrative"
    finally:
        asyncio.run(_drop_database(admin, database_name))


def test_company_card_narrative_populated_legacy_backfill_and_downgrade_refusal(monkeypatch) -> None:
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    admin, database_name, target = _disposable_target(admin_url)
    asyncio.run(_create_database(admin, database_name))
    try:
        monkeypatch.setenv("DATABASE_URL", target)
        config = _alembic_config(target)
        command.upgrade(config, "0016_company_card_v2_foundation")
        report_id, snapshot_hash = asyncio.run(_seed_legacy_report(target, corrupt=False))
        command.upgrade(config, "0017_company_card_v2_ai_narrative")
        assert asyncio.run(_outbox_binding(target)) == (report_id, snapshot_hash, "pending")
        with pytest.raises(RuntimeError, match="refuse to discard narrative data"):
            command.downgrade(config, "0016_company_card_v2_foundation")
        assert asyncio.run(_revision(target)) == "0017_company_card_v2_ai_narrative"
        assert asyncio.run(_outbox_binding(target)) == (report_id, snapshot_hash, "pending")
    finally:
        asyncio.run(_drop_database(admin, database_name))


def test_company_card_narrative_corrupt_backfill_aborts_atomically(monkeypatch) -> None:
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    admin, database_name, target = _disposable_target(admin_url)
    asyncio.run(_create_database(admin, database_name))
    try:
        monkeypatch.setenv("DATABASE_URL", target)
        config = _alembic_config(target)
        command.upgrade(config, "0016_company_card_v2_foundation")
        asyncio.run(_seed_legacy_report(target, corrupt=True))
        with pytest.raises(RuntimeError, match="cannot backfill corrupt company report snapshot"):
            command.upgrade(config, "0017_company_card_v2_ai_narrative")
        assert asyncio.run(_revision(target)) == "0016_company_card_v2_foundation"
        assert asyncio.run(_table_absent(target, "company_card_narrative_outbox"))
        assert asyncio.run(_legacy_report_count(target)) == 1
    finally:
        asyncio.run(_drop_database(admin, database_name))


def test_company_card_narrative_resolved_pin_refuses_downgrade(monkeypatch) -> None:
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    admin, database_name, target = _disposable_target(admin_url)
    asyncio.run(_create_database(admin, database_name))
    try:
        monkeypatch.setenv("DATABASE_URL", target)
        config = _alembic_config(target)
        command.upgrade(config, "0017_company_card_v2_ai_narrative")
        asyncio.run(_seed_resolved_pin(target))
        with pytest.raises(RuntimeError, match="refuse to discard narrative data"):
            command.downgrade(config, "0016_company_card_v2_foundation")
        assert asyncio.run(_resolved_pin_count(target)) == 1
        assert asyncio.run(_revision(target)) == "0017_company_card_v2_ai_narrative"
    finally:
        asyncio.run(_drop_database(admin, database_name))


def _disposable_target(value: str) -> tuple[str, str, str]:
    parsed = make_url(value)
    host, database = (parsed.host or "").lower(), (parsed.database or "").lower()
    if (
        parsed.get_backend_name() != "postgresql"
        or host not in {"localhost", "127.0.0.1", "::1", "postgres"}
        or database != "postgres"
    ):
        raise ValueError("TEST_POSTGRES_ADMIN_URL must name local disposable postgres")
    admin = (
        parsed.set(drivername="postgresql+asyncpg")
        if parsed.drivername == "postgresql"
        else parsed
    )
    name = f"{_DATABASE_PREFIX}{uuid4().hex}"
    return (
        admin.render_as_string(hide_password=False),
        name,
        admin.set(database=name).render_as_string(hide_password=False),
    )


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
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=:name AND pid<>pg_backend_pid()"
                ),
                {"name": name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    finally:
        await engine.dispose()


async def _seed_legacy_report(url: str, *, corrupt: bool) -> tuple[str, str]:
    subject_id, report_id = uuid4(), uuid4()
    snapshot = {
        "report_id": str(report_id),
        "report_version": "2",
        "target_identifier": "7701234567",
        "counterparty": {"inn": "7701234567", "full_name": "ООО Миграция"},
    }
    snapshot_hash = hashlib.sha256(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    stored_hash = "0" * 64 if corrupt else snapshot_hash
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(
                "INSERT INTO company_report_subjects (id, normalized_identifier, identifier_type) "
                "VALUES (:id, '7701234567', 'legal_entity_inn')"
            ), {"id": subject_id})
            await connection.execute(text(
                "INSERT INTO company_reports "
                "(id, subject_id, report_version, lifecycle_status, started_at, generated_at, "
                "normalized_snapshot, snapshot_hash, warnings_snapshot, usable_for_public_page, "
                "usable_for_future_scoring, writer_profile, presentation_contract, rollout_generation) "
                "VALUES (:id, :subject, '2', 'complete', now(), now(), CAST(:snapshot AS json), "
                ":hash, CAST('[]' AS json), true, false, 'h1_legacy_writer_v2', "
                "'company_public_h1_v1', 0)"
            ), {
                "id": report_id,
                "subject": subject_id,
                "snapshot": json.dumps(snapshot, ensure_ascii=False),
                "hash": stored_hash,
            })
    finally:
        await engine.dispose()
    return str(report_id), stored_hash


async def _seed_resolved_pin(url: str) -> None:
    subject_id, report_id, job_id, artifact_id = uuid4(), uuid4(), uuid4(), uuid4()
    snapshot = {"report_version": "3"}
    snapshot_hash = hashlib.sha256(b'{"report_version":"3"}').hexdigest()
    generation_key, binding_key = "a" * 64, "b" * 64
    identity = {
        "identity_version": "GenerationIdentityV2",
        "report_id": str(report_id),
        "snapshot_hash": snapshot_hash,
    }
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(
                "INSERT INTO company_report_subjects (id, normalized_identifier, identifier_type) "
                "VALUES (:id, '7701234568', 'legal_entity_inn')"
            ), {"id": subject_id})
            await connection.execute(text(
                "INSERT INTO company_reports "
                "(id, subject_id, report_version, lifecycle_status, started_at, generated_at, "
                "normalized_snapshot, snapshot_hash, warnings_snapshot, usable_for_public_page, "
                "usable_for_future_scoring, writer_profile, presentation_contract, rollout_generation) "
                "VALUES (:id, :subject, '3', 'complete', now(), now(), CAST(:snapshot AS json), "
                ":hash, CAST('[]' AS json), false, false, 'company_card_v2_writer_v3', "
                "'company_public_h2_v1', 1)"
            ), {"id": report_id, "subject": subject_id, "snapshot": json.dumps(snapshot), "hash": snapshot_hash})
            await connection.execute(text(
                "INSERT INTO company_card_narrative_jobs "
                "(id, report_id, snapshot_hash, generation_key, identity_version, generation_identity, "
                "state, available_at, artifact_id) VALUES (:id, :report, :hash, :key, "
                "'GenerationIdentityV2', CAST(:identity AS jsonb), 'fallback_finalized', now(), :artifact)"
            ), {"id": job_id, "report": report_id, "hash": snapshot_hash, "key": generation_key,
                "identity": json.dumps(identity), "artifact": artifact_id})
            await connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            await connection.execute(text(
                "INSERT INTO company_card_narrative_artifacts "
                "(id, report_id, snapshot_hash, generation_key, binding_kind, binding_key, "
                "fallback_identity, rendered_description, statement_ids, evidence_ids, "
                "phrase_trace, validation_codes, renderer_version, rendered_output_bytes_sha256) "
                "VALUES (:id, :report, :hash, :key, 'fallback', :binding, :binding, "
                "'Описание', CAST('[]' AS jsonb), CAST('[]' AS jsonb), CAST('[]' AS jsonb), "
                "CAST('[]' AS jsonb), 'company_card_h2_fallback_renderer_v1', :output_hash)"
            ), {"id": artifact_id, "report": report_id, "hash": snapshot_hash, "key": generation_key,
                "binding": binding_key,
                "output_hash": hashlib.sha256("Описание".encode()).hexdigest()})
            await connection.execute(text(
                "INSERT INTO company_report_presentation_pins "
                "(subject_id, report_id, presentation_contract, generation, snapshot_hash, "
                "publication_policy_version, canonical_path, indexable, published_lastmod, projection_digest, "
                "narrative_binding_status, narrative_binding_kind, narrative_binding_key, chart_facts_version, "
                "chart_facts_hash, evidence_registry_version) VALUES (:subject, :report, "
                "'company_public_h2_v1', 1, :hash, 'policy_v1', NULL, false, NULL, :digest, "
                "'resolved', 'fallback', :binding, 'chart_v1', :chart, 'evidence_v1')"
            ), {"subject": subject_id, "report": report_id, "hash": snapshot_hash,
                "digest": "c" * 64, "binding": binding_key, "chart": "d" * 64})
    finally:
        await engine.dispose()


async def _revision(url: str) -> str:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()


async def _runtime_defaults(url: str) -> tuple[object, ...]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            row = (await connection.execute(text(
                "SELECT enabled, kill_switch, daily_limit, monthly_limit, concurrency_limit, leased_count "
                "FROM company_card_narrative_runtime_control WHERE singleton_id=1"
            ))).one()
            return tuple(row)
    finally:
        await engine.dispose()


async def _outbox_binding(url: str) -> tuple[str, str, str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            row = (await connection.execute(text(
                "SELECT report_id::text, snapshot_hash, state FROM company_card_narrative_outbox"
            ))).one()
            return row[0], row[1], row[2]
    finally:
        await engine.dispose()


async def _resolved_pin_count(url: str) -> int:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text(
                "SELECT count(*) FROM company_report_presentation_pins "
                "WHERE narrative_binding_status='resolved'"
            ))
    finally:
        await engine.dispose()


async def _legacy_report_count(url: str) -> int:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT count(*) FROM company_reports"))
    finally:
        await engine.dispose()


async def _table_absent(url: str, table: str) -> bool:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return not bool(await connection.scalar(text("SELECT to_regclass(:table)"), {"table": table}))
    finally:
        await engine.dispose()


def _validate_database_name(value: str) -> None:
    suffix = value.removeprefix(_DATABASE_PREFIX)
    if (
        not value.startswith(_DATABASE_PREFIX)
        or len(value) > 63
        or len(suffix) != 32
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError("refusing to mutate an unmanaged database")
