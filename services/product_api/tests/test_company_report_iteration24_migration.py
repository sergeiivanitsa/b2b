"""Disposable PostgreSQL acceptance checks for revision 0018.

The iteration-24 runner creates two explicitly named loopback databases.  This
module owns their schemas: one database is reused for independent pre-DDL guard
probes, while the other is left at explicit revision ``0018`` for the
iteration-25 runner's separately verified forward-head handoff.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from product_api.company_reports.company_card_v2.finance import build_chart_facts
from product_api.company_reports.company_card_v2.models import (
    ArbitrationBasisV1,
    CompanyCardCounterpartyCoreV1,
    CompanyCardV2SnapshotV1,
    CompanyCardV2SnapshotV2,
    FinanceBasisV1,
    NarrativeEvidenceV1,
)
from product_api.company_reports.persistence.v3 import (
    calculate_company_card_v2_snapshot_hash,
    company_card_v2_to_snapshot,
)


PREDECESSOR = "0017_company_card_v2_ai_narrative"
REVISION = "0018_company_card_v2_arbitration"
GUARD_ERROR = "iteration24_active_h2_lineage_ambiguous"
H1_PROFILE = "h1_legacy_writer_v2"
H1_CONTRACT = "company_public_h1_v1"
H2_PROFILE = "company_card_v2_writer_v3"
H2_CONTRACT = "company_public_h2_v1"
H2_POLICY_V1 = "company_public_h2_publication_v1"


def test_iteration24_active_h2_guard_is_independent_and_pre_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard_url = _runner_target("TEST_POSTGRES_GUARD_URL", "i24_guard_")
    rendered = guard_url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", rendered)
    config = _alembic_config(rendered)
    command.upgrade(config, PREDECESSOR)

    scenarios = (
        ("pending_without_job", True, None, None),
        ("pending_with_mismatched_job", True, "queued", False),
        ("queued_job_with_mismatched_report", False, "queued", True),
        ("running_job_with_mismatched_report", False, "running", True),
        ("matching_pending_queued", True, "queued", True),
        ("matching_pending_running", True, "running", True),
    )
    for scenario, exact_report, job_state, exact_job in scenarios:
        asyncio.run(_clear_guard_rows(rendered))
        asyncio.run(
            _seed_guard_scenario(
                rendered,
                exact_report=exact_report,
                job_state=job_state,
                exact_job=exact_job,
            )
        )
        before = asyncio.run(_guard_state(rendered))

        with pytest.raises(RuntimeError, match=f"^{GUARD_ERROR}$"):
            command.upgrade(config, REVISION)

        assert asyncio.run(_revision(rendered)) == PREDECESSOR, scenario
        assert asyncio.run(_guard_state(rendered)) == before, scenario
        assert asyncio.run(_decision_columns(rendered)) == set(), scenario

    asyncio.run(_clear_guard_rows(rendered))
    asyncio.run(_assert_predecessor_job_fk_rejects_orphan(rendered))
    assert asyncio.run(_revision(rendered)) == PREDECESSOR
    assert asyncio.run(_decision_columns(rendered)) == set()


def test_iteration24_terminal_defaults_checks_and_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_url = _runner_target("TEST_POSTGRES_ROUNDTRIP_URL", "i24_roundtrip_")
    rendered = target_url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", rendered)
    config = _alembic_config(rendered)

    command.upgrade(config, PREDECESSOR)
    seeded = asyncio.run(_seed_terminal_and_historical_lineage(rendered))
    before = asyncio.run(_predecessor_rows(rendered))

    command.upgrade(config, REVISION)
    assert asyncio.run(_revision(rendered)) == REVISION
    asyncio.run(_assert_decision_schema_and_defaults(rendered, seeded))
    asyncio.run(_assert_disabled_nonnull_rejected(rendered, seeded))
    asyncio.run(_assert_historical_policy_is_pin_bound(rendered))

    command.downgrade(config, PREDECESSOR)
    assert asyncio.run(_revision(rendered)) == PREDECESSOR
    assert asyncio.run(_decision_columns(rendered)) == set()
    assert asyncio.run(_predecessor_rows(rendered)) == before

    command.upgrade(config, REVISION)
    assert asyncio.run(_revision(rendered)) == REVISION
    assert asyncio.run(_predecessor_rows(rendered)) == before
    asyncio.run(_assert_decision_schema_and_defaults(rendered, seeded))
    asyncio.run(_assert_historical_policy_is_pin_bound(rendered))


def _runner_target(variable: str, database_prefix: str) -> URL:
    raw = os.environ.get(variable)
    if not raw:
        pytest.skip(f"{variable} is not configured by the iteration-24 runner")
    parsed = make_url(raw)
    database = parsed.database or ""
    expected_database = re.compile(rf"^{re.escape(database_prefix)}[0-9a-f]{{12}}$")
    database_match = expected_database.fullmatch(database)
    suffix = database.removeprefix(database_prefix)
    if (
        parsed.drivername != "postgresql+asyncpg"
        or (parsed.host or "").lower() != "127.0.0.1"
        or parsed.port is None
        or database_match is None
        or parsed.username != f"i24u{suffix}"
        or bool(parsed.query)
    ):
        raise ValueError(f"{variable} must name the runner-owned disposable database")
    return parsed


def _alembic_config(target_url: str) -> Config:
    product_api = Path(__file__).resolve().parents[1]
    config = Config(str(product_api / "alembic.ini"))
    config.set_main_option("script_location", str(product_api / "alembic"))
    config.set_main_option("sqlalchemy.url", target_url.replace("%", "%%"))
    return config


async def _revision(url: str) -> str:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return str(await connection.scalar(text("SELECT version_num FROM alembic_version")))
    finally:
        await engine.dispose()


async def _decision_columns(url: str) -> set[tuple[str, str]]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema=current_schema() "
                    "AND table_name IN ('company_reports','company_report_jobs') "
                    "AND column_name IN "
                    "('arbitration_collection_enabled','arbitration_mask_key_id')"
                )
            )
            return {(str(row[0]), str(row[1])) for row in rows}
    finally:
        await engine.dispose()


async def _clear_guard_rows(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM company_report_subjects"))
    finally:
        await engine.dispose()


async def _seed_guard_scenario(
    url: str,
    *,
    exact_report: bool,
    job_state: str | None,
    exact_job: bool | None,
) -> None:
    subject_id, report_id = uuid4(), uuid4()
    report_profile = H2_PROFILE if exact_report else H1_PROFILE
    report_contract = H2_CONTRACT if exact_report else H1_CONTRACT
    report_version = "3" if exact_report else "2"
    report_generation = 1 if exact_report else 0
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO company_report_subjects "
                    "(id, normalized_identifier, identifier_type) "
                    "VALUES (:id, '7701234567', 'legal_entity_inn')"
                ),
                {"id": subject_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO company_reports "
                    "(id, subject_id, report_version, writer_profile, "
                    "presentation_contract, rollout_generation, lifecycle_status, "
                    "started_at, warnings_snapshot) VALUES "
                    "(:id, :subject_id, :report_version, :profile, :contract, "
                    ":generation, 'pending', now(), CAST('[]' AS json))"
                ),
                {
                    "id": report_id,
                    "subject_id": subject_id,
                    "report_version": report_version,
                    "profile": report_profile,
                    "contract": report_contract,
                    "generation": report_generation,
                },
            )
            if job_state is not None:
                assert exact_job is not None
                await _insert_job(
                    connection,
                    report_id=report_id,
                    subject_id=subject_id,
                    state=job_state,
                    profile=H2_PROFILE if exact_job else H1_PROFILE,
                    contract=H2_CONTRACT if exact_job else H1_CONTRACT,
                    generation=1 if exact_job else 0,
                )
    finally:
        await engine.dispose()


async def _insert_job(
    connection,
    *,
    report_id: UUID,
    subject_id: UUID,
    state: str,
    profile: str,
    contract: str,
    generation: int,
) -> None:
    job_id = uuid4()
    if state == "queued":
        await connection.execute(
            text(
                "INSERT INTO company_report_jobs "
                "(id, report_id, subject_id, state, writer_profile, "
                "presentation_contract, rollout_generation, fence_generation, "
                "attempt_count) VALUES (:id, :report_id, :subject_id, 'queued', "
                ":profile, :contract, :generation, 0, 0)"
            ),
            {
                "id": job_id,
                "report_id": report_id,
                "subject_id": subject_id,
                "profile": profile,
                "contract": contract,
                "generation": generation,
            },
        )
        return
    if state not in {"running", "succeeded"}:
        raise AssertionError(f"unsupported seeded job state: {state}")
    await connection.execute(
        text(
            "INSERT INTO company_report_jobs "
            "(id, report_id, subject_id, state, writer_profile, "
            "presentation_contract, rollout_generation, fence_generation, "
            "worker_token, attempt_count, claimed_at, heartbeat_at, "
            "lease_expires_at, finished_at) VALUES "
            "(:id, :report_id, :subject_id, :state, :profile, :contract, "
            ":generation, 1, :worker_token, 1, now(), now(), now(), "
            "CASE WHEN CAST(:state AS VARCHAR(16)) = 'succeeded' THEN now() ELSE NULL END)"
        ),
        {
            "id": job_id,
            "report_id": report_id,
            "subject_id": subject_id,
            "state": state,
            "profile": profile,
            "contract": contract,
            "generation": generation,
            "worker_token": uuid4(),
        },
    )


async def _guard_state(url: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            reports = (
                await connection.execute(
                    text(
                        "SELECT to_jsonb(r)::text FROM company_reports r ORDER BY r.id"
                    )
                )
            ).scalars().all()
            jobs = (
                await connection.execute(
                    text(
                        "SELECT to_jsonb(j)::text FROM company_report_jobs j ORDER BY j.id"
                    )
                )
            ).scalars().all()
            return tuple(reports), tuple(jobs)
    finally:
        await engine.dispose()


async def _assert_predecessor_job_fk_rejects_orphan(url: str) -> None:
    subject_id = uuid4()
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO company_report_subjects "
                    "(id, normalized_identifier, identifier_type) "
                    "VALUES (:id, '7701234567', 'legal_entity_inn')"
                ),
                {"id": subject_id},
            )
        async with engine.connect() as connection:
            transaction = await connection.begin()
            with pytest.raises(IntegrityError):
                await _insert_job(
                    connection,
                    report_id=uuid4(),
                    subject_id=subject_id,
                    state="queued",
                    profile=H2_PROFILE,
                    contract=H2_CONTRACT,
                    generation=1,
                )
            await transaction.rollback()
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM company_report_jobs")) == 0
    finally:
        await engine.dispose()


def _historical_snapshot(
    report_id: UUID,
    inn: str,
    *,
    version: int,
) -> CompanyCardV2SnapshotV1 | CompanyCardV2SnapshotV2:
    finance_basis = FinanceBasisV1()
    values = {
        "report_id": str(report_id),
        "subject_inn": inn,
        "target_inn": inn,
        "rollout_config_generation": 1,
        "generated_at": datetime(2026, 8, 27, tzinfo=timezone.utc),
        "counterparty": CompanyCardCounterpartyCoreV1(inn=inn, full_name="ООО Архив"),
        "finance_basis": finance_basis,
        "arbitration_basis": ArbitrationBasisV1(),
        "chart_facts": build_chart_facts(finance_basis),
        "evidence_version": "evidence_v1",
        "privacy_version": "privacy_v1",
    }
    if version == 1:
        return CompanyCardV2SnapshotV1(**values)
    if version == 2:
        return CompanyCardV2SnapshotV2(
            **values,
            narrative_evidence=NarrativeEvidenceV1(
                limitation_code="primary_activity_not_admitted"
            ),
        )
    raise AssertionError(f"unsupported historical snapshot version: {version}")


async def _seed_terminal_and_historical_lineage(url: str) -> dict[str, tuple[str, str]]:
    engine = create_async_engine(url)
    seeded: dict[str, tuple[str, str]] = {}
    try:
        async with engine.begin() as connection:
            # A predecessor H1 failure proves terminal defaulting is not
            # limited to successful H2 rows.
            h1_subject, h1_report, h1_job = uuid4(), uuid4(), uuid4()
            await connection.execute(
                text(
                    "INSERT INTO company_report_subjects "
                    "(id, normalized_identifier, identifier_type) "
                    "VALUES (:id, '7701234560', 'legal_entity_inn')"
                ),
                {"id": h1_subject},
            )
            await connection.execute(
                text(
                    "INSERT INTO company_reports "
                    "(id, subject_id, report_version, writer_profile, presentation_contract, "
                    "rollout_generation, lifecycle_status, started_at, finished_at, "
                    "warnings_snapshot, safe_error_snapshot) VALUES "
                    "(:id, :subject, '2', :profile, :contract, 0, 'failed', now(), now(), "
                    "CAST('[]' AS json), CAST('{\"code\":\"legacy_failure\"}' AS json))"
                ),
                {
                    "id": h1_report,
                    "subject": h1_subject,
                    "profile": H1_PROFILE,
                    "contract": H1_CONTRACT,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO company_report_jobs "
                    "(id, report_id, subject_id, state, writer_profile, presentation_contract, "
                    "rollout_generation, fence_generation, attempt_count, finished_at, "
                    "safe_failure_code) VALUES "
                    "(:id, :report, :subject, 'failed', :profile, :contract, 0, 0, 0, "
                    "now(), 'legacy_failure')"
                ),
                {
                    "id": h1_job,
                    "report": h1_report,
                    "subject": h1_subject,
                    "profile": H1_PROFILE,
                    "contract": H1_CONTRACT,
                },
            )
            seeded[str(h1_report)] = (str(h1_job), "failed")

            for offset, snapshot_version in enumerate((1, 2), start=1):
                subject_id, report_id = uuid4(), uuid4()
                inn = f"770123457{offset}"
                snapshot = _historical_snapshot(report_id, inn, version=snapshot_version)
                raw = company_card_v2_to_snapshot(snapshot)
                snapshot_hash = calculate_company_card_v2_snapshot_hash(snapshot)
                lifecycle = "complete" if snapshot_version == 1 else "partial"
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
                        "VALUES (:id, :subject, '3', :profile, :contract, 1, :lifecycle, "
                        "now(), now(), now(), CAST(:snapshot AS json), :snapshot_hash, "
                        "CAST('[]' AS json))"
                    ),
                    {
                        "id": report_id,
                        "subject": subject_id,
                        "profile": H2_PROFILE,
                        "contract": H2_CONTRACT,
                        "lifecycle": lifecycle,
                        "snapshot": json.dumps(raw, ensure_ascii=False),
                        "snapshot_hash": snapshot_hash,
                    },
                )
                await _insert_job(
                    connection,
                    report_id=report_id,
                    subject_id=subject_id,
                    state="succeeded",
                    profile=H2_PROFILE,
                    contract=H2_CONTRACT,
                    generation=1,
                )
                job_id = await connection.scalar(
                    text("SELECT id::text FROM company_report_jobs WHERE report_id=:report"),
                    {"report": report_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO company_report_presentation_pins "
                        "(subject_id, report_id, presentation_contract, generation, "
                        "snapshot_hash, chart_facts_version, chart_facts_hash, "
                        "evidence_registry_version, publication_policy_version, indexable, "
                        "narrative_binding_status) VALUES "
                        "(:subject, :report, :contract, 1, :snapshot_hash, :facts_version, "
                        ":facts_hash, :evidence_version, :policy, false, 'unresolved')"
                    ),
                    {
                        "subject": subject_id,
                        "report": report_id,
                        "contract": H2_CONTRACT,
                        "snapshot_hash": snapshot_hash,
                        "facts_version": snapshot.chart_facts.version,
                        "facts_hash": snapshot.chart_facts.hash,
                        "evidence_version": snapshot.evidence_version,
                        "policy": H2_POLICY_V1,
                    },
                )
                seeded[str(report_id)] = (str(job_id), lifecycle)
    finally:
        await engine.dispose()
    return seeded


async def _predecessor_rows(url: str) -> tuple[tuple[str, str], ...]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT table_name, payload FROM ("
                    "SELECT 'company_report_subjects' AS table_name, to_jsonb(s)::text AS payload "
                    "FROM company_report_subjects s "
                    "UNION ALL "
                    "SELECT 'company_reports', "
                    "(to_jsonb(r) - 'arbitration_collection_enabled' "
                    "- 'arbitration_mask_key_id')::text FROM company_reports r "
                    "UNION ALL "
                    "SELECT 'company_report_jobs', "
                    "(to_jsonb(j) - 'arbitration_collection_enabled' "
                    "- 'arbitration_mask_key_id')::text FROM company_report_jobs j "
                    "UNION ALL "
                    "SELECT 'company_report_presentation_pins', to_jsonb(p)::text "
                    "FROM company_report_presentation_pins p"
                    ") predecessor ORDER BY table_name, payload"
                )
            )
            return tuple((str(row[0]), str(row[1])) for row in rows)
    finally:
        await engine.dispose()


async def _assert_decision_schema_and_defaults(
    url: str,
    seeded: dict[str, tuple[str, str]],
) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            columns = (
                await connection.execute(
                    text(
                        "SELECT table_name, column_name, is_nullable, column_default, "
                        "data_type, character_maximum_length FROM information_schema.columns "
                        "WHERE table_schema=current_schema() "
                        "AND table_name IN ('company_reports','company_report_jobs') "
                        "AND column_name IN "
                        "('arbitration_collection_enabled','arbitration_mask_key_id')"
                    )
                )
            ).mappings().all()
            by_column = {
                (str(row["table_name"]), str(row["column_name"])): row for row in columns
            }
            for table_name in ("company_reports", "company_report_jobs"):
                enabled = by_column[(table_name, "arbitration_collection_enabled")]
                key_id = by_column[(table_name, "arbitration_mask_key_id")]
                assert (enabled["is_nullable"], enabled["data_type"]) == ("NO", "boolean")
                assert str(enabled["column_default"]).lower() == "false"
                assert (key_id["is_nullable"], key_id["data_type"]) == (
                    "YES",
                    "character varying",
                )
                assert key_id["column_default"] is None
                assert key_id["character_maximum_length"] == 32

            constraints = dict(
                (
                    str(row[0]),
                    " ".join(str(row[1]).lower().split()),
                )
                for row in await connection.execute(
                    text(
                        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conname IN "
                        "('ck_company_reports_company_reports_arbitration_decision', "
                        "'ck_company_report_jobs_company_report_jobs_arbitration_decision')"
                    )
                )
            )
            assert set(constraints) == {
                "ck_company_reports_company_reports_arbitration_decision",
                "ck_company_report_jobs_company_report_jobs_arbitration_decision",
            }
            assert all(
                "arbitration_collection_enabled" in definition
                and "arbitration_mask_key_id is null" in definition
                for definition in constraints.values()
            )

            report_rows = (
                await connection.execute(
                    text(
                        "SELECT id::text, arbitration_collection_enabled, "
                        "arbitration_mask_key_id FROM company_reports ORDER BY id"
                    )
                )
            ).tuples().all()
            job_rows = (
                await connection.execute(
                    text(
                        "SELECT report_id::text, arbitration_collection_enabled, "
                        "arbitration_mask_key_id FROM company_report_jobs ORDER BY report_id"
                    )
                )
            ).tuples().all()
            assert {row[0] for row in report_rows} == set(seeded)
            assert {row[0] for row in job_rows} == set(seeded)
            assert all(tuple(row[1:]) == (False, None) for row in report_rows)
            assert all(tuple(row[1:]) == (False, None) for row in job_rows)
    finally:
        await engine.dispose()


async def _assert_disabled_nonnull_rejected(
    url: str,
    seeded: dict[str, tuple[str, str]],
) -> None:
    report_id = next(iter(seeded))
    job_id = seeded[report_id][0]
    engine = create_async_engine(url)
    try:
        for table_name, row_id in (
            ("company_reports", report_id),
            ("company_report_jobs", job_id),
        ):
            async with engine.connect() as connection:
                transaction = await connection.begin()
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(
                            f"UPDATE {table_name} SET arbitration_mask_key_id="
                            "'forbidden_key' WHERE id=:id"
                        ),
                        {"id": UUID(row_id)},
                    )
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _assert_historical_policy_is_pin_bound(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT r.normalized_snapshot->>'snapshot_schema_version' AS schema, "
                        "r.arbitration_collection_enabled, r.arbitration_mask_key_id, "
                        "p.snapshot_hash=r.snapshot_hash AS same_hash, "
                        "p.publication_policy_version, p.narrative_binding_status "
                        "FROM company_reports r "
                        "JOIN company_report_presentation_pins p ON p.report_id=r.id "
                        "WHERE p.presentation_contract=:contract ORDER BY schema NULLS FIRST"
                    ),
                    {"contract": H2_CONTRACT},
                )
            ).tuples().all()
            assert [tuple(row) for row in rows] == [
                (None, False, None, True, H2_POLICY_V1, "unresolved"),
                (
                    "company_card_v2_snapshot_v2",
                    False,
                    None,
                    True,
                    H2_POLICY_V1,
                    "unresolved",
                ),
            ]
    finally:
        await engine.dispose()
