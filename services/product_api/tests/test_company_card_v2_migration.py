import asyncio
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
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
        runtime_columns = set(
            (
                await connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='company_card_narrative_runtime_control'"
                    )
                )
            ).scalars()
        )
        assert "quota_mode" in runtime_columns


def test_company_card_v2_clean_0015_head_refuses_lossy_downgrade(monkeypatch) -> None:
    """Upgrade 0015 data and prove the narrative downgrade fails atomically."""
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
        expected_jobs = asyncio.run(_seed_legacy_job_cohort(rendered_target))
        legacy_job_snapshot = asyncio.run(_read_legacy_job_cohort(rendered_target))
        expected_migrated_jobs = {
            job_id: (
                state,
                attempt_count,
                "h1_legacy_writer_v2",
                "company_public_h1_v1",
                0,
                attempt_count,
                "h1_legacy_writer_v2",
                "company_public_h1_v1",
                0,
            )
            for job_id, (state, attempt_count) in expected_jobs.items()
        }
        command.upgrade(config, "head")
        assert asyncio.run(_read_h1_import(rendered_target)) == expected
        assert asyncio.run(_read_legacy_job_cohort(rendered_target)) == legacy_job_snapshot
        assert asyncio.run(_read_migrated_job_cohort(rendered_target)) == expected_migrated_jobs
        assert asyncio.run(_revision(rendered_target)) == "0020_company_card_narrative_quota_mode"
        with pytest.raises(RuntimeError, match="refuse to discard narrative data"):
            command.downgrade(config, "0015_claims_company_report_handoff")
        assert asyncio.run(_revision(rendered_target)) == "0020_company_card_narrative_quota_mode"
        assert not asyncio.run(
            _table_absent(rendered_target, "company_report_presentation_pins")
        )
        assert not asyncio.run(
            _column_absent(rendered_target, "company_report_jobs", "fence_generation")
        )
        assert asyncio.run(_read_h1_import(rendered_target)) == expected
        assert asyncio.run(_read_legacy_job_cohort(rendered_target)) == legacy_job_snapshot
        assert asyncio.run(_read_migrated_job_cohort(rendered_target)) == expected_migrated_jobs
        # A retry at head is a no-op. Production rollback is an exact backup
        # restore to 0015, never a lossy Alembic downgrade of migrated data.
        command.upgrade(config, "head")
        assert asyncio.run(_read_h1_import(rendered_target)) == expected
        assert asyncio.run(_read_legacy_job_cohort(rendered_target)) == legacy_job_snapshot
        assert asyncio.run(_read_migrated_job_cohort(rendered_target)) == expected_migrated_jobs
        assert asyncio.run(_revision(rendered_target)) == "0020_company_card_narrative_quota_mode"
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


async def _seed_legacy_job_cohort(url: str) -> dict[str, tuple[str, int]]:
    """Seed every valid 0013 job shape observed in an existing installation."""
    claimed_at = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    heartbeat_at = claimed_at + timedelta(seconds=10)
    lease_expires_at = claimed_at + timedelta(minutes=1)
    finished_at = claimed_at + timedelta(seconds=30)
    shapes = (("succeeded", 1),) * 15 + (
        ("queued", 0),
        ("running", 1),
        ("failed", 0),
        ("failed", 1),
    )
    expected: dict[str, tuple[str, int]] = {}
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            for ordinal, (state, attempt_count) in enumerate(shapes):
                subject_id, report_id, job_id = uuid4(), uuid4(), uuid4()
                worker_token = uuid4() if attempt_count == 1 else None
                has_attempt = attempt_count == 1
                is_terminal = state in {"succeeded", "failed"}
                await connection.execute(
                    text(
                        "INSERT INTO company_report_subjects "
                        "(id, normalized_identifier, identifier_type) "
                        "VALUES (:id, :inn, 'legal_entity_inn')"
                    ),
                    {"id": subject_id, "inn": f"77012346{ordinal:02d}"},
                )
                await connection.execute(
                    text(
                        "INSERT INTO company_reports "
                        "(id, subject_id, report_version, lifecycle_status, started_at, "
                        "generated_at, finished_at, warnings_snapshot, usable_for_public_page, "
                        "usable_for_future_scoring) VALUES "
                        "(:id, :subject, '2', :lifecycle, :started_at, :generated_at, "
                        ":finished_at, CAST('[]' AS json), false, false)"
                    ),
                    {
                        "id": report_id,
                        "subject": subject_id,
                        "lifecycle": (
                            "pending"
                            if state in {"queued", "running"}
                            else "complete" if state == "succeeded" else "failed"
                        ),
                        "started_at": claimed_at,
                        "generated_at": finished_at if state == "succeeded" else None,
                        "finished_at": finished_at if is_terminal else None,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO company_report_jobs "
                        "(id, report_id, subject_id, state, worker_token, attempt_count, "
                        "claimed_at, heartbeat_at, lease_expires_at, finished_at, "
                        "safe_failure_code, created_at, updated_at) VALUES "
                        "(:id, :report, :subject, :state, :worker_token, :attempt_count, "
                        ":claimed_at, :heartbeat_at, :lease_expires_at, :finished_at, "
                        ":safe_failure_code, :created_at, :updated_at)"
                    ),
                    {
                        "id": job_id,
                        "report": report_id,
                        "subject": subject_id,
                        "state": state,
                        "worker_token": worker_token,
                        "attempt_count": attempt_count,
                        "claimed_at": claimed_at if has_attempt else None,
                        "heartbeat_at": heartbeat_at if has_attempt else None,
                        "lease_expires_at": lease_expires_at if has_attempt else None,
                        "finished_at": finished_at if is_terminal else None,
                        "safe_failure_code": "provider_failed" if state == "failed" else None,
                        "created_at": claimed_at - timedelta(minutes=1),
                        "updated_at": finished_at if is_terminal else heartbeat_at,
                    },
                )
                expected[str(job_id)] = (state, attempt_count)
    finally:
        await engine.dispose()
    return expected


async def _read_legacy_job_cohort(url: str) -> list[tuple[object, ...]]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return [
                tuple(row)
                for row in (
                    await connection.execute(
                        text(
                            "SELECT id::text, report_id::text, subject_id::text, state, "
                            "worker_token::text, attempt_count, claimed_at, heartbeat_at, "
                            "lease_expires_at, finished_at, safe_failure_code, created_at, updated_at "
                            "FROM company_report_jobs ORDER BY id"
                        )
                    )
                ).all()
            ]
    finally:
        await engine.dispose()


async def _read_migrated_job_cohort(
    url: str,
) -> dict[str, tuple[str, int, str, str, int, int, str, str, int]]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT j.id::text, j.state, j.attempt_count, j.writer_profile, "
                        "j.presentation_contract, j.rollout_generation, j.fence_generation, "
                        "r.writer_profile, r.presentation_contract, r.rollout_generation "
                        "FROM company_report_jobs j "
                        "JOIN company_reports r ON r.id = j.report_id ORDER BY j.id"
                    )
                )
            ).all()
            return {row[0]: tuple(row[1:]) for row in rows}
    finally:
        await engine.dispose()


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
