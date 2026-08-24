from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

TESTS_UNIT = Path(__file__).resolve().parents[1] / "tests_unit"
if str(TESTS_UNIT) not in sys.path:
    sys.path.append(str(TESTS_UNIT))

from company_report_public_h1_side_effect_test_helpers import (
    SelectOnlySession,
    assert_zero_side_effects,
    install_capability_guards,
)
from company_report_signal_test_helpers import complete_company_report, counterparty_facts
from product_api.company_reports.persistence.models import (
    PUBLICATION_POLICY_VERSION,
    CompanyReportPublication,
    CompanyReportPublicationBatch,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
    company_report_to_snapshot,
)
from product_api.company_reports.persistence.public_h1 import get_publication_resolution_record
from product_api.company_reports.persistence.repository import (
    get_latest_report_by_identifier,
    get_latest_run_status_by_identifier,
)
from product_api.company_reports.seo import canonical_path
from product_api.db.session import get_session
from product_api.main import app

pytestmark = pytest.mark.asyncio


async def _seed_public_h1(
    engine,
    *,
    publication: bool,
    report_version: str = "2",
    corrupt: bool = False,
):
    now = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    inn = "0000000000"
    name = "ООО Публичная матрица"
    report = complete_company_report(
        counterparty=counterparty_facts().model_copy(
            update={"inn": inn, "full_name": name, "short_name": name}
        ),
        report_version=report_version,
    ).model_copy(
        update={"report_id": uuid4(), "generated_at": now, "target_identifier": inn}
    )
    snapshot = company_report_to_snapshot(report)
    digest = calculate_company_report_snapshot_hash(snapshot)
    path = canonical_path(inn, name)
    assert path is not None

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = CompanyReportSubject(
            normalized_identifier=inn,
            identifier_type="legal_entity_inn",
        )
        session.add(subject)
        await session.flush()
        record = CompanyReportRecord(
            id=report.report_id,
            subject_id=subject.id,
            report_version=report.report_version,
            lifecycle_status="complete",
            started_at=now,
            generated_at=now,
            finished_at=now,
            normalized_snapshot=snapshot,
            snapshot_hash=digest,
            completeness_snapshot={},
            freshness_snapshot={},
            warnings_snapshot=[],
            usable_for_public_page=True,
            usable_for_future_scoring=True,
            created_at=now,
        )
        session.add(record)
        if publication:
            batch = CompanyReportPublicationBatch(
                state="completed",
                requested_limit=1,
                candidate_count=1,
                next_ordinal=1,
                claimed_ordinal=0,
                policy_version=PUBLICATION_POLICY_VERSION,
                completed_at=now,
            )
            session.add(batch)
            await session.flush()
            session.add(
                CompanyReportPublication(
                    subject_id=subject.id,
                    report_id=record.id,
                    status="active",
                    canonical_slug=path[len(f"/company/{inn}-"):],
                    canonical_path=path,
                    snapshot_hash="0" * 64 if corrupt else digest,
                    policy_version=PUBLICATION_POLICY_VERSION,
                    batch_generation=batch.generation,
                    indexable=True,
                    sufficiency_status="sufficient",
                    published_lastmod=now,
                    published_at=now,
                )
            )
        await session.commit()
    return inn, path


@asynccontextmanager
async def _guarded_client(engine):
    async with AsyncSession(bind=engine, expire_on_commit=False) as raw_session:
        guarded = SelectOnlySession(raw_session)

        async def override_session():
            yield guarded

        app.dependency_overrides[get_session] = override_session
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                yield client, guarded
        finally:
            app.dependency_overrides.pop(get_session, None)


@pytest.mark.parametrize(
    (
        "scenario",
        "path",
        "seed",
        "report_version",
        "expected_status",
        "expected_selects",
    ),
    [
        ("active_v1", "/company-reports/0000000000/public-h1", "active", "1", 200, 1),
        ("active_v2", "/company-reports/0000000000/public-h1", "active", "2", 200, 1),
        ("fallback_v1", "/company-reports/0000000000/public-h1", "fallback", "1", 200, 2),
        ("fallback_v2", "/company-reports/0000000000/public-h1", "fallback", "2", 200, 2),
        ("invalid", "/company-reports/not-an-inn/public-h1", None, None, 400, 0),
        ("query", "/company-reports/0000000000/public-h1?x=1", None, None, 422, 0),
    ],
)
async def test_api_exact_select_ceiling_and_complete_zero_side_effect_matrix(
    engine,
    monkeypatch,
    scenario,
    path,
    seed,
    report_version,
    expected_status,
    expected_selects,
):
    if seed is not None:
        await _seed_public_h1(
            engine,
            publication=seed == "active",
            report_version=report_version,
        )
    counters = install_capability_guards(monkeypatch)
    async with _guarded_client(engine) as (client, guarded):
        response = await client.get(path)
    assert response.status_code == expected_status, scenario
    if expected_status == 200:
        assert response.json()["report_version"] == report_version
    assert_zero_side_effects(guarded, counters, expected_selects=expected_selects)


