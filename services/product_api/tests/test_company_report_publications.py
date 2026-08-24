from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

TESTS_UNIT = Path(__file__).resolve().parents[1] / "tests_unit"
if str(TESTS_UNIT) not in sys.path:
    sys.path.append(str(TESTS_UNIT))

from company_report_signal_test_helpers import complete_company_report, counterparty_facts
from product_api.company_reports.persistence.models import (
    PUBLICATION_POLICY_VERSION,
    CompanyReportPublication,
    CompanyReportPublicationBatch,
    CompanyReportPublicationBatchItem,
    CompanyReportPublicationControl,
    CompanyReportPublicationJournal,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence import publications
from product_api.company_reports.persistence.publications import (
    PublicationBatchClaim,
    PublicationStateConflictError,
    claim_next_batch_item,
    create_batch,
    finalize_batch_claim,
    process_batch,
    relinquish_batch_claim,
    set_batch_state,
    set_publication_control,
)
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
    company_report_to_snapshot,
)

pytestmark = pytest.mark.asyncio


async def _require_publication_tables(engine) -> None:
    async with engine.connect() as connection:
        exists = await connection.scalar(
            text("SELECT to_regclass('company_report_publications')")
        )
    if exists is None:
        pytest.skip("company_report_publications migration is not applied")


async def _store_eligible_report(
    engine,
    *,
    subject_id: UUID | None = None,
    created_at: datetime | None = None,
    inn: str = "0000000000",
) -> tuple[UUID, UUID]:
    """Persist a real allowlisted finalized snapshot for publication tests."""
    now = created_at or datetime.now(timezone.utc)
    counterparty = counterparty_facts().model_copy(
        update={"inn": inn, "full_name": f"ООО Тест и партнёры {inn}"}
    )
    report = complete_company_report(
        counterparty=counterparty,
        report_version="2",
    ).model_copy(
        update={"report_id": uuid4(), "generated_at": now, "target_identifier": inn}
    )
    snapshot = company_report_to_snapshot(report)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        if subject_id is None:
            subject = CompanyReportSubject(
                normalized_identifier=inn, identifier_type="legal_entity"
            )
            session.add(subject)
            await session.flush()
            subject_id = subject.id
        record = CompanyReportRecord(
            id=report.report_id,
            subject_id=subject_id,
            report_version=report.report_version,
            lifecycle_status="complete",
            started_at=now,
            generated_at=now,
            finished_at=now,
            normalized_snapshot=snapshot,
            snapshot_hash=calculate_company_report_snapshot_hash(snapshot),
            completeness_snapshot={},
            freshness_snapshot={},
            warnings_snapshot=[],
            usable_for_public_page=True,
            usable_for_future_scoring=True,
            created_at=now,
        )
        session.add(record)
        await session.commit()
        return subject_id, record.id


async def _activate_control(engine) -> None:
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await set_publication_control(session, state="active", enabled=True)
        await session.commit()


async def _new_batch(engine, *, limit: int = 1) -> UUID:
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        batch = await create_batch(session, limit=limit, max_limit=10)
        await session.commit()
        return batch.id


async def _process_once(engine, batch_id: UUID) -> None:
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await process_batch(session, batch_id=batch_id)
        await session.commit()


_PUBLICATION_SENTINEL_COLUMNS = (
    CompanyReportPublication.id,
    CompanyReportPublication.subject_id,
    CompanyReportPublication.report_id,
    CompanyReportPublication.status,
    CompanyReportPublication.canonical_slug,
    CompanyReportPublication.canonical_path,
    CompanyReportPublication.snapshot_hash,
    CompanyReportPublication.policy_version,
    CompanyReportPublication.batch_generation,
    CompanyReportPublication.indexable,
    CompanyReportPublication.sufficiency_status,
    CompanyReportPublication.published_lastmod,
    CompanyReportPublication.published_at,
    CompanyReportPublication.disabled_at,
    CompanyReportPublication.audited_at,
)


