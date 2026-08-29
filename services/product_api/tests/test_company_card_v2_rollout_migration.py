"""Real-PostgreSQL contract for additive rollout-control revision 0019."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from product_api.company_reports.persistence.presentations import (
    PresentationAssignmentConflict,
    bind_rollout_decision,
)


REVISION = "0019_company_card_v2_rollout_control"
PREDECESSOR = "0018_company_card_v2_arbitration"
_DATABASE_PREFIX = "i25_rollout_migration_"


def test_company_card_v2_rollout_clean_upgrade_downgrade_reupgrade(
    monkeypatch,
) -> None:
    admin_url = _admin_url()
    admin, database_name, target = _disposable_target(admin_url)
    asyncio.run(_create_database(admin, database_name))
    try:
        monkeypatch.setenv("DATABASE_URL", target)
        config = _alembic_config(target)
        command.upgrade(config, PREDECESSOR)
        seeded = asyncio.run(_seed_legacy_assignment(target))
        before = asyncio.run(_legacy_rows(target))

        command.upgrade(config, REVISION)
        assert asyncio.run(_revision(target)) == REVISION
        after = asyncio.run(_legacy_rows(target))
        assert after == before
        assert asyncio.run(_new_columns_are_null(target, seeded))
        constraint_definitions = asyncio.run(_rollout_constraint_definitions(target))
        assert "FOREIGN KEY (assignment_id, subject_id)" in constraint_definitions[
            "fk_company_report_presentation_journal_assignment_subject"
        ]
        assert "UNIQUE (id, subject_id)" in constraint_definitions[
            "uq_company_report_presentation_assignment_id_subject"
        ]

        command.downgrade(config, PREDECESSOR)
        assert asyncio.run(_revision(target)) == PREDECESSOR
        assert asyncio.run(_legacy_rows(target)) == before
        assert not asyncio.run(
            _column_exists(target, "company_report_presentation_pins", "projection_scope")
        )
        assert not asyncio.run(
            _table_exists(target, "company_card_v2_rollout_decisions")
        )

        command.upgrade(config, REVISION)
        assert asyncio.run(_revision(target)) == REVISION
        assert asyncio.run(_legacy_rows(target)) == before
    finally:
        asyncio.run(_drop_database(admin, database_name))


def test_company_card_v2_rollout_downgrade_refuses_new_scope_or_audit(
    monkeypatch,
) -> None:
    admin_url = _admin_url()
    admin, database_name, target = _disposable_target(admin_url)
    asyncio.run(_create_database(admin, database_name))
    try:
        monkeypatch.setenv("DATABASE_URL", target)
        config = _alembic_config(target)
        command.upgrade(config, REVISION)
        seeded = asyncio.run(_seed_legacy_assignment(target))

        h2_subject = asyncio.run(_seed_staged_h2_pin(target))
        with pytest.raises(RuntimeError, match="iteration25_rollout_control_data_present"):
            command.downgrade(config, PREDECESSOR)
        assert asyncio.run(_revision(target)) == REVISION
        asyncio.run(_delete_subject(target, h2_subject))

        decision_id = uuid4()
        asyncio.run(_insert_decision(target, decision_id, "d" * 64))
        with pytest.raises(RuntimeError, match="iteration25_rollout_control_data_present"):
            command.downgrade(config, PREDECESSOR)
        assert asyncio.run(_revision(target)) == REVISION

        asyncio.run(
            _audit_legacy_journal(
                target,
                assignment_id=seeded["assignment_id"],
                decision_id=decision_id,
                decision_digest="d" * 64,
            )
        )
        with pytest.raises(RuntimeError, match="iteration25_rollout_control_data_present"):
            command.downgrade(config, PREDECESSOR)
        assert asyncio.run(_revision(target)) == REVISION
        assert asyncio.run(_audited_journal_count(target)) == 1
    finally:
        asyncio.run(_drop_database(admin, database_name))


@pytest.mark.asyncio
async def test_company_card_v2_rollout_cross_subject_journal_rejected(engine) -> None:
    first = await _seed_h1_assignment_on_connection(engine, "7701234567")
    second = await _seed_h1_assignment_on_connection(engine, "500100732259")
    decision_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO company_card_v2_rollout_decisions "
                "(decision_id, decision_digest, schema_version, release_commit, "
                "action, stage, target_contract, h2_indexable, target_count) VALUES "
                "(:id, :digest, 'company_card_v2_rollout_decision_v1', :commit, "
                "'rollback', 'emergency_rollback', 'company_public_h1_v1', false, 1)"
            ),
            {"id": decision_id, "digest": "e" * 64, "commit": "f" * 40},
        )

    async with engine.connect() as connection:
        transaction = await connection.begin()
        with pytest.raises(IntegrityError):
            await connection.execute(
                text(
                    "INSERT INTO company_report_presentation_assignment_journal "
                    "(id, assignment_id, subject_id, presentation_contract, "
                    "pin_generation, generation, decision_id) VALUES "
                    "(:id, :assignment, :subject, 'company_public_h1_v1', "
                    "1, 2, :decision)"
                ),
                {
                    "id": uuid4(),
                    "assignment": first["assignment_id"],
                    "subject": first["subject_id"],
                    "decision": decision_id,
                },
            )
        await transaction.rollback()

    async with engine.connect() as connection:
        transaction = await connection.begin()
        with pytest.raises(IntegrityError):
            await connection.execute(
                text(
                    "INSERT INTO company_report_presentation_assignment_journal "
                    "(id, assignment_id, subject_id, presentation_contract, "
                    "pin_generation, generation, decision_id, decision_digest, reason_code) "
                    "VALUES (:id, :assignment, :wrong_subject, 'company_public_h1_v1', "
                    "1, 2, :decision, :digest, 'rollback_emergency_rollback')"
                ),
                {
                    "id": uuid4(),
                    "assignment": first["assignment_id"],
                    "wrong_subject": second["subject_id"],
                    "decision": decision_id,
                    "digest": "e" * 64,
                },
            )
        await transaction.rollback()


@pytest.mark.asyncio
async def test_company_card_v2_rollout_decision_binding_race_is_closed(engine) -> None:
    async def bind(decision_id: UUID, digest: str) -> str:
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                async with session.begin():
                    await bind_rollout_decision(
                        session,
                        decision_id=decision_id,
                        decision_digest=digest,
                        schema_version="company_card_v2_rollout_decision_v1",
                        release_commit="a" * 40,
                        action="activate",
                        stage="allowlist",
                        target_contract="company_public_h2_v1",
                        h2_indexable=False,
                        target_count=1,
                    )
            return "bound"
        except PresentationAssignmentConflict:
            return "conflict"

    same_id = uuid4()
    assert await asyncio.gather(
        bind(same_id, "6" * 64),
        bind(same_id, "6" * 64),
    ) == ["bound", "bound"]

    first_id, second_id = uuid4(), uuid4()
    outcomes = await asyncio.gather(
        bind(first_id, "7" * 64),
        bind(second_id, "7" * 64),
    )
    assert sorted(outcomes) == ["bound", "conflict"]
    async with engine.connect() as connection:
        assert await connection.scalar(
            text(
                "SELECT count(*) FROM company_card_v2_rollout_decisions "
                "WHERE decision_digest IN (:same_digest, :race_digest)"
            ),
            {"same_digest": "6" * 64, "race_digest": "7" * 64},
        ) == 2


@pytest.mark.asyncio
async def test_company_card_v2_rollout_downgrade_writer_race(engine) -> None:
    """A writer cannot enter between downgrade guard and transactional DDL."""
    decision_id = uuid4()
    values = {
        "id": decision_id,
        "digest": "a" * 64,
        "commit": "b" * 40,
    }
    first = await engine.connect()
    second = await engine.connect()
    first_tx = await first.begin()
    try:
        for table in (
            "company_card_v2_rollout_decisions",
            "company_report_presentation_assignments",
            "company_report_presentation_pins",
            "company_report_presentation_assignment_journal",
        ):
            await first.execute(
                text(f"LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE")
            )
        assert not await first.scalar(
            text("SELECT EXISTS (SELECT 1 FROM company_card_v2_rollout_decisions)")
        )

        second_tx = await second.begin()
        await second.execute(text("SET LOCAL lock_timeout = '250ms'"))
        with pytest.raises(DBAPIError):
            await second.execute(_decision_insert_sql(), values)
        await second_tx.rollback()

        await first_tx.commit()
        async with second.begin():
            await second.execute(_decision_insert_sql(), values)
        assert await second.scalar(
            text(
                "SELECT count(*) FROM company_card_v2_rollout_decisions "
                "WHERE decision_id=:id"
            ),
            {"id": decision_id},
        ) == 1
    finally:
        if first.in_transaction():
            await first.rollback()
        if second.in_transaction():
            await second.rollback()
        await first.close()
        await second.close()


def _admin_url() -> str:
    value = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not value:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    return value


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
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await engine.dispose()


async def _drop_database(admin_url: str, name: str) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                     "WHERE datname=:name AND pid <> pg_backend_pid()"),
                {"name": name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    finally:
        await engine.dispose()


async def _revision(url: str) -> str:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            value = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert isinstance(value, str)
            return value
    finally:
        await engine.dispose()


async def _seed_legacy_assignment(url: str) -> dict[str, UUID]:
    ids = {
        "subject_id": uuid4(),
        "report_id": uuid4(),
        "assignment_id": uuid4(),
        "journal_id": uuid4(),
    }
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO company_report_subjects "
                    "(id, normalized_identifier, identifier_type) "
                    "VALUES (:id, '7701234567', 'legal_entity_inn')"
                ),
                {"id": ids["subject_id"]},
            )
            await connection.execute(
                text(
                    "INSERT INTO company_reports "
                    "(id, subject_id, report_version, writer_profile, presentation_contract, "
                    "rollout_generation, lifecycle_status, started_at, generated_at, "
                    "finished_at, normalized_snapshot, snapshot_hash, warnings_snapshot) "
                    "VALUES (:id, :subject, '2', 'h1_legacy_writer_v2', "
                    "'company_public_h1_v1', 0, 'complete', now(), now(), now(), "
                    "CAST('{}' AS json), :hash, CAST('[]' AS json))"
                ),
                {
                    "id": ids["report_id"],
                    "subject": ids["subject_id"],
                    "hash": "1" * 64,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO company_report_presentation_pins "
                    "(subject_id, report_id, presentation_contract, generation, "
                    "snapshot_hash, publication_policy_version, canonical_path, "
                    "indexable, published_lastmod) VALUES "
                    "(:subject, :report, 'company_public_h1_v1', 1, :hash, "
                    "'publication_sufficiency_v1', '/company/7701234567-company', "
                    "true, now())"
                ),
                {
                    "subject": ids["subject_id"],
                    "report": ids["report_id"],
                    "hash": "1" * 64,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO company_report_presentation_assignments "
                    "(id, subject_id, presentation_contract, pin_generation, generation) "
                    "VALUES (:id, :subject, 'company_public_h1_v1', 1, 1)"
                ),
                {"id": ids["assignment_id"], "subject": ids["subject_id"]},
            )
            await connection.execute(
                text(
                    "INSERT INTO company_report_presentation_assignment_journal "
                    "(id, assignment_id, subject_id, presentation_contract, "
                    "pin_generation, generation) VALUES "
                    "(:id, :assignment, :subject, 'company_public_h1_v1', 1, 1)"
                ),
                {
                    "id": ids["journal_id"],
                    "assignment": ids["assignment_id"],
                    "subject": ids["subject_id"],
                },
            )
    finally:
        await engine.dispose()
    return ids


async def _legacy_rows(url: str) -> tuple[str, str, str, str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            subject = await connection.scalar(
                text("SELECT to_jsonb(s)::text FROM company_report_subjects s")
            )
            report = await connection.scalar(
                text("SELECT to_jsonb(r)::text FROM company_reports r")
            )
            pin = await connection.scalar(
                text(
                    "SELECT (to_jsonb(p) - 'projection_scope')::text "
                    "FROM company_report_presentation_pins p"
                )
            )
            journal = await connection.scalar(
                text(
                    "SELECT (to_jsonb(j) - 'decision_id' - 'decision_digest' "
                    "- 'reason_code')::text "
                    "FROM company_report_presentation_assignment_journal j"
                )
            )
            return str(subject), str(report), str(pin), str(journal)
    finally:
        await engine.dispose()


async def _new_columns_are_null(url: str, seeded: dict[str, UUID]) -> bool:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            pin_scope = await connection.scalar(
                text(
                    "SELECT projection_scope FROM company_report_presentation_pins "
                    "WHERE subject_id=:subject"
                ),
                {"subject": seeded["subject_id"]},
            )
            journal = (
                await connection.execute(
                    text(
                        "SELECT decision_id, decision_digest, reason_code "
                        "FROM company_report_presentation_assignment_journal "
                        "WHERE id=:id"
                    ),
                    {"id": seeded["journal_id"]},
                )
            ).one()
            return pin_scope is None and tuple(journal) == (None, None, None)
    finally:
        await engine.dispose()


async def _rollout_constraint_definitions(url: str) -> dict[str, str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname IN ("
                    "'fk_company_report_presentation_journal_assignment_subject', "
                    "'uq_company_report_presentation_assignment_id_subject')"
                )
            )
            return {str(row[0]): str(row[1]) for row in rows}
    finally:
        await engine.dispose()


async def _column_exists(url: str, table: str, column: str) -> bool:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                        "WHERE table_schema=current_schema() AND table_name=:table "
                        "AND column_name=:column)"
                    ),
                    {"table": table, "column": column},
                )
            )
    finally:
        await engine.dispose()


async def _table_exists(url: str, table: str) -> bool:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text("SELECT to_regclass(:table) IS NOT NULL"), {"table": table}
                )
            )
    finally:
        await engine.dispose()


async def _seed_staged_h2_pin(url: str) -> UUID:
    subject_id, report_id = uuid4(), uuid4()
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO company_report_subjects "
                    "(id, normalized_identifier, identifier_type) "
                    "VALUES (:id, '500100732259', 'individual_entrepreneur_inn')"
                ),
                {"id": subject_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO company_reports "
                    "(id, subject_id, report_version, writer_profile, presentation_contract, "
                    "rollout_generation, lifecycle_status, started_at, generated_at, "
                    "finished_at, normalized_snapshot, snapshot_hash, warnings_snapshot, "
                    "arbitration_collection_enabled, arbitration_mask_key_id) VALUES "
                    "(:id, :subject, '3', 'company_card_v2_writer_v3', "
                    "'company_public_h2_v1', 1, 'complete', now(), now(), now(), "
                    "CAST('{}' AS json), :hash, CAST('[]' AS json), true, 'mask_test')"
                ),
                {"id": report_id, "subject": subject_id, "hash": "2" * 64},
            )
            await connection.execute(
                text(
                    "INSERT INTO company_report_presentation_pins "
                    "(subject_id, report_id, presentation_contract, generation, "
                    "snapshot_hash, chart_facts_version, chart_facts_hash, "
                    "evidence_registry_version, publication_policy_version, "
                    "projection_scope, indexable, narrative_binding_status) VALUES "
                    "(:subject, :report, 'company_public_h2_v1', 1, :hash, "
                    "'facts_v1', :facts_hash, 'evidence_v1', "
                    "'company_public_h2_publication_v3', 'staged_publication', "
                    "false, 'unresolved')"
                ),
                {
                    "subject": subject_id,
                    "report": report_id,
                    "hash": "2" * 64,
                    "facts_hash": "3" * 64,
                },
            )
    finally:
        await engine.dispose()
    return subject_id


async def _delete_subject(url: str, subject_id: UUID) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM company_report_subjects WHERE id=:id"),
                {"id": subject_id},
            )
    finally:
        await engine.dispose()


def _decision_insert_sql():
    return text(
        "INSERT INTO company_card_v2_rollout_decisions "
        "(decision_id, decision_digest, schema_version, release_commit, action, "
        "stage, target_contract, h2_indexable, target_count) VALUES "
        "(:id, :digest, 'company_card_v2_rollout_decision_v1', :commit, "
        "'rollback', 'emergency_rollback', 'company_public_h1_v1', false, 1)"
    )


async def _insert_decision(url: str, decision_id: UUID, digest: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                _decision_insert_sql(),
                {"id": decision_id, "digest": digest, "commit": "c" * 40},
            )
    finally:
        await engine.dispose()


async def _audit_legacy_journal(
    url: str,
    *,
    assignment_id: UUID,
    decision_id: UUID,
    decision_digest: str,
) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE company_report_presentation_assignment_journal SET "
                    "decision_id=:decision, decision_digest=:digest, "
                    "reason_code='rollback_emergency_rollback' "
                    "WHERE assignment_id=:assignment"
                ),
                {
                    "decision": decision_id,
                    "digest": decision_digest,
                    "assignment": assignment_id,
                },
            )
    finally:
        await engine.dispose()


async def _audited_journal_count(url: str) -> int:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return int(
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM "
                        "company_report_presentation_assignment_journal "
                        "WHERE decision_id IS NOT NULL"
                    )
                )
            )
    finally:
        await engine.dispose()


async def _seed_h1_assignment_on_connection(engine, inn: str) -> dict[str, UUID]:
    subject_id, report_id, assignment_id = uuid4(), uuid4(), uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO company_report_subjects "
                "(id, normalized_identifier, identifier_type) "
                "VALUES (:id, :inn, 'legal_entity_inn')"
            ),
            {"id": subject_id, "inn": inn},
        )
        await connection.execute(
            text(
                "INSERT INTO company_reports "
                "(id, subject_id, report_version, writer_profile, presentation_contract, "
                "rollout_generation, lifecycle_status, started_at, generated_at, "
                "finished_at, normalized_snapshot, snapshot_hash, warnings_snapshot) "
                "VALUES (:id, :subject, '2', 'h1_legacy_writer_v2', "
                "'company_public_h1_v1', 0, 'complete', now(), now(), now(), "
                "CAST('{}' AS json), :hash, CAST('[]' AS json))"
            ),
            {"id": report_id, "subject": subject_id, "hash": "4" * 64},
        )
        await connection.execute(
            text(
                "INSERT INTO company_report_presentation_pins "
                "(subject_id, report_id, presentation_contract, generation, "
                "snapshot_hash, publication_policy_version, canonical_path, "
                "indexable, published_lastmod) VALUES "
                "(:subject, :report, 'company_public_h1_v1', 1, :hash, "
                "'publication_sufficiency_v1', :path, true, now())"
            ),
            {
                "subject": subject_id,
                "report": report_id,
                "hash": "4" * 64,
                "path": f"/company/{inn}-company",
            },
        )
        await connection.execute(
            text(
                "INSERT INTO company_report_presentation_assignments "
                "(id, subject_id, presentation_contract, pin_generation, generation) "
                "VALUES (:id, :subject, 'company_public_h1_v1', 1, 1)"
            ),
            {"id": assignment_id, "subject": subject_id},
        )
    return {"subject_id": subject_id, "assignment_id": assignment_id}
