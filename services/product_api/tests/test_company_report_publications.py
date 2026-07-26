from __future__ import annotations

import asyncio
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
from product_api.company_reports.persistence.publications import (
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
    report = complete_company_report(counterparty=counterparty).model_copy(
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
            subject_id=subject_id,
            report_version="v1",
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