async def _publication_sentinel_rows(session: AsyncSession):
    return (
        await session.execute(
            select(*_PUBLICATION_SENTINEL_COLUMNS).order_by(
                CompanyReportPublication.id
            )
        )
    ).all()


async def test_concurrent_publication_get_or_create_uses_one_subject_row(engine):
    await _require_publication_tables(engine)
    await _store_eligible_report(engine)
    await _activate_control(engine)
    first_batch = await _new_batch(engine)
    second_batch = await _new_batch(engine)
    async with AsyncSession(bind=engine) as session:
        prepared = (await session.execute(select(CompanyReportPublicationBatch.id, CompanyReportPublicationBatch.candidate_count).order_by(CompanyReportPublicationBatch.generation))).all()
        assert prepared == [(first_batch, 1), (second_batch, 1)]

    await asyncio.gather(_process_once(engine, first_batch), _process_once(engine, second_batch))

    async with AsyncSession(bind=engine) as session:
        publications = (await session.execute(select(CompanyReportPublication))).scalars().all()
        items = (await session.execute(select(CompanyReportPublicationBatchItem))).scalars().all()
    assert len(publications) == 1
    assert len(items) == 2
    assert {item.state for item in items} in ({"published"}, {"published", "skipped"})
    assert {item.reason_code for item in items} <= {"sufficient", "superseded_by_newer_batch"}
    async with AsyncSession(bind=engine) as session:
        assert await session.scalar(select(func.count(CompanyReportPublicationJournal.id))) in {1, 2}
        generations = (await session.execute(select(CompanyReportPublicationBatch.generation))).scalars().all()
    assert publications[0].batch_generation == max(generations)


async def test_claim_fencing_rejects_stale_token_and_keeps_current_claim(engine):
    await _require_publication_tables(engine)
    await _store_eligible_report(engine)
    await _activate_control(engine)
    batch_id = await _new_batch(engine)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        stale = await claim_next_batch_item(session, batch_id=batch_id)
        assert stale is not None
        await session.commit()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await relinquish_batch_claim(session, claim=stale)
        await session.commit()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        current = await claim_next_batch_item(session, batch_id=batch_id)
        assert current is not None and current.token != stale.token
        await session.commit()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        with pytest.raises(PublicationStateConflictError, match="no longer current"):
            await finalize_batch_claim(session, claim=stale)
        # The rejected worker did not poison its independent outer transaction.
        assert await session.scalar(text("SELECT 1")) == 1
        await session.commit()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await finalize_batch_claim(session, claim=current)
        await session.commit()
    async with AsyncSession(bind=engine) as session:
        item = await session.scalar(select(CompanyReportPublicationBatchItem).where(CompanyReportPublicationBatchItem.batch_id == batch_id))
        assert item is not None and item.state == "published" and item.claim_token == current.token


