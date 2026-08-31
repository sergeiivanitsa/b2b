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
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine


_PREFIX = "company_url_0021_"


def test_company_page_url_0021_upgrade_has_no_backfill_and_round_trips(monkeypatch):
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    admin = _validated_admin_url(admin_url)
    name = f"{_PREFIX}{uuid4().hex}"
    target = admin.set(database=name)
    admin_text = admin.render_as_string(hide_password=False)
    target_text = target.render_as_string(hide_password=False)
    asyncio.run(_create_database(admin_text, name))
    try:
        monkeypatch.setenv("DATABASE_URL", target_text)
        config = _config(target_text)
        command.upgrade(config, "0020_company_card_narrative_quota_mode")
        historical = asyncio.run(_insert_historical_null_pin(target_text))
        before = asyncio.run(_schema_fingerprint(target_text))
        command.upgrade(config, "0021_company_page_canonical_urls")
        after = asyncio.run(_schema_fingerprint(target_text))
        assert after[0] == before[0]
        assert after[1] == before[1] == (0, 1)
        assert asyncio.run(_pin_json(target_text, historical[1])) == historical[2]
        checks = after[2]
        assert all(
            token in checks
            for token in (
                "ooo|ao|oao|zao|pao|ip",
                "staged_publication",
                "canonical_path is null",
            )
        )
        assert after[3] == ("trg_company_report_h2_pin_url_binding_guard_v1",)
        command.downgrade(config, "0020_company_card_narrative_quota_mode")
        command.upgrade(config, "0021_company_page_canonical_urls")
        assert asyncio.run(_version(target_text)) == "0021_company_page_canonical_urls"
    finally:
        asyncio.run(_drop_database(admin_text, name))


def test_company_page_url_0021_enforces_new_h2_binding_lifecycle(monkeypatch):
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    admin = _validated_admin_url(admin_url)
    name = f"{_PREFIX}{uuid4().hex}"
    target = admin.set(database=name)
    admin_text = admin.render_as_string(hide_password=False)
    target_text = target.render_as_string(hide_password=False)
    asyncio.run(_create_database(admin_text, name))
    try:
        monkeypatch.setenv("DATABASE_URL", target_text)
        config = _config(target_text)
        command.upgrade(config, "0021_company_page_canonical_urls")
        rows = asyncio.run(_assert_new_h2_lifecycle_guard(target_text))
        assert rows == (
            (1, "/company/ooo-romashka-7707079463", "staged_publication", "unresolved"),
            (2, "/company/ooo-romashka-7707079463", "staged_publication", "resolved"),
            (3, "/company/ooo-romashka-7707079463", "active_publication", "resolved"),
        )
    finally:
        asyncio.run(_drop_database(admin_text, name))


def test_company_page_url_0021_historical_null_continues_via_legacy_fallback(monkeypatch):
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    admin = _validated_admin_url(admin_url)
    name = f"{_PREFIX}{uuid4().hex}"
    target = admin.set(database=name)
    admin_text = admin.render_as_string(hide_password=False)
    target_text = target.render_as_string(hide_password=False)
    asyncio.run(_create_database(admin_text, name))
    try:
        monkeypatch.setenv("DATABASE_URL", target_text)
        config = _config(target_text)
        command.upgrade(config, "0020_company_card_narrative_quota_mode")
        historical = asyncio.run(_insert_historical_null_pin(target_text))
        command.upgrade(config, "0021_company_page_canonical_urls")
        paths = asyncio.run(_continue_historical_null_lifecycle(target_text, historical))
        assert paths == (None, "/company/7707079463-company", "/company/7707079463-company")
    finally:
        asyncio.run(_drop_database(admin_text, name))


