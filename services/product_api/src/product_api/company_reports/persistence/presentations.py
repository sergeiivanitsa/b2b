"""Internal immutable H1/H2 pins and CAS assignment foundation.

No router imports mutation functions from this module.
"""
from __future__ import annotations

from datetime import datetime
from copy import deepcopy
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    CompanyReportH2LifecycleHead, CompanyReportPresentation, CompanyReportPresentationAssignment, CompanyReportPresentationAssignmentJournal,
    CompanyReportPresentationPin, CompanyReportPresentationStagedPointer, CompanyReportRecord,
)
from .jobs import EnqueuedReportJob, H2_PRESENTATION_CONTRACT, H2_WRITER_PROFILE, WriterDecision, enqueue_company_report_job
from .v3 import calculate_company_card_v2_snapshot_hash, company_card_v2_from_snapshot

H2_PUBLICATION_POLICY_VERSION = "company_public_h2_publication_v1"


class PresentationAssignmentConflict(RuntimeError):
    code = "presentation_assignment_conflict"


async def create_or_reuse_h2_presentation(
    session: AsyncSession, *, identifier: str, rollout_generation: int
) -> tuple[CompanyReportPresentation, EnqueuedReportJob, CompanyReportH2LifecycleHead]:
    """Atomically create/reuse the only H2 writer decision and its durable head."""
    decision = WriterDecision(
        writer_profile=H2_WRITER_PROFILE, report_version="3",
        presentation_contract=H2_PRESENTATION_CONTRACT, rollout_generation=rollout_generation,
    )
    enqueued = await enqueue_company_report_job(session, identifier, decision=decision)
    presentation = await session.scalar(select(CompanyReportPresentation).where(
        CompanyReportPresentation.report_id == enqueued.report_id,
        CompanyReportPresentation.presentation_contract == H2_PRESENTATION_CONTRACT,
    ).with_for_update())
    if presentation is None:
        presentation = CompanyReportPresentation(
            subject_id=enqueued.subject_id, report_id=enqueued.report_id,
            presentation_contract=H2_PRESENTATION_CONTRACT,
            rollout_generation=rollout_generation,
        )
        session.add(presentation)
        await session.flush()
    elif (presentation.subject_id, presentation.rollout_generation) != (enqueued.subject_id, rollout_generation):
        raise PresentationAssignmentConflict("presentation exact binding is invalid")
    head = await session.get(CompanyReportH2LifecycleHead, enqueued.subject_id, with_for_update=True)
    if head is None:
        head = CompanyReportH2LifecycleHead(
            subject_id=enqueued.subject_id, presentation_id=presentation.id,
            report_id=enqueued.report_id, presentation_contract=H2_PRESENTATION_CONTRACT,
            rollout_generation=rollout_generation, head_generation=1,
        )
        session.add(head)
    elif (head.presentation_id, head.report_id, head.presentation_contract, head.rollout_generation) != (
        presentation.id, enqueued.report_id, H2_PRESENTATION_CONTRACT, rollout_generation,
    ):
        head.presentation_id = presentation.id
        head.report_id = enqueued.report_id
        head.presentation_contract = H2_PRESENTATION_CONTRACT
        head.rollout_generation = rollout_generation
        head.head_generation += 1
    await session.flush()
    return presentation, enqueued, head