async def test_pause_resume_blocks_new_claim_then_processes_same_manifest(engine):
    await _require_publication_tables(engine)
    await _store_eligible_report(engine, inn="0000000000")
    await _store_eligible_report(engine, inn="0000000001")
    await _activate_control(engine)
    batch_id = await _new_batch(engine, limit=2)
    await _process_once(engine, batch_id)
    async with AsyncSession(bind=engine) as session:
        prefix = (await session.execute(select(
            CompanyReportPublicationBatchItem.ordinal,
            CompanyReportPublicationBatchItem.subject_id,
            CompanyReportPublicationBatchItem.report_id,
            CompanyReportPublicationBatchItem.snapshot_hash,
            CompanyReportPublicationBatchItem.policy_version,
            CompanyReportPublicationBatchItem.state,
            CompanyReportPublicationBatchItem.claim_token,
            CompanyReportPublicationBatchItem.finished_at,
        ).where(CompanyReportPublicationBatchItem.batch_id == batch_id).order_by(CompanyReportPublicationBatchItem.ordinal))).all()
        before = await session.get(CompanyReportPublicationBatch, batch_id)
        assert before is not None and before.next_ordinal == 1 and prefix[0].state == "published"
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await set_publication_control(session, state="paused", enabled=True)
        await session.commit()
    await _process_once(engine, batch_id)
    async with AsyncSession(bind=engine) as session:
        paused = await session.get(CompanyReportPublicationBatch, batch_id)
        paused_items = (await session.execute(select(CompanyReportPublicationBatchItem.state).where(CompanyReportPublicationBatchItem.batch_id == batch_id).order_by(CompanyReportPublicationBatchItem.ordinal))).scalars().all()
        assert paused is not None and paused.state == "paused" and paused.next_ordinal == 1
        assert paused_items == ["published", "pending"]
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await set_publication_control(session, state="active", enabled=True)
        await set_batch_state(session, batch_id=batch_id, state="running", enabled=True)
        await session.commit()
    await _process_once(engine, batch_id)
    async with AsyncSession(bind=engine) as session:
        completed = await session.get(CompanyReportPublicationBatch, batch_id)
        after = (await session.execute(select(
            CompanyReportPublicationBatchItem.ordinal,
            CompanyReportPublicationBatchItem.subject_id,
            CompanyReportPublicationBatchItem.report_id,
            CompanyReportPublicationBatchItem.snapshot_hash,
            CompanyReportPublicationBatchItem.policy_version,
            CompanyReportPublicationBatchItem.state,
            CompanyReportPublicationBatchItem.claim_token,
            CompanyReportPublicationBatchItem.finished_at,
        ).where(CompanyReportPublicationBatchItem.batch_id == batch_id).order_by(CompanyReportPublicationBatchItem.ordinal))).all()
        journal_count = await session.scalar(select(func.count(CompanyReportPublicationJournal.id)).where(CompanyReportPublicationJournal.batch_id == batch_id))
        assert completed is not None and completed.state == "completed" and completed.next_ordinal == 2
        assert [item[:5] for item in after] == [item[:5] for item in prefix]
        assert after[0] == prefix[0] and [item.state for item in after] == ["published", "published"]
        assert journal_count == 2


async def test_paused_older_batch_cannot_overwrite_newer_publication(engine):
    await _require_publication_tables(engine)
    subject_id, first_report_id = await _store_eligible_report(engine)
    await _activate_control(engine)
    old_batch_id = await _new_batch(engine)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        old_batch = await set_batch_state(session, batch_id=old_batch_id, state="paused", enabled=True)
        await session.commit()
    _, second_report_id = await _store_eligible_report(
        engine,
        subject_id=subject_id,
        created_at=datetime.now(timezone.utc) + timedelta(seconds=1),
    )
    newer_batch_id = await _new_batch(engine)
    await _process_once(engine, newer_batch_id)
    async with AsyncSession(bind=engine) as session:
        newer_batch = await session.get(CompanyReportPublicationBatch, newer_batch_id)
        current = await session.scalar(select(CompanyReportPublication).where(CompanyReportPublication.subject_id == subject_id))
        assert newer_batch is not None and current is not None and current.batch_generation == newer_batch.generation
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await set_batch_state(session, batch_id=old_batch_id, state="running", enabled=True)
        await session.commit()
    await _process_once(engine, old_batch_id)
    async with AsyncSession(bind=engine) as session:
        old_batch = await session.get(CompanyReportPublicationBatch, old_batch_id)
        publication = await session.scalar(select(CompanyReportPublication).where(CompanyReportPublication.subject_id == subject_id))
        old_item = await session.scalar(select(CompanyReportPublicationBatchItem).where(CompanyReportPublicationBatchItem.batch_id == old_batch_id))
        newer_item = await session.scalar(select(CompanyReportPublicationBatchItem).where(CompanyReportPublicationBatchItem.batch_id == newer_batch_id))
        journals = (await session.execute(select(CompanyReportPublicationJournal.action, CompanyReportPublicationJournal.reason_code).where(CompanyReportPublicationJournal.subject_id == subject_id))).all()
        assert old_batch is not None and publication is not None and old_item is not None
        assert newer_item is not None and old_item.report_id == first_report_id and newer_item.report_id == second_report_id
        assert publication.batch_generation > old_batch.generation
        assert publication.report_id == second_report_id and publication.snapshot_hash == newer_item.snapshot_hash
        assert old_item.state == "skipped" and old_item.reason_code == "superseded_by_newer_batch"
        assert set(journals) == {("published", "sufficient"), ("skipped", "superseded_by_newer_batch")}


