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
    CompanyCardNarrativeArtifact, CompanyReportH2LifecycleHead, CompanyReportPresentation, CompanyReportPresentationAssignment, CompanyReportPresentationAssignmentJournal, CompanyReportSubject,
    CompanyReportPresentationPin, CompanyReportPresentationStagedPointer, CompanyReportRecord,
)
from .jobs import EnqueuedReportJob, H2_PRESENTATION_CONTRACT, H2_WRITER_PROFILE, WriterDecision, enqueue_company_report_job
from .v3 import calculate_company_card_v2_snapshot_hash, company_card_v2_from_snapshot
from product_api.company_reports.company_card_v2.models import (
    CompanyCardV2SnapshotV1,
    CompanyCardV2SnapshotV2,
    CompanyCardV2SnapshotV3,
)

H2_PUBLICATION_POLICY_V1 = "company_public_h2_publication_v1"
H2_PUBLICATION_POLICY_V2 = "company_public_h2_publication_v2"
H2_PUBLICATION_POLICY_V3 = "company_public_h2_publication_v3"
# Compatibility export used by historical callers; new finalization chooses
# v2 explicitly and stored pins, never this default, drive read behaviour.
H2_PUBLICATION_POLICY_VERSION = H2_PUBLICATION_POLICY_V1
H2_PUBLICATION_POLICY_VERSIONS = frozenset(
    (H2_PUBLICATION_POLICY_V1, H2_PUBLICATION_POLICY_V2, H2_PUBLICATION_POLICY_V3)
)


def _report_arbitration_decision(
    report: CompanyReportRecord,
) -> tuple[bool, str | None]:
    enabled = report.arbitration_collection_enabled
    if enabled is None:
        enabled = False
    if type(enabled) is not bool:
        raise PresentationAssignmentConflict("H2 arbitration decision is invalid")
    key_id = report.arbitration_mask_key_id
    try:
        WriterDecision(
            writer_profile=report.writer_profile,
            report_version=report.report_version,
            presentation_contract=report.presentation_contract,
            rollout_generation=report.rollout_generation,
            arbitration_collection_enabled=enabled,
            arbitration_mask_key_id=key_id,
        )
    except ValueError as exc:
        raise PresentationAssignmentConflict(
            "H2 arbitration decision is invalid"
        ) from exc
    if not enabled and key_id is not None:
        raise PresentationAssignmentConflict("H2 arbitration decision is invalid")
    return enabled, key_id


def _validate_h2_snapshot_policy(
    report: CompanyReportRecord,
    snapshot: CompanyCardV2SnapshotV1,
    policy: str,
) -> None:
    enabled, intended_key_id = _report_arbitration_decision(report)
    if policy == H2_PUBLICATION_POLICY_V1:
        valid = type(snapshot) in {CompanyCardV2SnapshotV1, CompanyCardV2SnapshotV2} and not enabled
    elif policy == H2_PUBLICATION_POLICY_V2:
        valid = type(snapshot) is CompanyCardV2SnapshotV2 and not enabled
    elif policy == H2_PUBLICATION_POLICY_V3:
        valid = type(snapshot) is CompanyCardV2SnapshotV3 and enabled
        if valid:
            effective_key_id = snapshot.arbitration_basis.mask_key_id
            valid = effective_key_id is None or effective_key_id == intended_key_id
    else:
        valid = False
    if not valid or (not enabled and intended_key_id is not None):
        raise PresentationAssignmentConflict("H2 snapshot/policy decision is invalid")


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _has_exact_artifact_binding(artifact: CompanyCardNarrativeArtifact) -> bool:
    if artifact.binding_kind == "artifact":
        return (
            artifact.binding_key == artifact.artifact_identity
            and artifact.fallback_identity is None
            and _is_digest(artifact.artifact_identity)
        )
    if artifact.binding_kind == "fallback":
        return (
            artifact.binding_key == artifact.fallback_identity
            and artifact.artifact_identity is None
            and _is_digest(artifact.fallback_identity)
        )
    return False


class PresentationAssignmentConflict(RuntimeError):
    code = "presentation_assignment_conflict"