@pytest.mark.parametrize("incompatible", ("h1_v2", "h2_v2", "h2_staged_legacy"))
def test_company_page_url_0021_downgrade_guards_every_new_binding(monkeypatch, incompatible):
    admin_url = os.environ.get("TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        pytest.skip("TEST_POSTGRES_ADMIN_URL is not configured")
    admin = _validated_admin_url(admin_url)
    name = f"{_PREFIX}{uuid4().hex}"
    target = admin.set(database=name)
    admin_text = admin.render_as_string(hide_password=False)
    target_text = target.render_as_string(hide_password=False)
    asyncio.run(_create_database(admin_text, name))
    try:
        monkeypatch.setenv("DATABASE_URL", target_text)
        config = _config(target_text)
        command.upgrade(config, "0021_company_page_canonical_urls")
        if incompatible == "h1_v2":
            asyncio.run(_insert_v2_publication(target_text))
        elif incompatible == "h2_v2":
            asyncio.run(_assert_new_h2_lifecycle_guard(target_text))
        else:
            asyncio.run(_insert_new_h2_unresolved(target_text, "/company/7707079463-company"))
        with pytest.raises(RuntimeError, match="refuse to discard"):
            command.downgrade(config, "0020_company_card_narrative_quota_mode")
        assert asyncio.run(_version(target_text)) == "0021_company_page_canonical_urls"
    finally:
        asyncio.run(_drop_database(admin_text, name))


async def _schema_fingerprint(url: str):
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            columns = tuple((await connection.execute(text(
                "SELECT table_name,column_name,data_type,is_nullable "
                "FROM information_schema.columns WHERE table_schema=current_schema() "
                "AND table_name IN ('company_report_publications','company_report_presentation_pins') "
                "ORDER BY table_name,ordinal_position"
            ))).all())
            counts = tuple((await connection.execute(text(
                "SELECT (SELECT count(*) FROM company_report_publications), "
                "(SELECT count(*) FROM company_report_presentation_pins)"
            ))).one())
            checks = " ".join((await connection.execute(text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE contype='c' AND conrelid IN ("
                "'company_report_publications'::regclass,"
                "'company_report_presentation_pins'::regclass) "
                "ORDER BY conrelid::regclass::text,conname"
            ))).scalars()).lower()
            triggers = tuple((await connection.execute(text(
                "SELECT tgname FROM pg_trigger "
                "WHERE tgrelid='company_report_presentation_pins'::regclass "
                "AND NOT tgisinternal ORDER BY tgname"
            ))).scalars())
            return columns, counts, checks, triggers
    finally:
        await engine.dispose()


async def _insert_historical_null_pin(url: str):
    engine = create_async_engine(url)
    subject_id, report_id = uuid4(), uuid4()
    try:
        async with engine.begin() as connection:
            await _insert_h2_report(connection, subject_id=subject_id, report_id=report_id)
            await connection.execute(text(
                "INSERT INTO company_report_presentation_pins "
                "(subject_id,report_id,presentation_contract,generation,snapshot_hash,"
                "chart_facts_version,chart_facts_hash,evidence_registry_version,publication_policy_version,"
                "projection_scope,canonical_path,indexable,published_lastmod,projection_digest,"
                "narrative_binding_status,narrative_binding_kind,narrative_binding_key) "
                "VALUES (:subject,:report,'company_public_h2_v1',1,:hash,'chart_facts_v2',:chart,"
                "'evidence_registry_v1','company_public_h2_publication_v3','staged_publication',NULL,"
                "false,NULL,NULL,'unresolved',NULL,NULL)"
            ), {"subject": subject_id, "report": report_id, "hash": "a" * 64, "chart": "b" * 64})
            snapshot = await connection.scalar(text(
                "SELECT to_jsonb(p)::text FROM company_report_presentation_pins p "
                "WHERE p.report_id=:report"
            ), {"report": report_id})
            return subject_id, report_id, snapshot
    finally:
        await engine.dispose()


async def _pin_json(url: str, report_id) -> str:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text(
                "SELECT to_jsonb(p)::text FROM company_report_presentation_pins p "
                "WHERE p.report_id=:report"
            ), {"report": report_id})
    finally:
        await engine.dispose()