async def test_batch_manifest_is_immutable_across_pause_and_resume(engine):
    await _require_publication_tables(engine)
    subject_id, first_report_id = await _store_eligible_report(engine)
    await _activate_control(engine)
    batch_id = await _new_batch(engine)
    async with AsyncSession(bind=engine) as session:
        before = (await session.execute(select(CompanyReportPublicationBatchItem.report_id, CompanyReportPublicationBatchItem.ordinal).where(CompanyReportPublicationBatchItem.batch_id == batch_id))).all()
    _, later_report_id = await _store_eligible_report(engine, subject_id=subject_id, created_at=datetime.now(timezone.utc) + timedelta(seconds=1))
    assert later_report_id != first_report_id
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await set_batch_state(session, batch_id=batch_id, state="paused", enabled=True)
        await set_batch_state(session, batch_id=batch_id, state="running", enabled=True)
        await session.commit()
    async with AsyncSession(bind=engine) as session:
        after = (await session.execute(select(CompanyReportPublicationBatchItem.report_id, CompanyReportPublicationBatchItem.ordinal).where(CompanyReportPublicationBatchItem.batch_id == batch_id))).all()
    assert after == before == [(first_report_id, 0)]


async def test_replacement_preserves_old_journal_and_replaces_subject_publication(engine):
    await _require_publication_tables(engine)
    subject_id, first_report_id = await _store_eligible_report(engine)
    await _activate_control(engine)
    await _process_once(engine, await _new_batch(engine))
    _, second_report_id = await _store_eligible_report(engine, subject_id=subject_id, created_at=datetime.now(timezone.utc) + timedelta(seconds=1))
    await _process_once(engine, await _new_batch(engine))
    async with AsyncSession(bind=engine) as session:
        publication = await session.scalar(select(CompanyReportPublication).where(CompanyReportPublication.subject_id == subject_id))
        journal_report_ids = (await session.execute(select(CompanyReportPublicationJournal.report_id).order_by(CompanyReportPublicationJournal.created_at))).scalars().all()
    assert publication is not None and publication.report_id == second_report_id
    assert journal_report_ids == [first_report_id, second_report_id]


async def test_rerun_is_idempotent_for_publication_batch_items_and_journal(engine):
    await _require_publication_tables(engine)
    await _store_eligible_report(engine)
    await _activate_control(engine)
    batch_id = await _new_batch(engine)
    await _process_once(engine, batch_id)
    await _process_once(engine, batch_id)
    rerun_batch_id = await _new_batch(engine)
    async with AsyncSession(bind=engine) as session:
        publications = await session.scalar(select(func.count(CompanyReportPublication.id)))
        items = await session.scalar(select(func.count(CompanyReportPublicationBatchItem.id)))
        journals = await session.scalar(select(func.count(CompanyReportPublicationJournal.id)))
        rerun = await session.get(CompanyReportPublicationBatch, rerun_batch_id)
    assert (publications, items, journals) == (1, 1, 1)
    assert rerun is not None and rerun.state == "completed" and rerun.candidate_count == 0


_POSTGRES_FINALIZER_MISMATCHES = (
    "claim_batch_lookup", "claim_item_lookup", "batch_cursor", "item_batch",
    "item_ordinal", "item_state", "item_token", "item_policy", "batch_policy",
    "alternate_subject", "item_hash", "raw_hash", "non_object_snapshot",
    "missing_stored_hash", "lifecycle_pending", "lifecycle_failed",
    "missing_generated_at", "wrong_subject_identifier",
    "raw_version_missing", "raw_version_non_string", "raw_version_unknown",
    "raw_v2_missing_optional_datasets", "raw_v2_missing_tax_info",
    "raw_v2_missing_bankruptcy", "raw_v1_contains_v2", "parsed_report_id",
    "parsed_report_version", "parsed_status", "parsed_generated_at",
    "parsed_target", "missing_counterparty", "counterparty_inn",
)