@pytest.mark.parametrize(
    ("scenario", "requested_path", "seed", "expected_status", "expected_selects"),
    [
        ("active", None, "active", 200, 1),
        ("wrong_slug", "/company/0000000000-wrong-slug", "active", 301, 1),
        ("corrupt_active", None, "corrupt", 500, 1),
        ("fallback_unpublished", "/company/0000000000-any-slug", "fallback", 404, 2),
        ("invalid_key", "/company/invalid-key", None, 404, 0),
        ("query", "/company/0000000000-any-slug?x=1", None, 404, 0),
    ],
)
async def test_ssr_exact_select_ceiling_and_complete_zero_side_effect_matrix(
    engine,
    monkeypatch,
    scenario,
    requested_path,
    seed,
    expected_status,
    expected_selects,
):
    canonical = None
    if seed is not None:
        _, canonical = await _seed_public_h1(
            engine,
            publication=seed in {"active", "corrupt"},
            corrupt=seed == "corrupt",
        )
    path = requested_path or canonical
    assert path is not None
    counters = install_capability_guards(monkeypatch)
    async with _guarded_client(engine) as (client, guarded):
        response = await client.get(path, follow_redirects=False)
    assert response.status_code == expected_status, scenario
    assert_zero_side_effects(guarded, counters, expected_selects=expected_selects)


@pytest.mark.parametrize(
    ("scenario", "path", "seed_active", "expected_status", "expected_selects"),
    [
        ("index", "/sitemaps/index.xml", True, 200, 1),
        ("chunk", "/sitemaps/1.xml", True, 200, 1),
        ("index_query", "/sitemaps/index.xml?x=1", False, 404, 0),
        ("chunk_query", "/sitemaps/1.xml?x=1", False, 404, 0),
        ("malformed_zero", "/sitemaps/0.xml", False, 404, 0),
        ("malformed_leading_zero", "/sitemaps/01.xml", False, 404, 0),
    ],
)
async def test_sitemap_exact_select_ceiling_and_complete_zero_side_effect_matrix(
    engine,
    monkeypatch,
    scenario,
    path,
    seed_active,
    expected_status,
    expected_selects,
):
    if seed_active:
        await _seed_public_h1(engine, publication=True)
    counters = install_capability_guards(monkeypatch)
    async with _guarded_client(engine) as (client, guarded):
        response = await client.get(path)
    assert response.status_code == expected_status, scenario
    assert_zero_side_effects(guarded, counters, expected_selects=expected_selects)


@pytest.mark.parametrize("v3_status", ("pending", "failed", "complete"))
async def test_actual_db_h1_order_and_public_terminal_ignore_v3_shadow(engine, v3_status: str) -> None:
    """H2 rows may exist physically, but cannot shadow H1 reads or an H1 pin."""
    inn, _ = await _seed_public_h1(engine, publication=True)
    now = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    # UUID ordering is part of the public H1 contract; use the maximum value
    # and deliberately give it an earlier created_at.
    highest_h1_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = await session.scalar(select(CompanyReportSubject).where(CompanyReportSubject.normalized_identifier == inn))
        assert subject is not None
        report = complete_company_report(
            counterparty=counterparty_facts().model_copy(update={"inn": inn, "full_name": "ООО Порядок", "short_name": "ООО Порядок"}),
        ).model_copy(update={"report_id": highest_h1_id, "target_identifier": inn, "generated_at": now})
        snapshot = company_report_to_snapshot(report)
        high_h1 = CompanyReportRecord(
            id=highest_h1_id, subject_id=subject.id, report_version="2", lifecycle_status="complete",
            started_at=now, generated_at=now, finished_at=now, created_at=now.replace(year=2025),
            normalized_snapshot=snapshot, snapshot_hash=calculate_company_report_snapshot_hash(snapshot),
            completeness_snapshot={}, freshness_snapshot={}, warnings_snapshot=[],
            usable_for_public_page=True, usable_for_future_scoring=False,
        )
        v3 = CompanyReportRecord(
            id=uuid4(), subject_id=subject.id, report_version="3", lifecycle_status=v3_status,
            writer_profile="company_card_v2_writer_v3", presentation_contract="company_public_h2_v1",
            rollout_generation=1, started_at=now.replace(year=2027),
            generated_at=now.replace(year=2027) if v3_status == "complete" else None,
            finished_at=now.replace(year=2027) if v3_status in {"failed", "complete"} else None,
            normalized_snapshot={"report_version": "3"} if v3_status == "complete" else None,
            snapshot_hash="a" * 64 if v3_status == "complete" else None,
            completeness_snapshot={} if v3_status == "complete" else None,
            freshness_snapshot={} if v3_status == "complete" else None,
            safe_error_snapshot={"code": "test"} if v3_status == "failed" else None, warnings_snapshot=[],
            usable_for_public_page=False, usable_for_future_scoring=False,
        )
        session.add_all((high_h1, v3)); await session.flush()
        publication = await session.scalar(select(CompanyReportPublication).where(CompanyReportPublication.subject_id == subject.id))
        assert publication is not None
        # This represents corrupt historical linkage.  The public-H1 query
        # must expose it as terminal rather than treating v3 as a H1 report.
        publication.report_id = v3.id
        await session.commit()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        latest = await get_latest_report_by_identifier(session, inn)
        status = await get_latest_run_status_by_identifier(session, inn)
        pinned = await get_publication_resolution_record(session, inn)
    assert latest is not None and latest.report_id == highest_h1_id
    assert status is not None and status.report_id == highest_h1_id
    assert pinned is not None and pinned.report is None