async def _insert_h2_report(connection, *, subject_id, report_id) -> None:
    await connection.execute(text(
        "INSERT INTO company_report_subjects (id,normalized_identifier,identifier_type) "
        "VALUES (:id,'7707079463','legal_entity_inn')"
    ), {"id": subject_id})
    await connection.execute(text(
        "INSERT INTO company_reports "
        "(id,subject_id,report_version,writer_profile,presentation_contract,rollout_generation,"
        "lifecycle_status,started_at,generated_at,finished_at,normalized_snapshot,snapshot_hash,"
        "warnings_snapshot,usable_for_public_page,usable_for_future_scoring) "
        "VALUES (:id,:subject,'3','company_card_v2_writer_v3','company_public_h2_v1',1,"
        "'complete',now(),now(),now(),CAST(:snapshot AS json),:hash,CAST('[]' AS json),false,false)"
    ), {"id": report_id, "subject": subject_id, "snapshot": "{}", "hash": "a" * 64})


async def _insert_fallback_artifact(connection, *, report_id) -> str:
    job_id, artifact_id = uuid4(), uuid4()
    generation_key, binding_key = "d" * 64, "e" * 64
    identity = json.dumps({
        "identity_version": "GenerationIdentityV2",
        "report_id": str(report_id),
        "snapshot_hash": "a" * 64,
    })
    await connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    await connection.execute(text(
        "INSERT INTO company_card_narrative_jobs "
        "(id,report_id,snapshot_hash,generation_key,identity_version,generation_identity,"
        "state,available_at,artifact_id) VALUES (:id,:report,:hash,:key,'GenerationIdentityV2',"
        "CAST(:identity AS jsonb),'fallback_finalized',now(),:artifact)"
    ), {"id": job_id, "report": report_id, "hash": "a" * 64, "key": generation_key,
        "identity": identity, "artifact": artifact_id})
    await connection.execute(text(
        "INSERT INTO company_card_narrative_artifacts "
        "(id,report_id,snapshot_hash,generation_key,binding_kind,binding_key,fallback_identity,"
        "rendered_description,statement_ids,evidence_ids,phrase_trace,validation_codes,renderer_version,"
        "rendered_output_bytes_sha256) VALUES (:id,:report,:hash,:key,'fallback',:binding,:binding,"
        "'Описание',CAST('[]' AS jsonb),CAST('[]' AS jsonb),CAST('[]' AS jsonb),CAST('[]' AS jsonb),"
        "'company_card_h2_fallback_renderer_v1',:output_hash)"
    ), {"id": artifact_id, "report": report_id, "hash": "a" * 64, "key": generation_key,
        "binding": binding_key, "output_hash": hashlib.sha256("Описание".encode()).hexdigest()})
    return binding_key


def _unresolved_insert(path: str | None):
    return text(
        "INSERT INTO company_report_presentation_pins "
        "(subject_id,report_id,presentation_contract,generation,snapshot_hash,chart_facts_version,"
        "chart_facts_hash,evidence_registry_version,publication_policy_version,projection_scope,"
        "canonical_path,indexable,published_lastmod,projection_digest,narrative_binding_status,"
        "narrative_binding_kind,narrative_binding_key) VALUES (:subject,:report,'company_public_h2_v1',"
        "1,:hash,'chart_facts_v2',:chart,'evidence_registry_v1','company_public_h2_publication_v3',"
        "'staged_publication',:path,false,NULL,NULL,'unresolved',NULL,NULL)"
    ), path


def _resolved_insert(path: str | None, binding_key: str):
    return text(
        "INSERT INTO company_report_presentation_pins "
        "(subject_id,report_id,presentation_contract,generation,snapshot_hash,chart_facts_version,"
        "chart_facts_hash,evidence_registry_version,publication_policy_version,projection_scope,"
        "canonical_path,indexable,published_lastmod,projection_digest,narrative_binding_status,"
        "narrative_binding_kind,narrative_binding_key) VALUES (:subject,:report,'company_public_h2_v1',"
        "2,:hash,'chart_facts_v2',:chart,'evidence_registry_v1','company_public_h2_publication_v3',"
        "'staged_publication',:path,false,NULL,:digest,'resolved','fallback',:binding)"
    ), path, binding_key


def _active_insert(path: str | None, binding_key: str):
    return text(
        "INSERT INTO company_report_presentation_pins "
        "(subject_id,report_id,presentation_contract,generation,snapshot_hash,chart_facts_version,"
        "chart_facts_hash,evidence_registry_version,publication_policy_version,projection_scope,"
        "canonical_path,indexable,published_lastmod,projection_digest,narrative_binding_status,"
        "narrative_binding_kind,narrative_binding_key) VALUES (:subject,:report,'company_public_h2_v1',"
        "3,:hash,'chart_facts_v2',:chart,'evidence_registry_v1','company_public_h2_publication_v3',"
        "'active_publication',:path,true,now(),:digest,'resolved','fallback',:binding)"
    ), path, binding_key