_OUTER_CLAIM_MISMATCHES = {
    "claim_batch_lookup", "claim_item_lookup", "batch_cursor", "item_batch",
    "item_ordinal", "item_state", "item_token",
}


def _replace_persisted_raw(report, item, mutate, *, rehash=True):
    raw = deepcopy(report.normalized_snapshot)
    mutate(raw)
    report.normalized_snapshot = raw
    if rehash:
        digest = calculate_company_report_snapshot_hash(raw)
        report.snapshot_hash = digest
        item.snapshot_hash = digest


async def _apply_postgres_finalizer_mismatch(
    session: AsyncSession,
    *,
    mismatch: str,
    claim: PublicationBatchClaim,
    batch: CompanyReportPublicationBatch,
    item: CompanyReportPublicationBatchItem,
    report: CompanyReportRecord,
) -> PublicationBatchClaim:
    if mismatch == "claim_batch_lookup":
        return PublicationBatchClaim(uuid4(), claim.item_id, claim.ordinal, claim.token)
    if mismatch == "claim_item_lookup":
        return PublicationBatchClaim(claim.batch_id, uuid4(), claim.ordinal, claim.token)
    if mismatch == "batch_cursor":
        batch.next_ordinal = 1
    elif mismatch == "item_batch":
        alternate_batch = CompanyReportPublicationBatch(
            state="completed", requested_limit=1, candidate_count=0,
            next_ordinal=0, claimed_ordinal=None,
            policy_version=PUBLICATION_POLICY_VERSION,
            completed_at=datetime.now(timezone.utc),
        )
        session.add(alternate_batch)
        await session.flush()
        item.batch_id = alternate_batch.id
    elif mismatch == "item_ordinal":
        item.ordinal = 1
    elif mismatch == "item_state":
        item.state = "pending"
        item.claim_token = None
        item.claimed_at = None
    elif mismatch == "item_token":
        item.claim_token = uuid4()
    elif mismatch == "item_policy":
        item.policy_version = "alternate_policy"
    elif mismatch == "batch_policy":
        batch.policy_version = "alternate_policy"
    elif mismatch == "alternate_subject":
        alternate = CompanyReportSubject(
            normalized_identifier="1111111111", identifier_type="legal_entity"
        )
        session.add(alternate)
        await session.flush()
        item.subject_id = alternate.id
    elif mismatch == "item_hash":
        item.snapshot_hash = "0" * 64
    elif mismatch == "raw_hash":
        _replace_persisted_raw(
            report, item,
            lambda raw: raw.__setitem__("target_identifier", "1111111111"),
            rehash=False,
        )
    elif mismatch == "non_object_snapshot":
        report.normalized_snapshot = []
    elif mismatch == "missing_stored_hash":
        report.snapshot_hash = None
    elif mismatch == "lifecycle_pending":
        report.lifecycle_status = "pending"
    elif mismatch == "lifecycle_failed":
        report.lifecycle_status = "failed"
    elif mismatch == "unknown_orm_version":
        report.report_version = "unknown"
    elif mismatch == "missing_generated_at":
        report.generated_at = None
    elif mismatch == "wrong_subject_identifier":
        subject = await session.get(CompanyReportSubject, item.subject_id)
        assert subject is not None
        subject.normalized_identifier = "1111111111"
    elif mismatch == "raw_version_missing":
        _replace_persisted_raw(report, item, lambda raw: raw.pop("report_version"))
    elif mismatch == "raw_version_non_string":
        _replace_persisted_raw(report, item, lambda raw: raw.__setitem__("report_version", 2))
    elif mismatch == "raw_version_unknown":
        _replace_persisted_raw(report, item, lambda raw: raw.__setitem__("report_version", "3"))
    elif mismatch.startswith("raw_v2_missing_"):
        field = mismatch.removeprefix("raw_v2_missing_")
        _replace_persisted_raw(report, item, lambda raw: raw.pop(field))
    elif mismatch == "raw_v1_contains_v2":
        _replace_persisted_raw(report, item, lambda raw: raw.__setitem__("report_version", "1"))
    elif mismatch == "parsed_report_id":
        _replace_persisted_raw(report, item, lambda raw: raw.__setitem__("report_id", str(uuid4())))
    elif mismatch == "parsed_report_version":
        report.report_version = "1"
    elif mismatch == "parsed_status":
        _replace_persisted_raw(report, item, lambda raw: raw.__setitem__("status", "partial"))
    elif mismatch == "parsed_generated_at":
        assert report.generated_at is not None
        changed = (report.generated_at + timedelta(seconds=1)).isoformat()
        _replace_persisted_raw(report, item, lambda raw: raw.__setitem__("generated_at", changed))
    elif mismatch == "parsed_target":
        _replace_persisted_raw(report, item, lambda raw: raw.__setitem__("target_identifier", "1111111111"))
    elif mismatch == "missing_counterparty":
        _replace_persisted_raw(report, item, lambda raw: raw.__setitem__("counterparty", None))
    elif mismatch == "counterparty_inn":
        _replace_persisted_raw(report, item, lambda raw: raw["counterparty"].__setitem__("inn", "1111111111"))
    else:
        raise AssertionError(f"unknown PostgreSQL finalizer case: {mismatch}")
    return claim


