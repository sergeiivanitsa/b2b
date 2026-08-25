"""Integration contract for canonical H1/H2 document selection.

Detailed persistence selection lives in unit tests; this suite proves the
public endpoint remains read-only and fails closed when H2 is unavailable.
"""
from __future__ import annotations

import json
import pytest
import importlib.util
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeJob,
    CompanyReportPresentationAssignment,
    CompanyReportPresentationPin,
    CompanyReportPublication,
    CompanyReportPublicationBatch,
    CompanyReportRecord,
    CompanyReportSubject,
    PUBLICATION_POLICY_VERSION,
)
from product_api.company_reports.public_h1 import render_public_h1_html
from product_api.company_reports.public_h1_service import (
    resolve_public_h1,
    validate_assigned_public_h1,
)
from product_api.company_reports.company_card_v2.public_h2_asset_manifest import load_public_h2_asset_manifest
from product_api.routers.company_reports_public import set_public_h2_asset_manifest
from product_api.routers import company_reports as generic_routes

_HELPER_SPEC = importlib.util.spec_from_file_location(
    "iteration22_h2_read_helpers", Path(__file__).with_name("test_company_report_public_h2_reads.py")
)
assert _HELPER_SPEC and _HELPER_SPEC.loader
_helpers = importlib.util.module_from_spec(_HELPER_SPEC)
sys.modules[_HELPER_SPEC.name] = _helpers
_HELPER_SPEC.loader.exec_module(_helpers)
_store_legacy_report = _helpers._store_legacy_report
_store_resolved_v3_fallback = _helpers._store_resolved_v3_fallback


pytestmark = pytest.mark.asyncio


async def test_canonical_public_document_is_not_a_writer(async_client) -> None:
    response = await async_client.get("/company/7701234567-company")
    # An empty disposable database has no public H1 record.  The important
    # property is a read-only, controlled not-found response, never creation.
    assert response.status_code == 404
    assert response.headers.get("cache-control") == "no-store"


async def test_canonical_public_document_head_is_bodyless(async_client) -> None:
    response = await async_client.head("/company/7701234567-company")
    assert response.status_code == 404
    assert response.content == b""


async def _table_counts(engine) -> dict[str, int]:
    """Snapshot every Product table so a hidden endpoint write is observable."""
    from product_api.db.base import Base
    async with AsyncSession(bind=engine) as session:
        tables = [Base.metadata.tables[name] for name in sorted(Base.metadata.tables)]
        return {
            table.name: int(await session.scalar(select(func.count()).select_from(table)))
            for table in tables
        }


def _stable_db_value(value):
    if isinstance(value, dict):
        return {str(key): _stable_db_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_stable_db_value(item) for item in value]
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