def _pin_params(subject_id, report_id, *, path, binding_key=None, digest="c" * 64):
    return {
        "subject": subject_id,
        "report": report_id,
        "hash": "a" * 64,
        "chart": "b" * 64,
        "path": path,
        "digest": digest,
        "binding": binding_key,
    }


async def _assert_rejected(connection, statement, parameters) -> None:
    with pytest.raises(IntegrityError):
        async with connection.begin_nested():
            await connection.execute(statement, parameters)


async def _assert_new_h2_lifecycle_guard(url: str):
    engine = create_async_engine(url)
    subject_id, report_id = uuid4(), uuid4()
    v2_path = "/company/ooo-romashka-7707079463"
    legacy_mismatch = "/company/7707079463-other"
    try:
        async with engine.begin() as connection:
            await _insert_h2_report(connection, subject_id=subject_id, report_id=report_id)
            binding_key = await _insert_fallback_artifact(connection, report_id=report_id)
            unresolved, _ = _unresolved_insert(None)
            await _assert_rejected(connection, unresolved, _pin_params(subject_id, report_id, path=None))
            wrong_subject, _ = _unresolved_insert("/company/ooo-romashka-7707079464")
            await _assert_rejected(connection, wrong_subject, _pin_params(subject_id, report_id, path="/company/ooo-romashka-7707079464"))
            unresolved, _ = _unresolved_insert(v2_path)
            await connection.execute(unresolved, _pin_params(subject_id, report_id, path=v2_path))

            resolved_null, _, _ = _resolved_insert(None, binding_key)
            await _assert_rejected(connection, resolved_null, _pin_params(subject_id, report_id, path=None, binding_key=binding_key))
            resolved_mismatch, _, _ = _resolved_insert(legacy_mismatch, binding_key)
            await _assert_rejected(connection, resolved_mismatch, _pin_params(subject_id, report_id, path=legacy_mismatch, binding_key=binding_key))
            resolved, _, _ = _resolved_insert(v2_path, binding_key)
            await connection.execute(resolved, _pin_params(subject_id, report_id, path=v2_path, binding_key=binding_key))
            await connection.execute(text(
                "INSERT INTO company_report_presentation_staged_pointers "
                "(id,subject_id,presentation_contract,generation) "
                "VALUES (:id,:subject,'company_public_h2_v1',2)"
            ), {"id": uuid4(), "subject": subject_id})

            active_null, _, _ = _active_insert(None, binding_key)
            await _assert_rejected(connection, active_null, _pin_params(subject_id, report_id, path=None, binding_key=binding_key, digest="f" * 64))
            active_mismatch, _, _ = _active_insert(legacy_mismatch, binding_key)
            await _assert_rejected(connection, active_mismatch, _pin_params(subject_id, report_id, path=legacy_mismatch, binding_key=binding_key, digest="f" * 64))
            active, _, _ = _active_insert(v2_path, binding_key)
            await connection.execute(active, _pin_params(subject_id, report_id, path=v2_path, binding_key=binding_key, digest="f" * 64))

            return tuple((await connection.execute(text(
                "SELECT generation,canonical_path,projection_scope,narrative_binding_status "
                "FROM company_report_presentation_pins WHERE subject_id=:subject ORDER BY generation"
            ), {"subject": subject_id})).all())
    finally:
        await engine.dispose()