async def append_presentation_pin(
    session: AsyncSession,
    *,
    subject_id: UUID,
    report: CompanyReportRecord,
    contract: str,
    generation: int,
    publication_policy_version: str | None = None,
    canonical_path: str | None = None,
    published_lastmod: datetime | None = None,
    indexable: bool | None = None,
    chart_facts_version: str | None = None,
    chart_facts_hash: str | None = None,
    evidence_registry_version: str | None = None,
) -> CompanyReportPresentationPin:
    if generation <= 0 or report.subject_id != subject_id or not report.snapshot_hash:
        raise PresentationAssignmentConflict("presentation pin identity is invalid")
    existing = await session.scalar(select(CompanyReportPresentationPin).where(
        CompanyReportPresentationPin.subject_id == subject_id,
        CompanyReportPresentationPin.presentation_contract == contract,
        CompanyReportPresentationPin.generation == generation,
    ).with_for_update())
    if existing is not None:
        if (
            existing.report_id == report.id
            and existing.snapshot_hash == report.snapshot_hash
            and existing.presentation_contract == contract
        ):
            return existing
        raise PresentationAssignmentConflict("presentation pin generation conflicts")
    if contract not in {"company_public_h1_v1", "company_public_h2_v1"}:
        raise PresentationAssignmentConflict("presentation contract is invalid")
    if contract == "company_public_h2_v1":
        if (report.writer_profile, report.presentation_contract, report.report_version) != (
            "company_card_v2_writer_v3", "company_public_h2_v1", "3",
        ) or report.rollout_generation <= 0:
            raise PresentationAssignmentConflict("H2 pin report decision is invalid")
        # The iteration-20 H2 pin is deliberately unresolved, but it is still
        # an immutable evidence binding.  Do not persist a partially-shaped
        # noindex pin that a future activation could mistake for eligible.
        try:
            snapshot = company_card_v2_from_snapshot(deepcopy(report.normalized_snapshot))
        except Exception as exc:
            raise PresentationAssignmentConflict("H2 pin snapshot is invalid") from exc
        if (
            report.snapshot_hash != calculate_company_card_v2_snapshot_hash(snapshot)
            or snapshot.report_id != str(report.id)
            or snapshot.rollout_config_generation != report.rollout_generation
            or chart_facts_version != snapshot.chart_facts.version
            or chart_facts_hash != snapshot.chart_facts.hash
            or evidence_registry_version != snapshot.evidence_version
            or publication_policy_version != H2_PUBLICATION_POLICY_VERSION
        ):
            raise PresentationAssignmentConflict("H2 pin evidence identity is invalid")
        pin = CompanyReportPresentationPin(
            subject_id=subject_id, report_id=report.id, presentation_contract=contract,
            generation=generation, snapshot_hash=report.snapshot_hash, indexable=False,
            projection_digest=None, narrative_binding_status="unresolved",
            narrative_binding_kind=None, narrative_binding_key=None,
            chart_facts_version=chart_facts_version,
            chart_facts_hash=chart_facts_hash,
            evidence_registry_version=evidence_registry_version,
            publication_policy_version=publication_policy_version,
        )
    else:
        if (
            not publication_policy_version
            or not canonical_path
            or published_lastmod is None
            or indexable is not True
        ):
            raise PresentationAssignmentConflict("H1 pin publication identity is invalid")
        pin = CompanyReportPresentationPin(
            subject_id=subject_id, report_id=report.id, presentation_contract=contract,
            generation=generation, snapshot_hash=report.snapshot_hash,
            publication_policy_version=publication_policy_version,
            canonical_path=canonical_path,
            published_lastmod=published_lastmod,
            indexable=True,
        )
    session.add(pin)
    await session.flush()
    return pin


async def stage_h2_pin(session: AsyncSession, *, subject_id: UUID, pin: CompanyReportPresentationPin, expected_generation: int) -> CompanyReportPresentationStagedPointer:
    if pin.subject_id != subject_id or pin.presentation_contract != "company_public_h2_v1" or expected_generation != pin.generation:
        raise PresentationAssignmentConflict("staged pointer identity is invalid")
    pointer = await session.scalar(select(CompanyReportPresentationStagedPointer).where(CompanyReportPresentationStagedPointer.subject_id == subject_id).with_for_update())
    if pointer is None:
        pointer = CompanyReportPresentationStagedPointer(
            subject_id=subject_id,
            presentation_contract=pin.presentation_contract,
            generation=pin.generation,
        )
        session.add(pointer)
    elif (
        pointer.presentation_contract != pin.presentation_contract
        or pointer.generation != expected_generation
    ):
        pointer.presentation_contract, pointer.generation = pin.presentation_contract, expected_generation
    await session.flush()
    return pointer


async def assign_pin_cas(session: AsyncSession, *, subject_id: UUID, pin: CompanyReportPresentationPin, expected_generation: int) -> CompanyReportPresentationAssignment:
    if pin.subject_id != subject_id or expected_generation != pin.generation:
        raise PresentationAssignmentConflict("assignment pin identity is invalid")
    # H2 pins are intentionally unresolved in iteration 20.  Reject before
    # locking/mutating assignment or appending a journal event.
    if pin.presentation_contract == "company_public_h2_v1":
        raise PresentationAssignmentConflict("unresolved H2 pin is not assignable")
    if pin.presentation_contract != "company_public_h1_v1":
        raise PresentationAssignmentConflict("assignment contract is invalid")
    assignment = await session.scalar(select(CompanyReportPresentationAssignment).where(CompanyReportPresentationAssignment.subject_id == subject_id).with_for_update())
    if assignment is None:
        if expected_generation != 1:
            raise PresentationAssignmentConflict("assignment generation conflicts")
        assignment = CompanyReportPresentationAssignment(
            subject_id=subject_id,
            presentation_contract=pin.presentation_contract,
            pin_generation=pin.generation,
            generation=1,
        )
        session.add(assignment)
        await session.flush()
        session.add(
            CompanyReportPresentationAssignmentJournal(
                assignment_id=assignment.id,
                subject_id=subject_id,
                presentation_contract=pin.presentation_contract,
                pin_generation=pin.generation,
                generation=1,
            )
        )
    elif assignment.generation != expected_generation - 1:
        raise PresentationAssignmentConflict("assignment generation conflicts")
    else:
        assignment.presentation_contract = pin.presentation_contract
        assignment.pin_generation = pin.generation
        assignment.generation = expected_generation
        session.add(
            CompanyReportPresentationAssignmentJournal(
                assignment_id=assignment.id,
                subject_id=subject_id,
                presentation_contract=pin.presentation_contract,
                pin_generation=pin.generation,
                generation=expected_generation,
            )
        )
    await session.flush()
    return assignment


__all__ = ["PresentationAssignmentConflict", "append_presentation_pin", "assign_pin_cas", "create_or_reuse_h2_presentation", "stage_h2_pin"]