async def _database_row_bytes(engine) -> bytes:
    """Byte-stable snapshot of every persisted Product row, including UPDATEs."""
    from product_api.db.base import Base
    result: dict[str, list[dict[str, object]]] = {}
    async with AsyncSession(bind=engine) as session:
        for name in sorted(Base.metadata.tables):
            table = Base.metadata.tables[name]
            rows = [
                {column.name: _stable_db_value(row._mapping[column]) for column in table.columns}
                for row in (await session.execute(select(table))).all()
            ]
            result[name] = sorted(rows, key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


async def _observe_read_only_request(async_client, engine, method: str, path: str):
    before_counts = await _table_counts(engine)
    before_rows = await _database_row_bytes(engine)
    statements: list[str] = []

    def capture(*args):
        statements.append(args[2])

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        response = await async_client.request(method, path)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert statements
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert await _table_counts(engine) == before_counts
    assert await _database_row_bytes(engine) == before_rows
    return response, statements


def _assert_safe_error(response, status_code: int) -> None:
    assert response.status_code == status_code
    assert response.headers["x-robots-tag"] == "noindex,follow"
    assert "company-public-h2-root" not in response.text
    assert "company-public-h2-state" not in response.text
    assert "/assets/company-public-h2." not in response.text
    assert "00000000-0000-4000-8000-000000000001" not in response.text


def _touched_product_tables(statements: list[str]) -> set[str]:
    from product_api.db.base import Base
    lowered = "\n".join(statements).lower()
    return {name for name in Base.metadata.tables if name.lower() in lowered}


async def _activate_h1(session, subject, record, canonical_path: str) -> None:
    batch = CompanyReportPublicationBatch(
        state="completed", requested_limit=1, candidate_count=1,
        next_ordinal=1, claimed_ordinal=0,
        policy_version=PUBLICATION_POLICY_VERSION, completed_at=record.generated_at,
    )
    session.add(batch); await session.flush()
    session.add(CompanyReportPublication(
        subject_id=subject.id, report_id=record.id, status="active",
        canonical_slug=canonical_path.rsplit("-", 1)[1], canonical_path=canonical_path,
        snapshot_hash=record.snapshot_hash, policy_version=PUBLICATION_POLICY_VERSION,
        batch_generation=batch.generation, indexable=True,
        sufficiency_status="sufficient", published_lastmod=record.generated_at,
        published_at=record.generated_at,
    ))


async def test_real_assigned_h1_get_and_head_are_read_only_and_use_exact_pin(async_client, engine) -> None:
    old_id, _ = await _store_legacy_report(
        engine, generated_at="2026-08-24T12:00:00Z", with_fallback=False,
    )
    newest_id, _ = await _store_legacy_report(
        engine,
        report_id="00000000-0000-4000-8000-000000000002",
        generated_at="2026-08-25T12:00:00Z",
        with_fallback=False,
    )
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        latest = await resolve_public_h1(session, inn="7701234567")
        assert str(latest.report_id) == str(newest_id)
        subject = await session.scalar(select(CompanyReportSubject).where(CompanyReportSubject.normalized_identifier == "7701234567"))
        newest = await session.get(CompanyReportRecord, newest_id)
        # Active H1 would select the newer report, while the canonical route
        # must use the immutable older assignment below.
        await _activate_h1(session, subject, newest, latest.canonical_path)
        record = await session.get(CompanyReportRecord, old_id)
        pin = CompanyReportPresentationPin(subject_id=subject.id, report_id=record.id, presentation_contract="company_public_h1_v1", generation=1, snapshot_hash=record.snapshot_hash, chart_facts_version=None, chart_facts_hash=None, evidence_registry_version=None, publication_policy_version=PUBLICATION_POLICY_VERSION, canonical_path=latest.canonical_path, indexable=True, published_lastmod=record.generated_at, projection_digest=None, narrative_binding_status=None, narrative_binding_kind=None, narrative_binding_key=None)
        session.add(pin); await session.flush()
        assignment = CompanyReportPresentationAssignment(subject_id=subject.id, presentation_contract="company_public_h1_v1", pin_generation=1, generation=1)
        session.add(assignment); await session.commit()
        active = await resolve_public_h1(session, inn="7701234567")
        assert str(active.report_id) == str(newest_id)
        expected_html = render_public_h1_html(
            validate_assigned_public_h1(subject, assignment, pin, record)
        ).encode("utf-8")
    for method in ("GET", "HEAD"):
        response, sql = await _observe_read_only_request(
            async_client, engine, method, latest.canonical_path
        )
        assert response.status_code == 200
        assert response.headers["x-robots-tag"] == "index,follow"
        assert len(sql) == 1
        assert sum("company_report_presentation_assignments" in statement for statement in sql) == 1
        if method == "GET":
            assert str(old_id) in response.text and str(newest_id) not in response.text
            # Byte-exact baseline: the route rendered the immutable old pin,
            # not the active/latest resolver result selected above.
            assert response.content == expected_html
        else:
            assert response.content == b""


async def _assigned_h2(engine):
    report_id, _ = await _store_resolved_v3_fallback(engine)
    set_public_h2_asset_manifest(load_public_h2_asset_manifest())
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = await session.scalar(select(CompanyReportSubject).where(CompanyReportSubject.normalized_identifier == "7701234567"))
        pin = await session.scalar(select(CompanyReportPresentationPin).where(CompanyReportPresentationPin.report_id == report_id))
        session.add(CompanyReportPresentationAssignment(subject_id=subject.id, presentation_contract="company_public_h2_v1", pin_generation=pin.generation, generation=1)); await session.commit()


async def _assign_h1_for_existing_subject(engine, report_id):
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        latest = await resolve_public_h1(session, inn="7701234567")
        subject = await session.scalar(select(CompanyReportSubject).where(CompanyReportSubject.normalized_identifier == "7701234567"))
        record = await session.get(CompanyReportRecord, report_id)
        session.add(CompanyReportPresentationPin(subject_id=subject.id, report_id=record.id, presentation_contract="company_public_h1_v1", generation=1, snapshot_hash=record.snapshot_hash, chart_facts_version=None, chart_facts_hash=None, evidence_registry_version=None, publication_policy_version=PUBLICATION_POLICY_VERSION, canonical_path=latest.canonical_path, indexable=True, published_lastmod=record.generated_at, projection_digest=None, narrative_binding_status=None, narrative_binding_kind=None, narrative_binding_key=None)); await session.flush()
        session.add(CompanyReportPresentationAssignment(subject_id=subject.id, presentation_contract="company_public_h1_v1", pin_generation=1, generation=1)); await session.commit()
    return latest.canonical_path


async def test_real_assigned_h2_get_and_head_are_noindex_and_read_only(async_client, engine) -> None:
    await _assigned_h2(engine)
    approved_tables = {
        "company_report_subjects", "company_report_presentation_assignments",
        "company_report_presentation_pins", "company_reports",
        "company_report_presentations", "company_card_narrative_jobs",
        "company_card_narrative_artifacts",
    }
    for method in ("GET", "HEAD"):
        response, sql = await _observe_read_only_request(
            async_client, engine, method, "/company/7701234567-company"
        )
        assert response.status_code == 200
        assert response.headers["x-robots-tag"] == "noindex,follow"
        assert sum("company_report_presentation_assignments" in statement for statement in sql) == 1
        assert _touched_product_tables(sql) <= approved_tables
        if method == "GET":
            assert "company-public-h2-root" in response.text
            assert f'data-report-id="00000000-0000-4000-8000-000000000001"' in response.text
            assert '<code data-h2-field="report_id">00000000-0000-4000-8000-000000000001</code>' in response.text
            hrefs = re.findall(r'<a\b[^>]*\bhref="([^"]+)"', response.text)
            claim_hrefs = [href for href in hrefs if href.startswith("/claims?report_id=")]
            assert claim_hrefs == [
                "/claims?report_id=00000000-0000-4000-8000-000000000001",
                "/claims?report_id=00000000-0000-4000-8000-000000000001",
            ]
        else:
            assert response.content == b""
    counts = await _table_counts(engine)
    assert counts["company_report_presentation_assignments"] == 1
    assert counts["company_report_presentation_assignment_journal"] == 0


async def test_real_exact_assigned_old_digest_h2_returns_safe_500_without_h1_fallback(async_client, engine) -> None:
    report_id, _ = await _store_resolved_v3_fallback(engine)
    set_public_h2_asset_manifest(load_public_h2_asset_manifest())
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = await session.scalar(select(CompanyReportSubject).where(CompanyReportSubject.normalized_identifier == "7701234567"))
        pin = await session.scalar(select(CompanyReportPresentationPin).where(CompanyReportPresentationPin.report_id == report_id)); pin.projection_digest = "f" * 64; await session.commit()
        session.add(CompanyReportPresentationAssignment(subject_id=subject.id, presentation_contract="company_public_h2_v1", pin_generation=pin.generation, generation=1)); await session.commit()
    stale, sql = await _observe_read_only_request(
        async_client, engine, "GET", "/company/7701234567-company"
    )
    _assert_safe_error(stale, 500)
    assert sum("company_report_presentation_assignments" in statement for statement in sql) == 1


async def test_unassigned_staged_old_digest_h2_leaves_latest_h1_canonical(async_client, engine) -> None:
    h2_id, _ = await _store_resolved_v3_fallback(engine)
    h1_id, _ = await _store_legacy_report(engine, report_id="00000000-0000-4000-8000-000000000002", generated_at="2026-08-25T12:00:00Z", with_fallback=False)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        pin = await session.scalar(select(CompanyReportPresentationPin).where(CompanyReportPresentationPin.report_id == h2_id)); pin.projection_digest = "e" * 64; await session.commit()
        expected = await resolve_public_h1(session, inn="7701234567")
        assert str(expected.report_id) == str(h1_id)
        subject = await session.scalar(select(CompanyReportSubject).where(CompanyReportSubject.normalized_identifier == "7701234567"))
        record = await session.get(CompanyReportRecord, h1_id)
        await _activate_h1(session, subject, record, expected.canonical_path)
        await session.commit()
    assert (await _table_counts(engine))["company_report_presentation_assignments"] == 0
    response, sql = await _observe_read_only_request(
        async_client, engine, "GET", expected.canonical_path
    )
    assert response.status_code == 200 and response.headers["x-robots-tag"] == "index,follow"
    assert str(h1_id) in response.text and str(h2_id) not in response.text
    assert sum("company_report_presentation_assignments" in statement for statement in sql) == 1


async def test_generic_staged_old_digest_h2_returns_500_with_route_session_override(async_client, engine, monkeypatch) -> None:
    report_id, _ = await _store_resolved_v3_fallback(engine)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        pin = await session.scalar(select(CompanyReportPresentationPin).where(CompanyReportPresentationPin.report_id == report_id)); pin.projection_digest = "d" * 64; await session.commit()
    async def override_session():
        async with AsyncSession(bind=engine, expire_on_commit=False) as session: yield session
    monkeypatch.setattr(generic_routes, "h2_cohort_selected", lambda **_kwargs: True)
    monkeypatch.setattr(generic_routes, "get_session", override_session)
    response, sql = await _observe_read_only_request(
        async_client, engine, "GET", "/company-reports/7701234567/public-h2"
    )
    assert response.status_code == 500 and response.json()["detail"]["code"] == "public_projection_invalid"
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in sql)


