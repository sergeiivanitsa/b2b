"""Internal immutable H1/H2 pins and CAS assignment foundation.

No router imports mutation functions from this module.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    CompanyCardNarrativeArtifact,
    CompanyCardNarrativeJob,
    CompanyCardV2RolloutDecision,
    CompanyReportH2LifecycleHead,
    CompanyReportPresentation,
    CompanyReportPresentationAssignment,
    CompanyReportPresentationAssignmentJournal,
    CompanyReportPresentationPin,
    CompanyReportPresentationStagedPointer,
    CompanyReportPublication,
    CompanyReportRecord,
    CompanyReportSubject,
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
H2_STAGED_PROJECTION_SCOPE = "staged_publication"
H2_ACTIVE_PROJECTION_SCOPE = "active_publication"


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


class PresentationLifecycleNotFound(RuntimeError):
    code = "presentation_not_found"


class PresentationLifecycleInvalid(RuntimeError):
    code = "presentation_invalid"


@dataclass(frozen=True)
class ResolvedPresentationLifecycle:
    presentation_id: UUID
    presentation_contract: str
    report_id: UUID
    lifecycle_status: str
    normalized_identifier: str


@dataclass(frozen=True)
class RolloutAssignmentCommand:
    """Exact per-subject CAS input; it never rediscovers a latest pin."""

    decision_id: UUID
    decision_digest: str
    schema_version: str
    release_commit: str
    action: str
    stage: str
    h2_indexable: bool
    target_count: int
    reason_code: str
    subject_id: UUID
    inn: str
    expected_assignment_generation: int
    expected_current_contract: str | None
    expected_current_pin_generation: int | None
    expected_rollout_generation: int | None
    target_contract: str
    target_pin_generation: int
    source_h2_pin_generation: int | None = None
    h1_rollback_pin_generation: int | None = None
    expected_target_projection_digest: str | None = None

    def __post_init__(self) -> None:
        valid_contracts = {
            "company_public_h1_v1",
            H2_PRESENTATION_CONTRACT,
        }
        absent = self.expected_assignment_generation == 0
        if (
            type(self.decision_id) is not UUID
            or not _is_digest(self.decision_digest)
            or self.schema_version != "company_card_v2_rollout_decision_v1"
            or type(self.release_commit) is not str
            or len(self.release_commit) != 40
            or any(
                character not in "0123456789abcdef"
                for character in self.release_commit
            )
            or self.action not in {"activate", "rollback"}
            or self.stage
            not in {"allowlist", "percentage", "ga", "emergency_rollback"}
            or type(self.h2_indexable) is not bool
            or type(self.target_count) is not int
            or not 1 <= self.target_count <= 1000
            or self.reason_code
            not in {
                "activate_allowlist",
                "activate_percentage",
                "activate_ga",
                "rollback_emergency_rollback",
            }
            or type(self.expected_assignment_generation) is not int
            or self.expected_assignment_generation < 0
            or type(self.subject_id) is not UUID
            or type(self.inn) is not str
            or len(self.inn) not in {10, 12}
            or not self.inn.isascii()
            or not self.inn.isdigit()
            or self.expected_current_contract not in valid_contracts | {None}
            or self.target_contract not in valid_contracts
            or type(self.target_pin_generation) is not int
            or self.target_pin_generation <= 0
            or absent
            != (
                self.expected_current_contract is None
                and self.expected_current_pin_generation is None
            )
            or (
                not absent
                and (
                    type(self.expected_current_pin_generation) is not int
                    or self.expected_current_pin_generation <= 0
                )
            )
        ):
            raise ValueError("rollout assignment command is invalid")
        if self.target_contract == H2_PRESENTATION_CONTRACT:
            if (
                type(self.h1_rollback_pin_generation) is not int
                or self.h1_rollback_pin_generation <= 0
                or type(self.source_h2_pin_generation) is not int
                or self.source_h2_pin_generation <= 0
                or type(self.expected_rollout_generation) is not int
                or self.expected_rollout_generation <= 0
                or not _is_digest(self.expected_target_projection_digest)
                or self.action != "activate"
                or self.stage not in {"allowlist", "percentage", "ga"}
                or self.reason_code != f"activate_{self.stage}"
                or (self.stage == "ga" and self.h2_indexable is not True)
            ):
                raise ValueError("H2 rollout assignment command is invalid")
        elif (
            self.reason_code != "rollback_emergency_rollback"
            or self.action != "rollback"
            or self.stage != "emergency_rollback"
            or self.h2_indexable is not False
            or self.expected_rollout_generation is not None
            or self.source_h2_pin_generation is not None
            or self.h1_rollback_pin_generation is not None
            or self.expected_target_projection_digest is not None
        ):
            raise ValueError("H1 rollback assignment command is invalid")

    def __repr__(self) -> str:
        return (
            "<RolloutAssignmentCommand "
            f"decision_id={self.decision_id!s} reason_code={self.reason_code!r}>"
        )


@dataclass(frozen=True)
class RolloutAssignmentOutcome:
    code: str
    assignment_id: UUID | None
    assignment_generation: int
    presentation_contract: str
    pin_generation: int


@dataclass(frozen=True)
class _H1AssignmentIdentity:
    subject_id: UUID
    presentation_contract: str
    pin_generation: int


@dataclass(frozen=True)
class _H1PublicationIdentity:
    publication: CompanyReportPublication
    subject: CompanyReportSubject
    report: CompanyReportRecord


def _validate_h1_rollout_pin(
    *,
    subject: CompanyReportSubject,
    pin: CompanyReportPresentationPin,
    report: CompanyReportRecord | None,
) -> None:
    """Apply the shared complete H1 public predicate to an exact immutable pin."""
    if (
        report is None
        or pin.subject_id != subject.id
        or pin.presentation_contract != "company_public_h1_v1"
        or pin.projection_scope is not None
        or pin.report_id != report.id
        or pin.snapshot_hash != report.snapshot_hash
        or pin.indexable is not True
        or pin.projection_digest is not None
        or pin.narrative_binding_status is not None
        or pin.narrative_binding_kind is not None
        or pin.narrative_binding_key is not None
        or pin.chart_facts_version is not None
        or pin.chart_facts_hash is not None
        or pin.evidence_registry_version is not None
        or report.subject_id != subject.id
        or report.writer_profile != "h1_legacy_writer_v2"
        or report.presentation_contract != "company_public_h1_v1"
        or report.rollout_generation != 0
        or report.report_version not in {"1", "2"}
    ):
        raise PresentationAssignmentConflict("H1 rollout pin lineage is invalid")
    # Local import avoids making the public resolver depend on this persistence
    # module while reusing its canonical pure validation rules byte-for-byte.
    from product_api.company_reports.public_h1_service import (
        validate_assigned_public_h1,
    )

    try:
        dto = validate_assigned_public_h1(
            subject,
            _H1AssignmentIdentity(
                subject_id=subject.id,
                presentation_contract="company_public_h1_v1",
                pin_generation=pin.generation,
            ),
            pin,
            report,
        )
    except Exception as exc:
        raise PresentationAssignmentConflict(
            "H1 rollout pin projection is invalid"
        ) from exc
    if dto.indexable is not True or dto.canonical_path != pin.canonical_path:
        raise PresentationAssignmentConflict("H1 rollout pin projection is invalid")


def _validate_active_h1_publication(
    *,
    subject: CompanyReportSubject,
    publication: CompanyReportPublication,
    report: CompanyReportRecord | None,
) -> bool:
    """Return whether the no-assignment legacy document is valid/indexable."""
    if report is None:
        raise PresentationAssignmentConflict("active H1 publication is invalid")
    from product_api.company_reports.public_h1_service import (
        validate_active_publication,
    )

    try:
        dto = validate_active_publication(
            _H1PublicationIdentity(
                publication=publication,
                subject=subject,
                report=report,
            )
        )
    except Exception as exc:
        raise PresentationAssignmentConflict(
            "active H1 publication is invalid"
        ) from exc
    return dto.indexable is True


async def _validate_unassigned_h1_predecessor(
    session: AsyncSession,
    *,
    subject: CompanyReportSubject,
    publication: CompanyReportPublication | None,
    rollback_pin: CompanyReportPresentationPin,
    rollback_report: CompanyReportRecord | None,
) -> bool:
    """Bind an absent-assignment activation to the canonical legacy H1."""

    _validate_h1_rollout_pin(
        subject=subject,
        pin=rollback_pin,
        report=rollback_report,
    )
    from product_api.company_reports.persistence.public_h1 import (
        list_report_resolution_records,
    )
    from product_api.company_reports.public_h1_service import resolve_public_h1

    try:
        resolved = await resolve_public_h1(
            session, inn=subject.normalized_identifier
        )
        candidates = await list_report_resolution_records(
            session, subject.normalized_identifier
        )
    except Exception as exc:
        raise PresentationAssignmentConflict(
            "unassigned H1 predecessor is invalid"
        ) from exc
    if (
        not candidates
        or candidates[0].report.id != resolved.report_id
        or resolved.report_id != rollback_pin.report_id
        or resolved.canonical_path != rollback_pin.canonical_path
        or rollback_pin.published_lastmod is None
        or resolved.checked_at.astimezone(timezone.utc)
        != rollback_pin.published_lastmod.astimezone(timezone.utc)
    ):
        raise PresentationAssignmentConflict(
            "unassigned H1 predecessor conflicts"
        )
    if publication is not None and publication.status == "active":
        if (
            resolved.projection_scope != "published"
            or resolved.indexable is not True
            or publication.indexable is not True
            or publication.report_id != rollback_pin.report_id
            or publication.snapshot_hash != rollback_pin.snapshot_hash
            or publication.policy_version
            != rollback_pin.publication_policy_version
            or publication.canonical_path != rollback_pin.canonical_path
            or publication.published_lastmod is None
            or publication.published_lastmod.astimezone(timezone.utc)
            != rollback_pin.published_lastmod.astimezone(timezone.utc)
            or not _validate_active_h1_publication(
                subject=subject,
                publication=publication,
                report=rollback_report,
            )
        ):
            raise PresentationAssignmentConflict(
                "unassigned H1 publication conflicts"
            )
        return True
    if (
        resolved.projection_scope != "latest_unpublished"
        or resolved.indexable is not False
    ):
        raise PresentationAssignmentConflict(
            "unassigned H1 predecessor conflicts"
        )
    return False


async def bind_rollout_decision(
    session: AsyncSession,
    *,
    decision_id: UUID,
    decision_digest: str,
    schema_version: str,
    release_commit: str,
    action: str,
    stage: str,
    target_contract: str,
    h2_indexable: bool,
    target_count: int,
) -> CompanyCardV2RolloutDecision:
    """Insert or compare the one global non-sensitive decision binding."""
    values = (
        decision_digest,
        schema_version,
        release_commit,
        action,
        stage,
        target_contract,
        h2_indexable,
        target_count,
    )
    if (
        not _is_digest(decision_digest)
        or schema_version != "company_card_v2_rollout_decision_v1"
        or not isinstance(release_commit, str)
        or len(release_commit) != 40
        or any(character not in "0123456789abcdef" for character in release_commit)
        or action not in {"activate", "rollback"}
        or (
            action == "activate"
            and (
                stage not in {"allowlist", "percentage", "ga"}
                or target_contract != H2_PRESENTATION_CONTRACT
                or (stage == "ga" and h2_indexable is not True)
            )
        )
        or (
            action == "rollback"
            and (
                stage != "emergency_rollback"
                or target_contract != "company_public_h1_v1"
                or h2_indexable is not False
            )
        )
        or type(h2_indexable) is not bool
        or type(target_count) is not int
        or not 1 <= target_count <= 1000
    ):
        raise PresentationAssignmentConflict("rollout decision binding is invalid")
    statement = (
        select(CompanyCardV2RolloutDecision)
        .where(
            or_(
                CompanyCardV2RolloutDecision.decision_id == decision_id,
                CompanyCardV2RolloutDecision.decision_digest == decision_digest,
            )
        )
        .with_for_update()
    )

    async def locked_match() -> CompanyCardV2RolloutDecision | None:
        bindings = list((await session.scalars(statement)).all())
        if not bindings:
            return None
        if (
            len(bindings) != 1
            or bindings[0].decision_id != decision_id
            or bindings[0].decision_digest != decision_digest
        ):
            raise PresentationAssignmentConflict(
                "rollout decision identity conflicts"
            )
        return bindings[0]

    binding = await locked_match()
    if binding is None:
        candidate = CompanyCardV2RolloutDecision(
            decision_id=decision_id,
            decision_digest=decision_digest,
            schema_version=schema_version,
            release_commit=release_commit,
            action=action,
            stage=stage,
            target_contract=target_contract,
            h2_indexable=h2_indexable,
            target_count=target_count,
        )
        try:
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
        except IntegrityError as exc:
            # The savepoint preserves the caller-owned binding transaction.
            # Re-read both unique identities after the winner commits and
            # convert every mismatch to the same closed domain conflict.
            binding = await locked_match()
            if binding is None:
                raise PresentationAssignmentConflict(
                    "rollout decision insert conflicts"
                ) from exc
        else:
            binding = candidate
    current = (
        binding.decision_digest,
        binding.schema_version,
        binding.release_commit,
        binding.action,
        binding.stage,
        binding.target_contract,
        binding.h2_indexable,
        binding.target_count,
    )
    if current != values:
        raise PresentationAssignmentConflict("rollout decision binding conflicts")
    return binding


async def resolve_presentation_lifecycle(
    session: AsyncSession,
    presentation_id: UUID,
) -> ResolvedPresentationLifecycle:
    """Resolve one opaque presentation's exact immutable lifecycle tuple."""
    statement = (
        select(
            CompanyReportPresentation,
            CompanyReportRecord,
            CompanyReportSubject,
        )
        .outerjoin(
            CompanyReportRecord,
            and_(
                CompanyReportRecord.id == CompanyReportPresentation.report_id,
                CompanyReportRecord.subject_id
                == CompanyReportPresentation.subject_id,
            ),
        )
        .outerjoin(
            CompanyReportSubject,
            and_(
                CompanyReportSubject.id == CompanyReportPresentation.subject_id,
                CompanyReportSubject.id == CompanyReportRecord.subject_id,
            ),
        )
        .where(CompanyReportPresentation.id == presentation_id)
        .execution_options(autoflush=False)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise PresentationLifecycleNotFound("presentation does not exist")

    presentation, report, subject = row
    if report is None or subject is None:
        raise PresentationLifecycleInvalid("presentation binding is incomplete")

    normalized_identifier = subject.normalized_identifier
    valid_identifier = (
        isinstance(normalized_identifier, str)
        and normalized_identifier.isascii()
        and normalized_identifier.isdigit()
        and len(normalized_identifier) in {10, 12}
    )
    valid_generation = (
        type(presentation.rollout_generation) is int
        and type(report.rollout_generation) is int
        and presentation.rollout_generation == report.rollout_generation
        and presentation.rollout_generation > 0
    )
    if (
        presentation.id != presentation_id
        or presentation.subject_id != report.subject_id
        or presentation.subject_id != subject.id
        or presentation.report_id != report.id
        or presentation.presentation_contract != report.presentation_contract
        or presentation.presentation_contract != H2_PRESENTATION_CONTRACT
        or not valid_generation
        or report.writer_profile != H2_WRITER_PROFILE
        or report.report_version != "3"
        or report.lifecycle_status not in {"pending", "complete", "partial", "failed"}
        or not valid_identifier
    ):
        raise PresentationLifecycleInvalid("presentation binding is invalid")

    return ResolvedPresentationLifecycle(
        presentation_id=presentation.id,
        presentation_contract=presentation.presentation_contract,
        report_id=report.id,
        lifecycle_status=report.lifecycle_status,
        normalized_identifier=normalized_identifier,
    )


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
            and (
                existing.projection_scope is None
                if contract != H2_PRESENTATION_CONTRACT
                else existing.projection_scope
                in {None, H2_STAGED_PROJECTION_SCOPE}
            )
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
            projection_scope=H2_STAGED_PROJECTION_SCOPE,
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
            projection_scope=None,
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
            or pin.projection_scope not in {None, H2_STAGED_PROJECTION_SCOPE}
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
            or pin.projection_scope not in {None, H2_STAGED_PROJECTION_SCOPE}
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
    if (
        pin.subject_id != subject_id
        or pin.presentation_contract != H2_PRESENTATION_CONTRACT
        or expected_generation != pin.generation
        or pin.projection_scope not in {None, H2_STAGED_PROJECTION_SCOPE}
        or pin.indexable is not False
        or pin.canonical_path is not None
        or pin.published_lastmod is not None
    ):
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
        or predecessor.projection_scope not in {None, H2_STAGED_PROJECTION_SCOPE}
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
            and existing.projection_scope in {None, H2_STAGED_PROJECTION_SCOPE}
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
        projection_scope=H2_STAGED_PROJECTION_SCOPE,
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


async def _plan_active_h2_pin_locked(
    session: AsyncSession,
    *,
    subject: CompanyReportSubject,
    pins: list[CompanyReportPresentationPin],
    report: CompanyReportRecord,
    source_pin: CompanyReportPresentationPin,
    expected_generation: int,
    projection_digest: str,
    canonical_path: str,
    indexable: bool,
    published_lastmod: datetime,
) -> CompanyReportPresentationPin:
    """Validate and plan one active H2 row in an already locked target context.

    The caller owns the subject-first lock and the complete ordered pin lock.
    A byte-identical active row may be reused; a new row remains transient until
    the caller has validated the complete CAS and is ready to append it beside
    the assignment/journal mutation.
    """
    if (
        source_pin.presentation_contract != H2_PRESENTATION_CONTRACT
        or source_pin.projection_scope not in {None, H2_STAGED_PROJECTION_SCOPE}
        or source_pin.indexable is not False
        or source_pin.canonical_path is not None
        or source_pin.published_lastmod is not None
        or source_pin.narrative_binding_status != "resolved"
        or source_pin.narrative_binding_kind not in {"artifact", "fallback"}
        or not _is_digest(source_pin.narrative_binding_key)
        or not _is_digest(source_pin.projection_digest)
        or source_pin.publication_policy_version != H2_PUBLICATION_POLICY_V3
        or type(expected_generation) is not int
        or expected_generation <= 0
        or not _is_digest(projection_digest)
        or projection_digest == source_pin.projection_digest
        or type(canonical_path) is not str
        or not canonical_path.startswith("/company/")
        or "?" in canonical_path
        or "#" in canonical_path
        or len(canonical_path) > 2048
        or type(indexable) is not bool
        or not isinstance(published_lastmod, datetime)
    ):
        raise PresentationAssignmentConflict("active H2 pin input is invalid")

    if (
        source_pin.subject_id != subject.id
        or source_pin.report_id != report.id
        or canonical_path == f"/company/{subject.normalized_identifier}"
        or not canonical_path.startswith(
            f"/company/{subject.normalized_identifier}-"
        )
    ):
        raise PresentationAssignmentConflict("active H2 pin subject is invalid")

    locked_source = next(
        (
            pin
            for pin in pins
            if pin.presentation_contract == H2_PRESENTATION_CONTRACT
            and pin.generation == source_pin.generation
        ),
        None,
    )
    if locked_source is None or any(
        getattr(locked_source, field) != getattr(source_pin, field)
        for field in (
            "report_id",
            "snapshot_hash",
            "projection_scope",
            "projection_digest",
            "narrative_binding_status",
            "narrative_binding_kind",
            "narrative_binding_key",
            "chart_facts_version",
            "chart_facts_hash",
            "evidence_registry_version",
            "publication_policy_version",
        )
    ):
        raise PresentationAssignmentConflict("active H2 source pin conflicts")

    locked_report = await session.get(
        CompanyReportRecord,
        report.id,
        with_for_update=True,
    )
    if locked_report is None:
        raise PresentationAssignmentConflict("active H2 report is missing")
    try:
        snapshot = company_card_v2_from_snapshot(
            deepcopy(locked_report.normalized_snapshot)
        )
    except Exception as exc:
        raise PresentationAssignmentConflict("active H2 snapshot is invalid") from exc
    _validate_h2_snapshot_policy(
        locked_report,
        snapshot,
        H2_PUBLICATION_POLICY_V3,
    )
    if (
        locked_report.subject_id != subject.id
        or locked_report.report_version != "3"
        or locked_report.writer_profile != H2_WRITER_PROFILE
        or locked_report.presentation_contract != H2_PRESENTATION_CONTRACT
        or locked_report.lifecycle_status not in {"complete", "partial"}
        or (indexable and locked_report.lifecycle_status != "complete")
        or locked_report.generated_at is None
        or locked_report.generated_at != published_lastmod
        or locked_report.snapshot_hash != locked_source.snapshot_hash
        or snapshot.report_id != str(locked_report.id)
        or snapshot.subject_inn != subject.normalized_identifier
        or snapshot.target_inn != subject.normalized_identifier
        or snapshot.rollout_config_generation != locked_report.rollout_generation
        or calculate_company_card_v2_snapshot_hash(snapshot)
        != locked_report.snapshot_hash
    ):
        raise PresentationAssignmentConflict("active H2 report lineage is invalid")

    if locked_source.narrative_binding_kind is None or locked_source.narrative_binding_key is None:
        raise PresentationAssignmentConflict("active H2 narrative binding is invalid")
    artifact = await session.scalar(
        select(CompanyCardNarrativeArtifact)
        .where(
            CompanyCardNarrativeArtifact.binding_kind
            == locked_source.narrative_binding_kind,
            CompanyCardNarrativeArtifact.binding_key
            == locked_source.narrative_binding_key,
        )
        .with_for_update()
    )
    if (
        artifact is None
        or artifact.report_id != locked_report.id
        or artifact.snapshot_hash != locked_report.snapshot_hash
        or not _has_exact_artifact_binding(artifact)
    ):
        raise PresentationAssignmentConflict("active H2 artifact lineage is invalid")

    presentation = await session.scalar(
        select(CompanyReportPresentation)
        .where(
            CompanyReportPresentation.subject_id == subject.id,
            CompanyReportPresentation.report_id == locked_report.id,
            CompanyReportPresentation.presentation_contract
            == H2_PRESENTATION_CONTRACT,
        )
        .with_for_update()
    )
    narrative_job = await session.scalar(
        select(CompanyCardNarrativeJob)
        .where(
            CompanyCardNarrativeJob.artifact_id == artifact.id,
            CompanyCardNarrativeJob.generation_key == artifact.generation_key,
        )
        .with_for_update()
    )
    if presentation is None or narrative_job is None:
        raise PresentationAssignmentConflict("active H2 saved result is invalid")

    # The pure rebind must reproduce the command's exact active digest before
    # the caller may append this transient row beside assignment CAS.
    from product_api.company_reports.company_card_v2.service import (
        ExactPublicH2Dependencies,
        build_active_public_h2_for_pin,
    )

    try:
        active_projection = await build_active_public_h2_for_pin(
            session,
            record=locked_report,
            source_pin=locked_source,
            expected_subject_id=subject.id,
            expected_inn=subject.normalized_identifier,
            canonical_path=canonical_path,
            indexable=indexable,
            published_lastmod=published_lastmod,
            dependencies=ExactPublicH2Dependencies(
                presentation=presentation,
                narrative_job=narrative_job,
                narrative_artifact=artifact,
            ),
        )
    except Exception as exc:
        raise PresentationAssignmentConflict(
            "active H2 saved result is invalid"
        ) from exc
    if (
        active_projection.projection_digest != projection_digest
        or active_projection.canonical_path != canonical_path
        or active_projection.indexable is not indexable
    ):
        raise PresentationAssignmentConflict(
            "active H2 projection binding is invalid"
        )

    expected_values = (
        locked_report.id,
        locked_report.snapshot_hash,
        H2_ACTIVE_PROJECTION_SCOPE,
        locked_source.chart_facts_version,
        locked_source.chart_facts_hash,
        locked_source.evidence_registry_version,
        locked_source.publication_policy_version,
        canonical_path,
        indexable,
        published_lastmod,
        projection_digest,
        "resolved",
        locked_source.narrative_binding_kind,
        locked_source.narrative_binding_key,
    )
    exact_existing = []
    existing_at_generation = None
    for candidate in pins:
        if candidate.presentation_contract != H2_PRESENTATION_CONTRACT:
            continue
        if candidate.generation == expected_generation:
            existing_at_generation = candidate
        candidate_values = (
            candidate.report_id,
            candidate.snapshot_hash,
            candidate.projection_scope,
            candidate.chart_facts_version,
            candidate.chart_facts_hash,
            candidate.evidence_registry_version,
            candidate.publication_policy_version,
            candidate.canonical_path,
            candidate.indexable,
            candidate.published_lastmod,
            candidate.projection_digest,
            candidate.narrative_binding_status,
            candidate.narrative_binding_kind,
            candidate.narrative_binding_key,
        )
        if candidate_values == expected_values:
            exact_existing.append(candidate)
    if len(exact_existing) > 1:
        raise PresentationAssignmentConflict("active H2 pin identity is duplicated")
    if exact_existing:
        existing = exact_existing[0]
        if existing.generation != expected_generation:
            raise PresentationAssignmentConflict("active H2 pin generation conflicts")
        return existing
    if existing_at_generation is not None:
        raise PresentationAssignmentConflict("active H2 pin generation conflicts")

    next_generation = max(
        (
            pin.generation
            for pin in pins
            if pin.presentation_contract == H2_PRESENTATION_CONTRACT
        ),
        default=0,
    ) + 1
    if expected_generation != next_generation:
        raise PresentationAssignmentConflict("active H2 pin generation conflicts")
    pin = CompanyReportPresentationPin(
        subject_id=subject.id,
        report_id=locked_report.id,
        presentation_contract=H2_PRESENTATION_CONTRACT,
        generation=expected_generation,
        snapshot_hash=locked_report.snapshot_hash,
        chart_facts_version=locked_source.chart_facts_version,
        chart_facts_hash=locked_source.chart_facts_hash,
        evidence_registry_version=locked_source.evidence_registry_version,
        publication_policy_version=locked_source.publication_policy_version,
        projection_scope=H2_ACTIVE_PROJECTION_SCOPE,
        canonical_path=canonical_path,
        indexable=indexable,
        published_lastmod=published_lastmod,
        projection_digest=projection_digest,
        narrative_binding_status="resolved",
        narrative_binding_kind=locked_source.narrative_binding_kind,
        narrative_binding_key=locked_source.narrative_binding_key,
    )
    return pin


async def assign_rollout_pin_cas(
    session: AsyncSession,
    *,
    command: RolloutAssignmentCommand,
) -> RolloutAssignmentOutcome:
    """Switch one exact assignment with subject-first CAS and durable audit."""
    subject = await session.get(
        CompanyReportSubject,
        command.subject_id,
        with_for_update=True,
    )
    if subject is None or subject.normalized_identifier != command.inn:
        raise PresentationAssignmentConflict("assignment subject is missing")

    assignment = await session.scalar(
        select(CompanyReportPresentationAssignment)
        .where(
            CompanyReportPresentationAssignment.subject_id == command.subject_id
        )
        .with_for_update()
    )
    journal = await session.scalar(
        select(CompanyReportPresentationAssignmentJournal)
        .where(
            CompanyReportPresentationAssignmentJournal.subject_id
            == command.subject_id,
            CompanyReportPresentationAssignmentJournal.decision_digest
            == command.decision_digest,
        )
        .with_for_update()
    )
    bindings = list(
        (
            await session.scalars(
                select(CompanyCardV2RolloutDecision).where(
                    or_(
                        CompanyCardV2RolloutDecision.decision_id
                        == command.decision_id,
                        CompanyCardV2RolloutDecision.decision_digest
                        == command.decision_digest,
                    )
                )
            )
        ).all()
    )
    expected_binding = (
        command.decision_digest,
        command.schema_version,
        command.release_commit,
        command.action,
        command.stage,
        command.target_contract,
        command.h2_indexable,
        command.target_count,
    )
    if (
        len(bindings) != 1
        or bindings[0].decision_id != command.decision_id
        or (
            bindings[0].decision_digest,
            bindings[0].schema_version,
            bindings[0].release_commit,
            bindings[0].action,
            bindings[0].stage,
            bindings[0].target_contract,
            bindings[0].h2_indexable,
            bindings[0].target_count,
        )
        != expected_binding
    ):
        raise PresentationAssignmentConflict("rollout decision binding conflicts")
    if journal is not None:
        if (
            assignment is None
            or journal.assignment_id != assignment.id
            or journal.decision_id != command.decision_id
            or journal.reason_code != command.reason_code
            or journal.presentation_contract != command.target_contract
            or journal.pin_generation != command.target_pin_generation
        ):
            raise PresentationAssignmentConflict("rollout journal identity conflicts")
        if (
            assignment.generation == journal.generation
            and assignment.presentation_contract == journal.presentation_contract
            and assignment.pin_generation == journal.pin_generation
        ):
            return RolloutAssignmentOutcome(
                code="applied_current",
                assignment_id=assignment.id,
                assignment_generation=assignment.generation,
                presentation_contract=assignment.presentation_contract,
                pin_generation=assignment.pin_generation,
            )
        raise PresentationAssignmentConflict("decision_superseded")

    if assignment is None:
        current_generation = 0
        current_contract = None
        current_pin_generation = None
    else:
        current_generation = assignment.generation
        current_contract = assignment.presentation_contract
        current_pin_generation = assignment.pin_generation
    if (
        current_generation != command.expected_assignment_generation
        or current_contract != command.expected_current_contract
        or current_pin_generation != command.expected_current_pin_generation
    ):
        raise PresentationAssignmentConflict("assignment generation conflicts")

    legacy_publication = None
    locked_h1_reports: list[CompanyReportRecord] = []
    if assignment is None:
        legacy_publication = await session.scalar(
            select(CompanyReportPublication)
            .where(CompanyReportPublication.subject_id == command.subject_id)
            .with_for_update()
        )
        # Freeze every row that can participate in the legacy latest-H1
        # resolver.  Together with the subject lock this serializes both
        # completion of an existing report and creation/publication of a new
        # predecessor against the first H2 assignment.
        locked_h1_reports = list(
            (
                await session.scalars(
                    select(CompanyReportRecord)
                    .where(
                        CompanyReportRecord.subject_id == command.subject_id,
                        CompanyReportRecord.writer_profile
                        == "h1_legacy_writer_v2",
                        CompanyReportRecord.presentation_contract
                        == "company_public_h1_v1",
                        CompanyReportRecord.rollout_generation == 0,
                    )
                    .order_by(CompanyReportRecord.id)
                    .with_for_update()
                )
            ).all()
        )

    pins = list(
        (
            await session.scalars(
                select(CompanyReportPresentationPin)
                .where(CompanyReportPresentationPin.subject_id == command.subject_id)
                .order_by(
                    CompanyReportPresentationPin.presentation_contract,
                    CompanyReportPresentationPin.generation,
                )
                .with_for_update()
            )
        ).all()
    )
    current_pin = None
    if assignment is not None:
        current_pin = next(
            (
                pin
                for pin in pins
                if pin.presentation_contract == assignment.presentation_contract
                and pin.generation == assignment.pin_generation
            ),
            None,
        )
        if current_pin is None:
            raise PresentationAssignmentConflict("current assignment pin is missing")

    rollback_pin = None
    source_h2_pin = None
    if command.target_contract == H2_PRESENTATION_CONTRACT:
        source_h2_pin = next(
            (
                pin
                for pin in pins
                if pin.presentation_contract == H2_PRESENTATION_CONTRACT
                and pin.generation == command.source_h2_pin_generation
            ),
            None,
        )
        rollback_pin = next(
            (
                pin
                for pin in pins
                if pin.presentation_contract == "company_public_h1_v1"
                and pin.generation == command.h1_rollback_pin_generation
            ),
            None,
        )
        if source_h2_pin is None or rollback_pin is None:
            raise PresentationAssignmentConflict("H2 assignment lineage is invalid")
        source_report = await session.get(
            CompanyReportRecord,
            source_h2_pin.report_id,
            with_for_update=True,
        )
        if source_report is None:
            raise PresentationAssignmentConflict("assignment target report is invalid")
        target_pin = await _plan_active_h2_pin_locked(
            session,
            subject=subject,
            pins=pins,
            report=source_report,
            source_pin=source_h2_pin,
            expected_generation=command.target_pin_generation,
            projection_digest=command.expected_target_projection_digest,
            canonical_path=f"/company/{command.inn}-company",
            indexable=command.h2_indexable,
            published_lastmod=source_report.generated_at,
        )
    else:
        target_pin = next(
            (
                pin
                for pin in pins
                if pin.presentation_contract == command.target_contract
                and pin.generation == command.target_pin_generation
            ),
            None,
        )
        if target_pin is None:
            raise PresentationAssignmentConflict("assignment target pin is missing")

    report_ids = {target_pin.report_id}
    if source_h2_pin is not None:
        report_ids.add(source_h2_pin.report_id)
    if rollback_pin is not None:
        report_ids.add(rollback_pin.report_id)
    if current_pin is not None and current_pin.presentation_contract == "company_public_h1_v1":
        report_ids.add(current_pin.report_id)
    if legacy_publication is not None and legacy_publication.status == "active":
        report_ids.add(legacy_publication.report_id)
    reports: dict[UUID, CompanyReportRecord | None] = {
        report.id: report for report in locked_h1_reports
    }
    for report_id in sorted(report_ids, key=str):
        if report_id not in reports:
            reports[report_id] = await session.get(
                CompanyReportRecord,
                report_id,
                with_for_update=True,
            )

    target_report = reports.get(target_pin.report_id)
    if (
        target_report is None
        or target_report.subject_id != command.subject_id
        or target_report.snapshot_hash != target_pin.snapshot_hash
        or target_report.lifecycle_status not in {"complete", "partial"}
    ):
        raise PresentationAssignmentConflict("assignment target report is invalid")

    current_h1_indexable = False
    if current_pin is not None and current_pin.presentation_contract == "company_public_h1_v1":
        _validate_h1_rollout_pin(
            subject=subject,
            pin=current_pin,
            report=reports.get(current_pin.report_id),
        )
        current_h1_indexable = True
    elif legacy_publication is not None and legacy_publication.status == "active":
        current_h1_indexable = _validate_active_h1_publication(
            subject=subject,
            publication=legacy_publication,
            report=reports.get(legacy_publication.report_id),
        )

    if command.target_contract == H2_PRESENTATION_CONTRACT:
        if assignment is None:
            if rollback_pin is None:
                raise PresentationAssignmentConflict(
                    "H2 assignment lineage is invalid"
                )
            current_h1_indexable = await _validate_unassigned_h1_predecessor(
                session,
                subject=subject,
                publication=legacy_publication,
                rollback_pin=rollback_pin,
                rollback_report=reports.get(rollback_pin.report_id),
            )
        if (
            target_pin.projection_scope != H2_ACTIVE_PROJECTION_SCOPE
            or target_pin.indexable is not command.h2_indexable
            or target_pin.narrative_binding_status != "resolved"
            or target_pin.canonical_path is None
            or target_pin.published_lastmod is None
            or target_pin.projection_digest
            != command.expected_target_projection_digest
            or rollback_pin is None
            or source_h2_pin is None
            or rollback_pin.indexable is not True
            or rollback_pin.projection_scope is not None
            or source_h2_pin.projection_scope
            not in {None, H2_STAGED_PROJECTION_SCOPE}
            or source_h2_pin.indexable is not False
            or source_h2_pin.canonical_path is not None
            or source_h2_pin.published_lastmod is not None
            or source_h2_pin.narrative_binding_status != "resolved"
            or source_h2_pin.report_id != target_pin.report_id
            or source_h2_pin.snapshot_hash != target_pin.snapshot_hash
            or source_h2_pin.chart_facts_version != target_pin.chart_facts_version
            or source_h2_pin.chart_facts_hash != target_pin.chart_facts_hash
            or source_h2_pin.evidence_registry_version
            != target_pin.evidence_registry_version
            or source_h2_pin.publication_policy_version
            != target_pin.publication_policy_version
            or source_h2_pin.narrative_binding_kind
            != target_pin.narrative_binding_kind
            or source_h2_pin.narrative_binding_key
            != target_pin.narrative_binding_key
            or (current_h1_indexable and target_pin.indexable is False)
        ):
            raise PresentationAssignmentConflict("H2 assignment lineage is invalid")
        _validate_h1_rollout_pin(
            subject=subject,
            pin=rollback_pin,
            report=reports.get(rollback_pin.report_id),
        )
        try:
            snapshot = company_card_v2_from_snapshot(
                deepcopy(target_report.normalized_snapshot)
            )
        except Exception as exc:
            raise PresentationAssignmentConflict(
                "H2 assignment snapshot is invalid"
            ) from exc
        _validate_h2_snapshot_policy(
            target_report,
            snapshot,
            H2_PUBLICATION_POLICY_V3,
        )
        if (
            target_report.report_version != "3"
            or target_report.writer_profile != H2_WRITER_PROFILE
            or target_report.presentation_contract != H2_PRESENTATION_CONTRACT
            or target_report.rollout_generation
            != command.expected_rollout_generation
            or (target_pin.indexable and target_report.lifecycle_status != "complete")
            or target_report.generated_at != target_pin.published_lastmod
            or snapshot.report_id != str(target_report.id)
            or snapshot.subject_inn != subject.normalized_identifier
            or snapshot.target_inn != subject.normalized_identifier
            or snapshot.rollout_config_generation != target_report.rollout_generation
            or calculate_company_card_v2_snapshot_hash(snapshot)
            != target_report.snapshot_hash
        ):
            raise PresentationAssignmentConflict("H2 assignment report is invalid")
        artifact = await session.scalar(
            select(CompanyCardNarrativeArtifact)
            .where(
                CompanyCardNarrativeArtifact.binding_kind
                == target_pin.narrative_binding_kind,
                CompanyCardNarrativeArtifact.binding_key
                == target_pin.narrative_binding_key,
            )
            .with_for_update()
        )
        if (
            artifact is None
            or artifact.report_id != target_report.id
            or artifact.snapshot_hash != target_report.snapshot_hash
            or not _has_exact_artifact_binding(artifact)
        ):
            raise PresentationAssignmentConflict("H2 assignment artifact is invalid")
        presentation = await session.scalar(
            select(CompanyReportPresentation)
            .where(
                CompanyReportPresentation.subject_id == subject.id,
                CompanyReportPresentation.report_id == target_report.id,
                CompanyReportPresentation.presentation_contract
                == H2_PRESENTATION_CONTRACT,
            )
            .with_for_update()
        )
        narrative_job = await session.scalar(
            select(CompanyCardNarrativeJob)
            .where(
                CompanyCardNarrativeJob.artifact_id == artifact.id,
                CompanyCardNarrativeJob.generation_key == artifact.generation_key,
            )
            .with_for_update()
        )
        if presentation is None or narrative_job is None:
            raise PresentationAssignmentConflict("H2 assignment saved result is invalid")
        from product_api.company_reports.company_card_v2.service import (
            ExactPublicH2Dependencies,
            _resolve_exact_v3,
        )

        try:
            await _resolve_exact_v3(
                session,
                target_report,
                pin=source_h2_pin,
                expected_subject_id=subject.id,
                expected_inn=subject.normalized_identifier,
                dependencies=ExactPublicH2Dependencies(
                    presentation=presentation,
                    narrative_job=narrative_job,
                    narrative_artifact=artifact,
                ),
            )
            active_projection = await _resolve_exact_v3(
                session,
                target_report,
                pin=target_pin,
                expected_subject_id=subject.id,
                expected_inn=subject.normalized_identifier,
                dependencies=ExactPublicH2Dependencies(
                    presentation=presentation,
                    narrative_job=narrative_job,
                    narrative_artifact=artifact,
                ),
            )
        except Exception as exc:
            raise PresentationAssignmentConflict(
                "H2 assignment saved result is invalid"
            ) from exc
        if active_projection.projection_digest != target_pin.projection_digest:
            raise PresentationAssignmentConflict(
                "H2 assignment projection is invalid"
            )
    else:
        if command.expected_current_contract != H2_PRESENTATION_CONTRACT:
            raise PresentationAssignmentConflict("H1 rollback lineage is invalid")
        _validate_h1_rollout_pin(
            subject=subject,
            pin=target_pin,
            report=target_report,
        )

    if (
        assignment is not None
        and assignment.presentation_contract == target_pin.presentation_contract
        and assignment.pin_generation == target_pin.generation
    ):
        return RolloutAssignmentOutcome(
            code="already_target",
            assignment_id=assignment.id,
            assignment_generation=assignment.generation,
            presentation_contract=assignment.presentation_contract,
            pin_generation=assignment.pin_generation,
        )

    if target_pin not in pins:
        session.add(target_pin)
        await session.flush()

    next_generation = current_generation + 1
    if assignment is None:
        assignment = CompanyReportPresentationAssignment(
            subject_id=command.subject_id,
            presentation_contract=target_pin.presentation_contract,
            pin_generation=target_pin.generation,
            generation=next_generation,
        )
        session.add(assignment)
        await session.flush()
    else:
        assignment.presentation_contract = target_pin.presentation_contract
        assignment.pin_generation = target_pin.generation
        assignment.generation = next_generation

    session.add(
        CompanyReportPresentationAssignmentJournal(
            assignment_id=assignment.id,
            subject_id=command.subject_id,
            presentation_contract=target_pin.presentation_contract,
            pin_generation=target_pin.generation,
            generation=next_generation,
            decision_id=command.decision_id,
            decision_digest=command.decision_digest,
            reason_code=command.reason_code,
        )
    )
    await session.flush()
    return RolloutAssignmentOutcome(
        code="applied",
        assignment_id=assignment.id,
        assignment_generation=assignment.generation,
        presentation_contract=assignment.presentation_contract,
        pin_generation=assignment.pin_generation,
    )


async def assign_pin_cas(session: AsyncSession, *, subject_id: UUID, pin: CompanyReportPresentationPin, expected_generation: int) -> CompanyReportPresentationAssignment:
    if pin.subject_id != subject_id or expected_generation != pin.generation:
        raise PresentationAssignmentConflict("assignment pin identity is invalid")
    # H2 pins are intentionally unresolved in iteration 20.  Reject before
    # locking/mutating assignment or appending a journal event.
    if pin.presentation_contract == "company_public_h2_v1":
        raise PresentationAssignmentConflict("unresolved H2 pin is not assignable")
    if pin.presentation_contract != "company_public_h1_v1":
        raise PresentationAssignmentConflict("assignment contract is invalid")
    subject = await session.get(CompanyReportSubject, subject_id, with_for_update=True)
    if subject is None:
        raise PresentationAssignmentConflict("assignment subject is missing")
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
    "H2_ACTIVE_PROJECTION_SCOPE",
    "H2_PUBLICATION_POLICY_V1",
    "H2_PUBLICATION_POLICY_V2",
    "H2_PUBLICATION_POLICY_V3",
    "H2_PUBLICATION_POLICY_VERSION",
    "H2_PUBLICATION_POLICY_VERSIONS",
    "H2_STAGED_PROJECTION_SCOPE",
    "PresentationAssignmentConflict",
    "PresentationLifecycleInvalid",
    "PresentationLifecycleNotFound",
    "ResolvedPresentationLifecycle",
    "RolloutAssignmentCommand",
    "RolloutAssignmentOutcome",
    "append_presentation_pin",
    "append_resolved_h2_pin",
    "assign_pin_cas",
    "assign_rollout_pin_cas",
    "bind_rollout_decision",
    "create_or_reuse_h2_presentation",
    "resolve_presentation_lifecycle",
    "stage_h2_pin",
]