@pytest.mark.parametrize("mismatch", _POSTGRES_FINALIZER_MISMATCHES)
async def test_finalizer_integrity_mismatch_preserves_every_sentinel_column(
    engine, monkeypatch, mismatch
):
    await _require_publication_tables(engine)
    subject_id, first_report_id = await _store_eligible_report(engine)
    await _activate_control(engine)
    await _process_once(engine, await _new_batch(engine))
    async with AsyncSession(bind=engine) as session:
        before = await _publication_sentinel_rows(session)
    assert len(before) == 1

    _, second_report_id = await _store_eligible_report(
        engine,
        subject_id=subject_id,
        created_at=datetime.now(timezone.utc) + timedelta(seconds=1),
    )
    batch_id = await _new_batch(engine)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim = await claim_next_batch_item(session, batch_id=batch_id)
        assert claim is not None
        await session.commit()
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        item = await session.get(CompanyReportPublicationBatchItem, claim.item_id)
        report = await session.get(CompanyReportRecord, second_report_id)
        batch = await session.get(CompanyReportPublicationBatch, batch_id)
        assert item is not None and report is not None and batch is not None
        claim = await _apply_postgres_finalizer_mismatch(
            session, mismatch=mismatch, claim=claim, batch=batch, item=item, report=report
        )
        await session.commit()

    calls = {"evaluator": 0, "upsert": 0}

    def forbidden(*_args, **_kwargs):
        calls["evaluator"] += 1
        raise AssertionError("evaluator must be unreachable")

    async def forbidden_async(*_args, **_kwargs):
        calls["upsert"] += 1
        raise AssertionError("upsert must be unreachable")

    monkeypatch.setattr(publications, "evaluate_publication", forbidden)
    monkeypatch.setattr(publications, "_upsert_publication", forbidden_async)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        if mismatch in _OUTER_CLAIM_MISMATCHES:
            with pytest.raises(PublicationStateConflictError):
                await finalize_batch_claim(session, claim=claim)
        else:
            await finalize_batch_claim(session, claim=claim)
        await session.commit()
    async with AsyncSession(bind=engine) as session:
        after = await _publication_sentinel_rows(session)
        item = await session.get(CompanyReportPublicationBatchItem, claim.item_id)

    assert before[0].report_id == first_report_id
    assert len(after) == 1 and after == before
    assert calls == {"evaluator": 0, "upsert": 0}
    if mismatch not in _OUTER_CLAIM_MISMATCHES:
        assert item is not None
        assert item.state == "failed" and item.reason_code == "state_conflict"