async def test_real_corrupt_assigned_h1_returns_safe_500_without_fallback(async_client, engine) -> None:
    report_id, _ = await _store_legacy_report(engine, with_fallback=False)
    path = await _assign_h1_for_existing_subject(engine, report_id)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        record = await session.get(CompanyReportRecord, report_id)
        record.snapshot_hash = "a" * 64
        await session.commit()
    response, sql = await _observe_read_only_request(async_client, engine, "GET", path)
    _assert_safe_error(response, 500)
    assert sum("company_report_presentation_assignments" in statement for statement in sql) == 1


async def test_real_non_digest_corrupt_assigned_h2_returns_safe_500_without_fallback(async_client, engine) -> None:
    await _assigned_h2(engine)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        job = await session.scalar(select(CompanyCardNarrativeJob))
        job.generation_identity = {**job.generation_identity, "prompt_version": "corrupt"}
        await session.commit()
    response, sql = await _observe_read_only_request(
        async_client, engine, "GET", "/company/7701234567-company"
    )
    _assert_safe_error(response, 500)
    assert sum("company_report_presentation_assignments" in statement for statement in sql) == 1


@pytest.mark.parametrize(
    "outcome",
    ("pending", "failed", "unresolved"),
)
async def test_real_exact_h2_nonready_outcomes_are_safe_409(
    async_client, engine, outcome: str,
) -> None:
    report_id, _ = await _store_resolved_v3_fallback(engine)
    set_public_h2_asset_manifest(load_public_h2_asset_manifest())
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = await session.scalar(select(CompanyReportSubject).where(
            CompanyReportSubject.normalized_identifier == "7701234567"
        ))
        pin = await session.scalar(select(CompanyReportPresentationPin).where(
            CompanyReportPresentationPin.report_id == report_id
        ))
        if outcome in {"pending", "failed"}:
            record = await session.get(CompanyReportRecord, report_id)
            record.lifecycle_status = outcome
        else:
            pin.narrative_binding_status = "unresolved"
            pin.narrative_binding_kind = None
            pin.narrative_binding_key = None
            pin.projection_digest = None
        session.add(CompanyReportPresentationAssignment(
            subject_id=subject.id,
            presentation_contract="company_public_h2_v1",
            pin_generation=pin.generation,
            generation=1,
        ))
        await session.commit()
    response, sql = await _observe_read_only_request(
        async_client, engine, "GET", "/company/7701234567-company"
    )
    _assert_safe_error(response, 409)
    assert sum("company_report_presentation_assignments" in statement for statement in sql) == 1


async def test_real_exact_h2_sqlalchemy_failure_is_safe_503(async_client, engine) -> None:
    await _assigned_h2(engine)
    before_counts = await _table_counts(engine)
    before_rows = await _database_row_bytes(engine)
    statements: list[str] = []
    injected = False

    def fail_presentation_read(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal injected
        statements.append(statement)
        lowered = statement.lower()
        if not injected and "from company_report_presentations" in lowered:
            injected = True
            raise OperationalError(statement, {}, RuntimeError("injected unavailable storage"))

    event.listen(engine.sync_engine, "before_cursor_execute", fail_presentation_read)
    try:
        response = await async_client.get("/company/7701234567-company")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", fail_presentation_read)
    _assert_safe_error(response, 503)
    assert injected
    assert sum("company_report_presentation_assignments" in statement for statement in statements) == 1
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert await _table_counts(engine) == before_counts
    assert await _database_row_bytes(engine) == before_rows