async def create_or_reuse_h2_presentation(
    session: AsyncSession,
    *,
    identifier: str,
    rollout_generation: int,
    arbitration_collection_enabled: bool = False,
    arbitration_mask_key_id: str | None = None,
) -> tuple[CompanyReportPresentation, EnqueuedReportJob, CompanyReportH2LifecycleHead]:
    """Atomically create/reuse the only H2 writer decision and its durable head."""
    decision = WriterDecision(
        writer_profile=H2_WRITER_PROFILE, report_version="3",
        presentation_contract=H2_PRESENTATION_CONTRACT, rollout_generation=rollout_generation,
        arbitration_collection_enabled=arbitration_collection_enabled,
        arbitration_mask_key_id=arbitration_mask_key_id,
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
            and existing.publication_policy_version == publication_policy_version
            and existing.canonical_path == canonical_path
            and existing.published_lastmod == published_lastmod
            and existing.indexable
            == (False if contract == H2_PRESENTATION_CONTRACT else indexable)
            and existing.chart_facts_version == chart_facts_version
            and existing.chart_facts_hash == chart_facts_hash
            and existing.evidence_registry_version == evidence_registry_version
            and (
                contract != H2_PRESENTATION_CONTRACT
                or (
                    existing.projection_digest is None
                    and existing.narrative_binding_status == "unresolved"
                    and existing.narrative_binding_kind is None
                    and existing.narrative_binding_key is None
                )
            )
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
        _validate_h2_snapshot_policy(
            report,
            snapshot,
            publication_policy_version or "",
        )
        if (
            report.snapshot_hash != calculate_company_card_v2_snapshot_hash(snapshot)
            or snapshot.report_id != str(report.id)
            or snapshot.rollout_config_generation != report.rollout_generation
            or chart_facts_version != snapshot.chart_facts.version
            or chart_facts_hash != snapshot.chart_facts.hash
            or evidence_registry_version != snapshot.evidence_version
            or publication_policy_version not in H2_PUBLICATION_POLICY_VERSIONS
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


async def _resolve_unresolved_h2_pin(
    session: AsyncSession,
    *,
    report: CompanyReportRecord,
    create_if_missing: bool,
) -> CompanyReportPresentationPin:
    """Resolve the v2 predecessor while holding the stable subject lineage lock.

    The report row is already fenced/locked by ``jobs``.  Locking the subject
    lineage here makes retries deterministic and prevents a v2 pin from being
    silently mixed with an older v1 lineage.
    """
    if (
        report.report_version != "3"
        or report.writer_profile != H2_WRITER_PROFILE
        or report.presentation_contract != H2_PRESENTATION_CONTRACT
        or report.rollout_generation <= 0
        or report.snapshot_hash is None
    ):
        raise PresentationAssignmentConflict("H2 v2 pin report decision is invalid")
    snapshot = company_card_v2_from_snapshot(deepcopy(report.normalized_snapshot))
    if type(snapshot) is CompanyCardV2SnapshotV2:
        expected_policy = H2_PUBLICATION_POLICY_V2
    elif type(snapshot) is CompanyCardV2SnapshotV3:
        expected_policy = H2_PUBLICATION_POLICY_V3
    else:
        raise PresentationAssignmentConflict("H2 current pin snapshot version is invalid")
    _validate_h2_snapshot_policy(report, snapshot, expected_policy)
    if (
        snapshot.report_id != str(report.id)
        or snapshot.rollout_config_generation != report.rollout_generation
        or calculate_company_card_v2_snapshot_hash(snapshot) != report.snapshot_hash
    ):
        raise PresentationAssignmentConflict("H2 v2 pin snapshot is invalid")
    # Lock a stable per-subject row even before a first pin exists; locking an
    # empty result set cannot serialize concurrent first finalizations.
    subject = await session.get(CompanyReportSubject, report.subject_id, with_for_update=True)
    if subject is None:
        raise PresentationAssignmentConflict("H2 pin subject is missing")
    pins = list((await session.scalars(
        select(CompanyReportPresentationPin)
        .where(
            CompanyReportPresentationPin.subject_id == report.subject_id,
            CompanyReportPresentationPin.presentation_contract == H2_PRESENTATION_CONTRACT,
        )
        .order_by(CompanyReportPresentationPin.generation)
        .with_for_update()
    )).all())
    exact = [pin for pin in pins if pin.report_id == report.id]
    # Different reports can retain their historical v1 lineage.  A single
    # report, however, cannot mix policies or immutable snapshot identities.
    # Reject before selecting an unresolved row so retry never masks corruption.
    for pin in exact:
        if (
            pin.publication_policy_version != expected_policy
            or pin.snapshot_hash != report.snapshot_hash
            or pin.chart_facts_version != snapshot.chart_facts.version
            or pin.chart_facts_hash != snapshot.chart_facts.hash
            or pin.evidence_registry_version != snapshot.evidence_version
        ):
            raise PresentationAssignmentConflict("H2 report lineage has mixed policy or identity")
    unresolved = [pin for pin in exact if pin.narrative_binding_status == "unresolved"]
    if unresolved:
        if len(unresolved) != 1:
            raise PresentationAssignmentConflict("H2 report has multiple unresolved lineages")
        pin = unresolved[0]
        if (
            pin.snapshot_hash != report.snapshot_hash
            or pin.publication_policy_version != expected_policy
            or pin.narrative_binding_status != "unresolved"
            or pin.chart_facts_version != snapshot.chart_facts.version
            or pin.chart_facts_hash != snapshot.chart_facts.hash
            or pin.evidence_registry_version != snapshot.evidence_version
        ):
            raise PresentationAssignmentConflict("H2 report pin lineage conflicts")
        return pin
    if exact:
        # A resolved same-report lineage without its immutable predecessor is
        # corruption, not an invitation to rewrite publication policy.
        raise PresentationAssignmentConflict("H2 report lineage is already resolved")
    if not create_if_missing:
        raise PresentationAssignmentConflict(
            "H2 report has no existing unresolved lineage"
        )
    return await append_presentation_pin(
        session,
        subject_id=report.subject_id,
        report=report,
        contract=H2_PRESENTATION_CONTRACT,
        generation=max((pin.generation for pin in pins), default=0) + 1,
        publication_policy_version=expected_policy,
        chart_facts_version=snapshot.chart_facts.version,
        chart_facts_hash=snapshot.chart_facts.hash,
        evidence_registry_version=snapshot.evidence_version,
    )


async def create_or_reuse_unresolved_h2_pin(
    session: AsyncSession,
    *,
    report: CompanyReportRecord,
) -> CompanyReportPresentationPin:
    """Create or reuse v2 lineage inside the first finalization transaction."""
    return await _resolve_unresolved_h2_pin(
        session,
        report=report,
        create_if_missing=True,
    )


async def require_existing_unresolved_h2_pin(
    session: AsyncSession,
    *,
    report: CompanyReportRecord,
) -> CompanyReportPresentationPin:
    """Validate a terminal retry without ever backfilling a missing lineage."""
    return await _resolve_unresolved_h2_pin(
        session,
        report=report,
        create_if_missing=False,
    )


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


async def append_resolved_h2_pin(
    session: AsyncSession,
    *,
    report: CompanyReportRecord,
    artifact: CompanyCardNarrativeArtifact,
    projection_digest: str,
) -> tuple[CompanyReportPresentationPin, CompanyReportPresentationStagedPointer]:
    """Append and stage one exact noindex H2 binding without assignment.

    A resolved pin is immutable.  Repeating finalization for the same artifact
    reuses the exact row; a different binding for the same immutable report is
    rejected instead of silently replacing the public text.
    """
    if (
        report.report_version != "3"
        or report.writer_profile != H2_WRITER_PROFILE
        or report.presentation_contract != H2_PRESENTATION_CONTRACT
        or report.rollout_generation <= 0
        or report.snapshot_hash is None
        or artifact.report_id != report.id
        or artifact.snapshot_hash != report.snapshot_hash
        or not _has_exact_artifact_binding(artifact)
        or not _is_digest(artifact.binding_key)
        or not _is_digest(projection_digest)
    ):
        raise PresentationAssignmentConflict("resolved H2 pin identity is invalid")
    try:
        snapshot = company_card_v2_from_snapshot(deepcopy(report.normalized_snapshot))
    except Exception as exc:
        raise PresentationAssignmentConflict("resolved H2 pin snapshot is invalid") from exc
    if (
        snapshot.report_id != str(report.id)
        or snapshot.rollout_config_generation != report.rollout_generation
        or calculate_company_card_v2_snapshot_hash(snapshot) != report.snapshot_hash
    ):
        raise PresentationAssignmentConflict("resolved H2 pin snapshot identity is invalid")

    pins = (
        await session.scalars(
            select(CompanyReportPresentationPin)
            .where(
                CompanyReportPresentationPin.subject_id == report.subject_id,
                CompanyReportPresentationPin.presentation_contract == H2_PRESENTATION_CONTRACT,
            )
            .order_by(CompanyReportPresentationPin.generation)
            .with_for_update()
        )
    ).all()
    report_lineage = [pin for pin in pins if pin.report_id == report.id]
    unresolved = [pin for pin in report_lineage if pin.narrative_binding_status == "unresolved"]
    if len(unresolved) != 1 or unresolved[0].publication_policy_version not in H2_PUBLICATION_POLICY_VERSIONS:
        raise PresentationAssignmentConflict("resolved H2 pin has no exact unresolved lineage")
    policy = unresolved[0].publication_policy_version
    _validate_h2_snapshot_policy(report, snapshot, policy)
    predecessor = unresolved[0]
    if (
        predecessor.subject_id != report.subject_id
        or predecessor.snapshot_hash != report.snapshot_hash
        or predecessor.indexable is not False
        or predecessor.projection_digest is not None
        or predecessor.narrative_binding_kind is not None
        or predecessor.narrative_binding_key is not None
        or predecessor.chart_facts_version != snapshot.chart_facts.version
        or predecessor.chart_facts_hash != snapshot.chart_facts.hash
        or predecessor.evidence_registry_version != snapshot.evidence_version
    ):
        raise PresentationAssignmentConflict("resolved H2 pin predecessor identity is invalid")
    for existing in pins:
        if existing.report_id != report.id or existing.narrative_binding_status != "resolved":
            continue
        exact = (
            existing.snapshot_hash == report.snapshot_hash
            and existing.indexable is False
            and existing.canonical_path is None
            and existing.published_lastmod is None
            and existing.projection_digest == projection_digest
            and existing.narrative_binding_kind == artifact.binding_kind
            and existing.narrative_binding_key == artifact.binding_key
            and existing.chart_facts_version == snapshot.chart_facts.version
            and existing.chart_facts_hash == snapshot.chart_facts.hash
            and existing.evidence_registry_version == snapshot.evidence_version
            and existing.publication_policy_version == policy
        )
        if not exact:
            raise PresentationAssignmentConflict("resolved H2 pin already exists for report")
        pointer = await stage_h2_pin(
            session,
            subject_id=report.subject_id,
            pin=existing,
            expected_generation=existing.generation,
        )
        return existing, pointer

    generation = max((pin.generation for pin in pins), default=0) + 1
    pin = CompanyReportPresentationPin(
        subject_id=report.subject_id,
        report_id=report.id,
        presentation_contract=H2_PRESENTATION_CONTRACT,
        generation=generation,
        snapshot_hash=report.snapshot_hash,
        chart_facts_version=snapshot.chart_facts.version,
        chart_facts_hash=snapshot.chart_facts.hash,
        evidence_registry_version=snapshot.evidence_version,
        publication_policy_version=policy,
        canonical_path=None,
        indexable=False,
        published_lastmod=None,
        projection_digest=projection_digest,
        narrative_binding_status="resolved",
        narrative_binding_kind=artifact.binding_kind,
        narrative_binding_key=artifact.binding_key,
    )
    session.add(pin)
    await session.flush()
    pointer = await stage_h2_pin(
        session,
        subject_id=report.subject_id,
        pin=pin,
        expected_generation=generation,
    )
    return pin, pointer


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


__all__ = [
    "H2_PUBLICATION_POLICY_V1",
    "H2_PUBLICATION_POLICY_V2",
    "H2_PUBLICATION_POLICY_V3",
    "H2_PUBLICATION_POLICY_VERSION",
    "H2_PUBLICATION_POLICY_VERSIONS",
    "PresentationAssignmentConflict",
    "append_presentation_pin",
    "append_resolved_h2_pin",
    "assign_pin_cas",
    "create_or_reuse_h2_presentation",
    "stage_h2_pin",
]
