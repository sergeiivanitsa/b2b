"""Persistence primitives for the explicitly operated SEO publication registry."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
    company_report_from_snapshot,
)
from product_api.company_reports.seo import canonical_path, evaluate_publication


class PublicationStateConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicationBatchClaim:
    """A durable ownership token for one immutable manifest ordinal."""

    batch_id: UUID
    item_id: UUID
    ordinal: int
    token: UUID


@dataclass(frozen=True)
class PublicPageRecord:
    publication: CompanyReportPublication
    report: CompanyReportRecord
    subject: CompanyReportSubject


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


async def get_public_page(session: AsyncSession, *, inn: str) -> PublicPageRecord | None:
    result = await session.execute(
        select(CompanyReportPublication, CompanyReportRecord, CompanyReportSubject)
        .join(CompanyReportRecord, CompanyReportRecord.id == CompanyReportPublication.report_id)
        .join(CompanyReportSubject, CompanyReportSubject.id == CompanyReportPublication.subject_id)
        .where(CompanyReportSubject.normalized_identifier == inn)
    )
    row = result.one_or_none()
    return PublicPageRecord(*row) if row else None


async def list_indexable_publications(session: AsyncSession) -> list[PublicPageRecord]:
    result = await session.execute(
        select(CompanyReportPublication, CompanyReportRecord, CompanyReportSubject)
        .join(CompanyReportRecord, CompanyReportRecord.id == CompanyReportPublication.report_id)
        .join(CompanyReportSubject, CompanyReportSubject.id == CompanyReportPublication.subject_id)
        .where(CompanyReportPublication.status == "active", CompanyReportPublication.indexable.is_(True))
        .order_by(CompanyReportPublication.canonical_path)
    )
    return [PublicPageRecord(*row) for row in result.all()]


async def set_publication_control(session: AsyncSession, *, state: str, enabled: bool) -> CompanyReportPublicationControl:
    if state not in {"paused", "active"}:
        raise PublicationStateConflictError("invalid publication control state")
    if state == "active" and not enabled:
        raise PublicationStateConflictError("SEO_PUBLIC_ROLLOUT_ENABLED is required")
    control = await session.get(CompanyReportPublicationControl, 1, with_for_update=True)
    if control is None:
        raise PublicationStateConflictError("publication control is missing")
    control.state = state
    await session.flush()
    return control


async def create_batch(session: AsyncSession, *, limit: int, max_limit: int) -> CompanyReportPublicationBatch:
    if not 1 <= limit <= max_limit:
        raise PublicationStateConflictError("publication batch limit is outside configured bounds")
    control = await session.get(CompanyReportPublicationControl, 1, with_for_update=True)
    if control is None or control.state != "active":
        raise PublicationStateConflictError("publication control is paused")
    records = (await session.execute(
        select(CompanyReportRecord).where(
            CompanyReportRecord.lifecycle_status.in_(("complete", "partial")),
            CompanyReportRecord.normalized_snapshot.is_not(None),
            CompanyReportRecord.snapshot_hash.is_not(None),
        ).order_by(CompanyReportRecord.created_at.desc(), CompanyReportRecord.id.desc())
    )).scalars().all()
    latest_by_subject: dict[UUID, CompanyReportRecord] = {}
    for record in records:
        latest_by_subject.setdefault(record.subject_id, record)
    candidates: list[CompanyReportRecord] = []
    for record in latest_by_subject.values():
        terminal = await session.scalar(select(CompanyReportPublicationJournal.id).where(
            CompanyReportPublicationJournal.report_id == record.id,
            CompanyReportPublicationJournal.snapshot_hash == record.snapshot_hash,
            CompanyReportPublicationJournal.policy_version == PUBLICATION_POLICY_VERSION,
        ).limit(1))
        if terminal is None:
            candidates.append(record)
    candidates.sort(key=lambda record: (record.created_at, record.id))
    candidates = candidates[:limit]
    batch = CompanyReportPublicationBatch(
        state="running" if candidates else "completed", requested_limit=limit,
        candidate_count=len(candidates), next_ordinal=0,
        policy_version=PUBLICATION_POLICY_VERSION,
        completed_at=None if candidates else datetime.now(timezone.utc),
    )
    session.add(batch)
    await session.flush()
    for ordinal, report in enumerate(candidates):
        session.add(CompanyReportPublicationBatchItem(
            batch_id=batch.id, ordinal=ordinal, subject_id=report.subject_id, report_id=report.id,
            snapshot_hash=report.snapshot_hash or "", policy_version=PUBLICATION_POLICY_VERSION, state="pending",
        ))
    await session.flush()
    return batch


async def set_batch_state(session: AsyncSession, *, batch_id: UUID, state: str, enabled: bool) -> CompanyReportPublicationBatch:
    if state not in {"paused", "running"}:
        raise PublicationStateConflictError("invalid batch state")
    if state == "running" and not enabled:
        raise PublicationStateConflictError("SEO_PUBLIC_ROLLOUT_ENABLED is required")
    batch = await session.get(CompanyReportPublicationBatch, batch_id, with_for_update=True)
    if batch is None or batch.state in {"completed", "failed"}:
        raise PublicationStateConflictError("batch cannot be changed")
    batch.state = state
    await session.flush()
    return batch


async def _upsert_publication(
    session: AsyncSession,
    *,
    subject_id: UUID,
    report_id: UUID,
    canonical_slug: str,
    canonical_path_value: str,
    snapshot_hash: str,
    policy_version: str,
    batch_generation: int,
    sufficiency_status: str,
    published_lastmod: datetime,
) -> tuple[CompanyReportPublication, bool]:
    """Atomically publish only when this immutable batch is newer.

    ``generation`` is a PostgreSQL identity generated when the batch is
    persisted.  The subject-key conflict and the generation predicate execute
    in one statement, so an old resumed batch cannot overwrite a newer page.
    """
    values = {
        "subject_id": subject_id,
        "report_id": report_id,
        "status": "active",
        "canonical_slug": canonical_slug,
        "canonical_path": canonical_path_value,
        "snapshot_hash": snapshot_hash,
        "policy_version": policy_version,
        "batch_generation": batch_generation,
        "indexable": True,
        "sufficiency_status": sufficiency_status,
        "published_lastmod": published_lastmod,
    }
    try:
        async with session.begin_nested():
            insert_statement = postgresql_insert(CompanyReportPublication).values(**values)
            updated_values = {
                name: getattr(insert_statement.excluded, name)
                for name in values
                if name != "subject_id"
            }
            publication_id = await session.scalar(
                insert_statement.on_conflict_do_update(
                    index_elements=["subject_id"],
                    set_=updated_values,
                    where=(
                        CompanyReportPublication.batch_generation
                        < insert_statement.excluded.batch_generation
                    ),
                ).returning(CompanyReportPublication.id)
            )
            if publication_id is not None:
                publication = await session.get(CompanyReportPublication, publication_id)
                if publication is None:
                    raise PublicationStateConflictError("publication write could not be reread")
                return publication, True
            publication = await session.scalar(
                select(CompanyReportPublication)
                .where(CompanyReportPublication.subject_id == subject_id)
                .with_for_update()
            )
            if publication is None:
                raise PublicationStateConflictError("publication conflict could not be reread")
            return publication, False
    except IntegrityError as exc:
        # The savepoint keeps the outer transaction usable.  A conflict on a
        # distinct report/path key cannot be safely interpreted as replacement.
        raise PublicationStateConflictError("publication unique constraint conflict") from exc


async def claim_next_batch_item(
    session: AsyncSession, *, batch_id: UUID
) -> PublicationBatchClaim | None:
    """Claim exactly the persisted cursor ordinal through the worker flow."""
    batch = await session.get(CompanyReportPublicationBatch, batch_id, with_for_update=True)
    control = await session.get(CompanyReportPublicationControl, 1, with_for_update=True)
    if batch is None or control is None:
        raise PublicationStateConflictError("publication state is missing")
    if batch.state != "running":
        return None
    if control.state != "active":
        batch.state = "paused"
        await session.flush()
        return None
    if batch.next_ordinal >= batch.candidate_count:
        batch.state, batch.completed_at = "completed", datetime.now(timezone.utc)
        await session.flush()
        return None
    item = (await session.execute(
        select(CompanyReportPublicationBatchItem).where(
            CompanyReportPublicationBatchItem.batch_id == batch.id,
            CompanyReportPublicationBatchItem.ordinal == batch.next_ordinal,
        ).with_for_update()
    )).scalar_one()
    if item.state != "pending":
        raise PublicationStateConflictError("manifest ordinal is not pending")
    token = uuid4()
    claimed = await session.execute(
        update(CompanyReportPublicationBatchItem)
        .where(
            CompanyReportPublicationBatchItem.id == item.id,
            CompanyReportPublicationBatchItem.state == "pending",
            CompanyReportPublicationBatchItem.ordinal == batch.next_ordinal,
        )
        .values(state="claimed", claim_token=token, claimed_at=datetime.now(timezone.utc))
    )
    if claimed.rowcount != 1:
        raise PublicationStateConflictError("manifest claim conflict")
    await session.flush()
    return PublicationBatchClaim(
        batch_id=batch.id, item_id=item.id, ordinal=item.ordinal, token=token
    )


async def relinquish_batch_claim(
    session: AsyncSession, *, claim: PublicationBatchClaim
) -> None:
    """Return an unfinished claim to its immutable ordinal for another worker."""
    released = await session.execute(
        update(CompanyReportPublicationBatchItem)
        .where(
            CompanyReportPublicationBatchItem.id == claim.item_id,
            CompanyReportPublicationBatchItem.batch_id == claim.batch_id,
            CompanyReportPublicationBatchItem.ordinal == claim.ordinal,
            CompanyReportPublicationBatchItem.state == "claimed",
            CompanyReportPublicationBatchItem.claim_token == claim.token,
        )
        .values(state="pending", claim_token=None, claimed_at=None)
    )
    if released.rowcount != 1:
        raise PublicationStateConflictError("manifest claim is no longer current")
    await session.flush()


async def finalize_batch_claim(
    session: AsyncSession, *, claim: PublicationBatchClaim
) -> CompanyReportPublicationBatch:
    """Fence a claim before any publication or terminal mutation occurs."""
    batch = await session.get(CompanyReportPublicationBatch, claim.batch_id, with_for_update=True)
    item = await session.get(CompanyReportPublicationBatchItem, claim.item_id, with_for_update=True)
    if (
        batch is None
        or item is None
        or batch.next_ordinal != claim.ordinal
        or item.batch_id != claim.batch_id
        or item.ordinal != claim.ordinal
        or item.state != "claimed"
        or item.claim_token != claim.token
    ):
        raise PublicationStateConflictError("manifest claim is no longer current")
    report = await session.get(CompanyReportRecord, item.report_id)
    terminal, reason = "skipped", "invalid_report"
    if report and report.normalized_snapshot and report.snapshot_hash == item.snapshot_hash:
        try:
            if calculate_company_report_snapshot_hash(report.normalized_snapshot) != report.snapshot_hash:
                raise PublicationStateConflictError("snapshot hash mismatch")
            report_model = company_report_from_snapshot(report.normalized_snapshot)
            decision = evaluate_publication(report_model)
            if decision.indexable and decision.projection:
                path = canonical_path(decision.projection.inn, decision.projection.name)
                lastmod = _utc(report.generated_at or report.finished_at) if (report.generated_at or report.finished_at) else None
                if lastmod is None:
                    raise PublicationStateConflictError("final report has no lastmod")
                slug = path[len(f"/company/{decision.projection.inn}-"):]
                _, applied = await _upsert_publication(
                    session,
                    subject_id=report.subject_id,
                    report_id=report.id,
                    canonical_slug=slug,
                    canonical_path_value=path,
                    snapshot_hash=report.snapshot_hash,
                    policy_version=item.policy_version,
                    batch_generation=batch.generation,
                    sufficiency_status=decision.sufficiency_status,
                    published_lastmod=lastmod,
                )
                terminal, reason = (
                    ("published", "sufficient")
                    if applied
                    else ("skipped", "superseded_by_newer_batch")
                )
            else:
                reason = decision.sufficiency_status
        except PublicationStateConflictError:
            terminal, reason = "failed", "state_conflict"
        except Exception:
            terminal, reason = "failed", "safe_policy_error"
    finalized = await session.execute(
        update(CompanyReportPublicationBatchItem)
        .where(
            CompanyReportPublicationBatchItem.id == item.id,
            CompanyReportPublicationBatchItem.state == "claimed",
            CompanyReportPublicationBatchItem.claim_token == claim.token,
            CompanyReportPublicationBatchItem.ordinal == batch.next_ordinal,
        )
        .values(state=terminal, reason_code=reason, finished_at=datetime.now(timezone.utc))
    )
    if finalized.rowcount != 1:
        raise PublicationStateConflictError("manifest finalize conflict")
    try:
        async with session.begin_nested():
            session.add(CompanyReportPublicationJournal(batch_id=batch.id, ordinal=item.ordinal, subject_id=item.subject_id, report_id=item.report_id, snapshot_hash=item.snapshot_hash, policy_version=item.policy_version, action=terminal, reason_code=reason))
            await session.flush()
    except IntegrityError:
        existing_journal = await session.scalar(select(CompanyReportPublicationJournal.id).where(
            CompanyReportPublicationJournal.report_id == item.report_id,
            CompanyReportPublicationJournal.snapshot_hash == item.snapshot_hash,
            CompanyReportPublicationJournal.policy_version == item.policy_version,
            CompanyReportPublicationJournal.action == terminal,
        ))
        if existing_journal is None:
            raise PublicationStateConflictError("journal conflict")
    batch.claimed_ordinal, batch.next_ordinal = item.ordinal, item.ordinal + 1
    if batch.next_ordinal == batch.candidate_count:
        batch.state, batch.completed_at = "completed", datetime.now(timezone.utc)
    await session.flush()
    return batch


async def process_batch(session: AsyncSession, *, batch_id: UUID) -> CompanyReportPublicationBatch:
    """Claim and finalize at most one persisted ordinal in this transaction.

    Callers commit this result before asking for the next item.  That boundary
    deliberately lets an external pause win before any subsequent claim.
    """
    claim = await claim_next_batch_item(session, batch_id=batch_id)
    if claim is None:
        batch = await session.get(CompanyReportPublicationBatch, batch_id)
        if batch is None:
            raise PublicationStateConflictError("publication state is missing")
        return batch
    return await finalize_batch_claim(session, claim=claim)


__all__ = ["PublicPageRecord", "PublicationBatchClaim", "PublicationStateConflictError", "claim_next_batch_item", "create_batch", "finalize_batch_claim", "get_public_page", "list_indexable_publications", "process_batch", "relinquish_batch_claim", "set_batch_state", "set_publication_control"]