async def _continue_historical_null_lifecycle(url: str, historical):
    subject_id, report_id, _ = historical
    fallback = "/company/7707079463-company"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            binding_key = await _insert_fallback_artifact(connection, report_id=report_id)
            resolved, _, _ = _resolved_insert(fallback, binding_key)
            await connection.execute(resolved, _pin_params(subject_id, report_id, path=fallback, binding_key=binding_key))
            await connection.execute(text(
                "INSERT INTO company_report_presentation_staged_pointers "
                "(id,subject_id,presentation_contract,generation) "
                "VALUES (:id,:subject,'company_public_h2_v1',2)"
            ), {"id": uuid4(), "subject": subject_id})
            active, _, _ = _active_insert(fallback, binding_key)
            await connection.execute(active, _pin_params(subject_id, report_id, path=fallback, binding_key=binding_key, digest="f" * 64))
            return tuple((await connection.execute(text(
                "SELECT canonical_path FROM company_report_presentation_pins "
                "WHERE subject_id=:subject ORDER BY generation"
            ), {"subject": subject_id})).scalars())
    finally:
        await engine.dispose()


async def _insert_new_h2_unresolved(url: str, path: str) -> None:
    engine = create_async_engine(url)
    subject_id, report_id = uuid4(), uuid4()
    try:
        async with engine.begin() as connection:
            await _insert_h2_report(connection, subject_id=subject_id, report_id=report_id)
            statement, _ = _unresolved_insert(path)
            await connection.execute(statement, _pin_params(subject_id, report_id, path=path))
    finally:
        await engine.dispose()


async def _insert_v2_publication(url: str) -> None:
    engine = create_async_engine(url)
    subject_id, report_id, batch_id, publication_id = (uuid4() for _ in range(4))
    try:
        async with engine.begin() as connection:
            await connection.execute(text(
                "INSERT INTO company_report_subjects (id,normalized_identifier,identifier_type) "
                "VALUES (:id,'7707079463','legal_entity_inn')"
            ), {"id": subject_id})
            await connection.execute(text(
                "INSERT INTO company_reports "
                "(id,subject_id,report_version,lifecycle_status,started_at,generated_at,finished_at,"
                "normalized_snapshot,snapshot_hash,warnings_snapshot,usable_for_public_page,usable_for_future_scoring) "
                "VALUES (:id,:subject,'2','complete',now(),now(),now(),"
                "CAST(:snapshot AS json),:hash,CAST(:warnings AS json),true,true)"
            ), {"id": report_id, "subject": subject_id, "snapshot": "{}", "hash": "a" * 64, "warnings": "[]"})
            generation = await connection.scalar(text(
                "INSERT INTO company_report_publication_batches "
                "(id,state,requested_limit,candidate_count,next_ordinal,policy_version,completed_at) "
                "VALUES (:id,'completed',1,0,0,'publication_sufficiency_v1',now()) RETURNING generation"
            ), {"id": batch_id})
            await connection.execute(text(
                "INSERT INTO company_report_publications "
                "(id,subject_id,report_id,status,canonical_slug,canonical_path,snapshot_hash,policy_version,"
                "batch_generation,indexable,sufficiency_status,published_lastmod) "
                "VALUES (:id,:subject,:report,'active','romashka','/company/ooo-romashka-7707079463',:hash,"
                "'publication_sufficiency_v1',:generation,true,'sufficient',now())"
            ), {"id": publication_id, "subject": subject_id, "report": report_id, "hash": "a" * 64, "generation": generation})
    finally:
        await engine.dispose()


async def _version(url: str) -> str:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()


def _validated_admin_url(value: str):
    parsed = make_url(value)
    if parsed.get_backend_name() != "postgresql" or (parsed.host or "").lower() not in {"localhost", "127.0.0.1", "::1", "postgres"} or (parsed.database or "").lower() != "postgres":
        raise ValueError("TEST_POSTGRES_ADMIN_URL must name the disposable local postgres database")
    return parsed.set(drivername="postgresql+asyncpg") if parsed.drivername == "postgresql" else parsed


def _config(target_url: str) -> Config:
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", target_url.replace("%", "%%"))
    return config


async def _create_database(admin_url: str, name: str) -> None:
    _validate_name(name)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await engine.dispose()


async def _drop_database(admin_url: str, name: str) -> None:
    _validate_name(name)
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name AND pid<>pg_backend_pid()"), {"name": name})
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    finally:
        await engine.dispose()


def _validate_name(value: str) -> None:
    if not value.startswith(_PREFIX) or len(value.removeprefix(_PREFIX)) != 32:
        raise ValueError("refusing to mutate a database not generated by this test")
