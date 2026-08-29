from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import timezone
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.persistence.jobs import (
    H2_PRESENTATION_CONTRACT,
    H2_WRITER_PROFILE,
    WriterDecision,
)
from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeArtifact,
    CompanyCardNarrativeJob,
    CompanyCardNarrativeOutbox,
    CompanyReportH2LifecycleHead,
    CompanyReportPresentation,
    CompanyReportPresentationAssignment,
    CompanyReportPresentationPin,
    CompanyReportPresentationStagedPointer,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.presentations import (
    H2_PUBLICATION_POLICY_V1,
    H2_PUBLICATION_POLICY_V2,
    H2_PUBLICATION_POLICY_V3,
)
from product_api.company_reports.persistence.v3 import (
    calculate_company_card_v2_snapshot_hash,
    company_card_v2_from_snapshot,
    validate_company_card_v2_finalization,
)
from product_api.company_reports.persistence.serialization import calculate_company_report_snapshot_hash, company_report_from_snapshot
from .canonical_json import canonical_json_bytes
from .models import (
    CompanyCardV2SnapshotV1,
    CompanyCardV2SnapshotV2,
    CompanyCardV2SnapshotV3,
)
from .narrative.catalog import (
    CONNECTOR_CATALOG_VERSION,
    EVIDENCE_BY_STATEMENT,
    FALLBACK_CATALOG_VERSION,
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
    FROZEN_V3_SNAPSHOT_VERSION,
    GATEWAY_PROFILE_VERSION,
    INPUT_SCHEMA_VERSION,
    INSIGHT_CATALOG_VERSION,
    LEGACY_SNAPSHOT_VERSIONS,
    NARRATIVE_EVIDENCE_ABSENT,
    NOT_APPLICABLE,
    OUTPUT_SCHEMA_VERSION,
    POLICY_VERSION,
    PROMPT_VERSION,
    PUBLIC_STATEMENT_IDS,
    RENDERER_VERSION,
    STATEMENT_CATALOG_VERSION,
    TEMPLATE_CATALOG_VERSION,
)
from .narrative.identity import (
    ArtifactIdentityV1,
    FallbackIdentityV1,
    GenerationIdentityV2,
    identity_key,
)
from .narrative.models import NarrativeEvidenceEnvelope, RenderPlan
from .narrative.validation import normalize_text, validate_render_plan
from .public_h2 import (
    EMPTY_CHART_FACTS_HASH,
    LegacySnapshotBinding,
    PublicH2ProjectionBindingV1,
    build_legacy_public_h2,
    build_public_h2,
    rebind_public_h2_projection,
)
from .public_h2_models import CompanyPublicH2Response, PublicH2Narrative


class PublicH2Error(RuntimeError):
    code = "company_public_h2_unavailable"


class PublicH2NotFound(PublicH2Error):
    code = "company_report_not_found"


class PublicH2Invalid(PublicH2Error):
    code = "public_projection_invalid"


class PublicH2NotEligible(PublicH2Error):
    code = "report_not_eligible"


class PublicH2Pending(PublicH2NotEligible):
    code = "report_pending"


class PublicH2Failed(PublicH2NotEligible):
    code = "report_failed"


@dataclass(frozen=True)
class ExactPublicH2Dependencies:
    """Dependency tuple captured by the same sitemap overlay SELECT."""

    presentation: CompanyReportPresentation | None
    narrative_job: CompanyCardNarrativeJob | None
    narrative_artifact: CompanyCardNarrativeArtifact | None


def h2_cohort_selected(*, inn: str, settings: object) -> bool:
    """Return the immutable server-side H2 cohort decision.

    No request-controlled input is accepted here.  Bad/missing configuration
    is deliberately a no-H2 decision rather than a permissive fallback.
    """
    try:
        if not getattr(settings, "company_card_v2_presentations_enabled"):
            return False
        generation = getattr(settings, "company_card_v2_rollout_generation")
        allowlist = getattr(settings, "company_card_v2_allowlist_inns")
        percentage = getattr(settings, "company_card_v2_percentage_basis_points")
        if not isinstance(generation, int) or generation <= 0 or not isinstance(percentage, int) or not 0 <= percentage <= 10000:
            return False
        if not isinstance(allowlist, list) or not inn.isascii() or not inn.isdigit() or len(inn) not in {10, 12}:
            return False
        if inn in allowlist:
            return True
        bucket = int.from_bytes(hashlib.sha256(("company-card-v2-cohort-v1\0" + inn).encode("utf-8")).digest()[:8], "big") % 10000
        return bucket < percentage
    except (AttributeError, TypeError, ValueError):
        return False


async def resolve_public_h2(session: AsyncSession, *, inn: str) -> CompanyPublicH2Response:
    subject = await session.scalar(select(CompanyReportSubject).where(CompanyReportSubject.normalized_identifier == inn))
    if subject is None:
        raise PublicH2NotFound("company card v2 was not found")
    for pointer_model in (CompanyReportPresentationAssignment, CompanyReportPresentationStagedPointer):
        pointer = await session.scalar(select(pointer_model).where(
            pointer_model.subject_id == subject.id,
            pointer_model.presentation_contract == "company_public_h2_v1",
        ))
        if pointer is not None:
            pin_generation = (
                pointer.pin_generation
                if isinstance(pointer, CompanyReportPresentationAssignment)
                else pointer.generation
            )
            pin = await session.scalar(select(CompanyReportPresentationPin).where(
                CompanyReportPresentationPin.subject_id == subject.id,
                CompanyReportPresentationPin.presentation_contract == "company_public_h2_v1",
                CompanyReportPresentationPin.generation == pin_generation,
            ))
            if pin is None:
                raise PublicH2Invalid("company card v2 binding is invalid")
            scope = getattr(pin, "projection_scope", None)
            if isinstance(pointer, CompanyReportPresentationStagedPointer):
                if scope not in {None, "staged_publication"} or not _is_staged_pin_shape(pin):
                    raise PublicH2Invalid("company card v2 staged binding is invalid")
            elif not (
                scope == "active_publication"
                or (scope is None and _is_staged_pin_shape(pin))
            ):
                raise PublicH2Invalid("company card v2 assignment is not active")
            record = await session.get(CompanyReportRecord, pin.report_id)
            return await _resolve_exact_v3(
                session,
                record,
                pin=pin,
                expected_subject_id=subject.id,
                expected_inn=inn,
            )
    head = await session.get(CompanyReportH2LifecycleHead, subject.id)
    if head is not None:
        presentation = await session.get(CompanyReportPresentation, head.presentation_id)
        if presentation is None or (
            presentation.subject_id, presentation.report_id, presentation.presentation_contract, presentation.rollout_generation
        ) != (head.subject_id, head.report_id, head.presentation_contract, head.rollout_generation):
            raise PublicH2Invalid("company card v2 lifecycle head is invalid")
        record = await session.get(CompanyReportRecord, head.report_id)
        if record is None:
            raise PublicH2Invalid("company card v2 lifecycle report is invalid")
        if record.lifecycle_status == "pending":
            raise PublicH2Pending("report_pending")
        if record.lifecycle_status == "failed":
            raise PublicH2Failed("report_failed")
        raise PublicH2NotEligible("report_not_eligible")
    # A v3 row with no durable H2 head must never fall through to a legacy
    # preview: it is neither an H1 report nor an H2 publication binding.
    has_v3 = await session.scalar(select(CompanyReportRecord.id).where(
        CompanyReportRecord.subject_id == subject.id,
        CompanyReportRecord.report_version == "3",
    ).limit(1))
    if has_v3 is not None:
        raise PublicH2NotEligible("report_not_eligible")
    record = await session.scalar(select(CompanyReportRecord).where(
        CompanyReportRecord.subject_id == subject.id,
        CompanyReportRecord.writer_profile == "h1_legacy_writer_v2",
        CompanyReportRecord.presentation_contract == "company_public_h1_v1",
        CompanyReportRecord.report_version.in_(("1", "2")),
        CompanyReportRecord.lifecycle_status.in_(("complete", "partial")),
        CompanyReportRecord.normalized_snapshot.is_not(None),
    ).order_by(
        CompanyReportRecord.generated_at.desc().nullslast(),
        CompanyReportRecord.id.desc(),
    ).limit(1))
    if record is None:
        raise PublicH2NotEligible("company card v2 has no eligible binding")
    return await _legacy_preview(session, record, inn)


async def _resolve_exact_v3(
    session: AsyncSession,
    record: CompanyReportRecord | None,
    *,
    pin: CompanyReportPresentationPin,
    expected_subject_id: object,
    expected_inn: str,
    dependencies: ExactPublicH2Dependencies | None = None,
) -> CompanyPublicH2Response:
    """Resolve one exact V3 saved result and reproduce its pinned projection.

    A resolved pin is a promise about the complete immutable report,
    generation, job and artifact tuple.  Once that promise exists, any absent
    or mismatched member is corruption rather than a reason to select a
    different report or synthesize fallback text.
    """
    if record is None:
        raise PublicH2Invalid("company card v2 binding is invalid")
    # Lifecycle outcomes are not immutable-binding corruption.  Preserve the
    # established 409 classes for an exact assigned document before validating
    # the complete/partial publication tuple below.
    if record.lifecycle_status == "pending":
        raise PublicH2Pending("report_pending")
    if record.lifecycle_status == "failed":
        raise PublicH2Failed("report_failed")
    try:
        snapshot = company_card_v2_from_snapshot(deepcopy(record.normalized_snapshot))
        projection_binding = _projection_binding_for_pin(
            pin,
            expected_inn=expected_inn,
        )
        _validate_saved_snapshot_policy(
            record,
            snapshot,
            pin.publication_policy_version,
        )
        _serialized, calculated_hash = validate_company_card_v2_finalization(
            snapshot,
            report_id=record.id,
            subject_inn=expected_inn,
            writer_profile=record.writer_profile,
            report_version=record.report_version,
            presentation_contract=record.presentation_contract,
            rollout_config_generation=record.rollout_generation,
        )
        presentation = (
            dependencies.presentation
            if dependencies is not None
            else await session.scalar(
                select(CompanyReportPresentation).where(
                    CompanyReportPresentation.subject_id == expected_subject_id,
                    CompanyReportPresentation.report_id == record.id,
                    CompanyReportPresentation.presentation_contract
                    == H2_PRESENTATION_CONTRACT,
                )
            )
        )
        if (
            record.subject_id != expected_subject_id
            or record.report_version != "3"
            or record.writer_profile != H2_WRITER_PROFILE
            or record.presentation_contract != H2_PRESENTATION_CONTRACT
            or not isinstance(record.rollout_generation, int)
            or record.rollout_generation <= 0
            or record.lifecycle_status not in {"complete", "partial"}
            or not _is_hex64(record.snapshot_hash)
            or record.snapshot_hash != pin.snapshot_hash
            or record.snapshot_hash != calculated_hash
            or record.snapshot_hash != calculate_company_card_v2_snapshot_hash(snapshot)
            or record.generated_at is None
            or record.generated_at.tzinfo is None
            or record.generated_at.utcoffset() is None
            or snapshot.generated_at != record.generated_at.astimezone(timezone.utc)
            or (
                getattr(pin, "projection_scope", None) == "active_publication"
                and pin.published_lastmod.astimezone(timezone.utc)
                != record.generated_at.astimezone(timezone.utc)
            )
            or presentation is None
            or presentation.subject_id != expected_subject_id
            or presentation.report_id != record.id
            or presentation.presentation_contract != H2_PRESENTATION_CONTRACT
            or presentation.rollout_generation != record.rollout_generation
            or pin.subject_id != expected_subject_id
            or pin.report_id != record.id
            or pin.presentation_contract != H2_PRESENTATION_CONTRACT
            or not isinstance(pin.generation, int)
            or pin.generation <= 0
            or pin.chart_facts_version != snapshot.chart_facts.version
            or pin.chart_facts_hash != snapshot.chart_facts.hash
            or pin.evidence_registry_version != snapshot.evidence_version
            or pin.publication_policy_version not in {
                H2_PUBLICATION_POLICY_V1,
                H2_PUBLICATION_POLICY_V2,
                H2_PUBLICATION_POLICY_V3,
            }
        ):
            raise ValueError("company card v2 pin identity is invalid")

        if pin.narrative_binding_status == "unresolved":
            if (
                pin.narrative_binding_kind is None
                and pin.narrative_binding_key is None
                and pin.projection_digest is None
            ):
                raise PublicH2NotEligible("report_not_eligible")
            raise ValueError("company card v2 unresolved pin shape is invalid")
        if (
            pin.narrative_binding_status != "resolved"
            or pin.narrative_binding_kind not in {"artifact", "fallback"}
            or not _is_hex64(pin.narrative_binding_key)
            or not _is_hex64(pin.projection_digest)
        ):
            raise ValueError("company card v2 resolved pin shape is invalid")

        job = (
            dependencies.narrative_job
            if dependencies is not None
            else await session.scalar(
                select(CompanyCardNarrativeJob)
                .join(
                    CompanyCardNarrativeArtifact,
                    (CompanyCardNarrativeArtifact.id == CompanyCardNarrativeJob.artifact_id)
                    & (
                        CompanyCardNarrativeArtifact.generation_key
                        == CompanyCardNarrativeJob.generation_key
                    ),
                )
                .where(
                    CompanyCardNarrativeArtifact.binding_kind
                    == pin.narrative_binding_kind,
                    CompanyCardNarrativeArtifact.binding_key
                    == pin.narrative_binding_key,
                )
            )
        )
        if job is None or job.artifact_id is None:
            raise ValueError("company card v2 saved result is missing")
        artifact = (
            dependencies.narrative_artifact
            if dependencies is not None
            else await session.get(CompanyCardNarrativeArtifact, job.artifact_id)
        )
        if artifact is None:
            raise ValueError("company card v2 saved artifact is missing")

        narrative_binding = _validated_v3_saved_result(
            record=record,
            snapshot=snapshot,
            pin=pin,
            job=job,
            artifact=artifact,
        )
        response = build_public_h2(
            snapshot,
            narrative_binding=narrative_binding,
            projection_binding=projection_binding,
            finance_enabled=pin.publication_policy_version
            in {H2_PUBLICATION_POLICY_V2, H2_PUBLICATION_POLICY_V3},
            arbitration_enabled=pin.publication_policy_version
            == H2_PUBLICATION_POLICY_V3,
        )
        if response.indexable:
            _validate_indexable_public_h2(response)
        if response.projection_digest != pin.projection_digest:
            raise ValueError("company card v2 projection digest is invalid")
        return response
    except PublicH2Error:
        raise
    except SQLAlchemyError:
        # Exact public-document selection distinguishes storage unavailability
        # (router 503) from a malformed immutable result (safe 500).
        raise
    except Exception as exc:
        raise PublicH2Invalid("company card v2 is invalid") from exc


def _is_staged_pin_shape(pin: CompanyReportPresentationPin) -> bool:
    """Return the exact persisted shape admitted by staged/latest preview."""
    return (
        getattr(pin, "projection_scope", None) in {None, "staged_publication"}
        and pin.indexable is False
        and pin.canonical_path is None
        and pin.published_lastmod is None
    )


def _validate_indexable_public_h2(response: CompanyPublicH2Response) -> None:
    """Enforce the rollout-only eligibility predicate for an indexable H2.

    The public DTO model proves structural and semantic consistency, but a
    structurally honest failure must still remain noindex.  Policy-v3
    indexability therefore requires all three bound source families and
    rejects every unsafe coverage state.  ``not_requested`` is additionally
    forbidden for the visible finance/arbitration gates: an unexecuted gate is
    not evidence that can authorize indexing.
    """
    if (
        type(response) is not CompanyPublicH2Response
        or response.indexable is not True
        or response.projection_scope != "active_publication"
        or response.report_version != "3"
        or response.snapshot_capability != "card_v2"
        or tuple(item.dataset for item in response.sources)
        != ("counterparty", "finance", "arbitration")
    ):
        raise ValueError("indexable public H2 identity is invalid")
    disallowed_states = {
        "failed",
        "conflict",
        "gate_closed",
        "legacy_unavailable",
    }
    if any(item.state in disallowed_states for item in response.coverage):
        raise ValueError("indexable public H2 coverage is unsafe")
    if any(
        item.state == "not_requested"
        and (
            item.block_id.startswith("finance_")
            or item.block_id.startswith("arbitration_")
        )
        for item in response.coverage
    ):
        raise ValueError("indexable public H2 evidence gate is unverified")


def _projection_binding_for_pin(
    pin: CompanyReportPresentationPin,
    *,
    expected_inn: str,
) -> PublicH2ProjectionBindingV1:
    scope = getattr(pin, "projection_scope", None)
    default_path = f"/company/{expected_inn}-company"
    if scope is None:
        if not _is_staged_pin_shape(pin):
            raise ValueError("legacy public H2 pin shape is invalid")
        return PublicH2ProjectionBindingV1(
            projection_scope="latest_unpublished",
            canonical_path=default_path,
            indexable=False,
            published_lastmod=None,
        )
    if scope == "staged_publication":
        if not _is_staged_pin_shape(pin):
            raise ValueError("staged public H2 pin shape is invalid")
        return PublicH2ProjectionBindingV1(
            projection_scope="staged_publication",
            canonical_path=default_path,
            indexable=False,
            published_lastmod=None,
        )
    if scope == "active_publication":
        if (
            pin.narrative_binding_status != "resolved"
            or pin.publication_policy_version != H2_PUBLICATION_POLICY_V3
            or not isinstance(pin.canonical_path, str)
            or type(pin.indexable) is not bool
            or pin.published_lastmod is None
        ):
            raise ValueError("active public H2 pin shape is invalid")
        return PublicH2ProjectionBindingV1(
            projection_scope="active_publication",
            canonical_path=pin.canonical_path,
            indexable=pin.indexable,
            published_lastmod=pin.published_lastmod,
        )
    raise ValueError("public H2 pin scope is invalid")


async def build_active_public_h2_for_pin(
    session: AsyncSession,
    *,
    record: CompanyReportRecord,
    source_pin: CompanyReportPresentationPin,
    expected_subject_id: object,
    expected_inn: str,
    canonical_path: str,
    indexable: bool,
    published_lastmod: object,
    dependencies: ExactPublicH2Dependencies | None = None,
) -> CompanyPublicH2Response:
    """Validate one exact staged pin and deterministically plan its active DTO."""
    if (
        getattr(source_pin, "projection_scope", None)
        not in {None, "staged_publication"}
        or not _is_staged_pin_shape(source_pin)
        or record.generated_at is None
        or record.generated_at.tzinfo is None
        or record.generated_at.utcoffset() is None
        or published_lastmod != record.generated_at
    ):
        raise PublicH2Invalid("company card v2 active source binding is invalid")
    source = await _resolve_exact_v3(
        session,
        record,
        pin=source_pin,
        expected_subject_id=expected_subject_id,
        expected_inn=expected_inn,
        dependencies=dependencies,
    )
    try:
        active = rebind_public_h2_projection(
            source,
            projection_binding=PublicH2ProjectionBindingV1(
                projection_scope="active_publication",
                canonical_path=canonical_path,
                indexable=indexable,
                published_lastmod=record.generated_at,
            ),
        )
        if active.indexable:
            _validate_indexable_public_h2(active)
        return active
    except Exception as exc:
        raise PublicH2Invalid("company card v2 active projection is invalid") from exc


async def _legacy_preview(session: AsyncSession, record: CompanyReportRecord, inn: str) -> CompanyPublicH2Response:
    """Resolve one exact saved fallback without a pin, mutation, or renderer."""
    try:
        raw_snapshot = deepcopy(record.normalized_snapshot)
        calculated_hash = calculate_company_report_snapshot_hash(raw_snapshot)
        snapshot = company_report_from_snapshot(raw_snapshot)
        if (
            record.snapshot_hash != calculated_hash
            or record.report_version != snapshot.report_version
            or str(record.id) != str(snapshot.report_id)
            or record.lifecycle_status != snapshot.status.value
            or snapshot.target_identifier != inn
            or snapshot.counterparty is None
            or snapshot.counterparty.inn != inn
            or record.generated_at is None
            or record.generated_at.tzinfo is None
            or record.generated_at.utcoffset() is None
            or snapshot.generated_at != record.generated_at.astimezone(timezone.utc)
        ):
            raise ValueError("legacy generated_at is invalid")
        snapshot_binding = LegacySnapshotBinding(
            report_id=str(record.id),
            report_version=record.report_version,
            inn=inn,
            lifecycle_status=record.lifecycle_status,
            stored_snapshot_hash=record.snapshot_hash,
            calculated_snapshot_hash=calculated_hash,
        )
    except Exception as exc:
        raise PublicH2Invalid("legacy company report is invalid") from exc

    outbox = await session.scalar(select(CompanyCardNarrativeOutbox).where(
        CompanyCardNarrativeOutbox.report_id == record.id,
        CompanyCardNarrativeOutbox.snapshot_hash == record.snapshot_hash,
        CompanyCardNarrativeOutbox.event_kind == "initialize_narrative_v1",
    ).limit(1))
    if outbox is None or outbox.state != "processed":
        raise PublicH2NotEligible("report_not_eligible")
    try:
        if (
            str(outbox.report_id) != str(record.id)
            or outbox.snapshot_hash != record.snapshot_hash
            or outbox.event_kind != "initialize_narrative_v1"
            or not _is_hex64(outbox.generation_key)
            or outbox.processed_at is None
            or outbox.failure_code is not None
            or outbox.lease_token is not None
            or outbox.lease_expires_at is not None
        ):
            raise ValueError("legacy narrative outbox identity is invalid")
        job = await session.scalar(
            select(CompanyCardNarrativeJob)
            .join(
                CompanyCardNarrativeArtifact,
                (CompanyCardNarrativeArtifact.id == CompanyCardNarrativeJob.artifact_id)
                & (
                    CompanyCardNarrativeArtifact.generation_key
                    == CompanyCardNarrativeJob.generation_key
                ),
            )
            .where(CompanyCardNarrativeJob.generation_key == outbox.generation_key)
        )
        if job is None or job.artifact_id is None:
            raise ValueError("legacy saved narrative job is missing")
        artifact = await session.get(CompanyCardNarrativeArtifact, job.artifact_id)
        if artifact is None:
            raise ValueError("legacy saved narrative artifact is missing")
        narrative_binding = _validated_legacy_saved_result(
            record=record,
            job=job,
            artifact=artifact,
            outbox_generation_key=outbox.generation_key,
        )
        return build_legacy_public_h2(
            snapshot,
            snapshot_binding=snapshot_binding,
            narrative_binding=narrative_binding,
        )
    except Exception as exc:
        raise PublicH2Invalid("legacy company report is invalid") from exc


@dataclass(frozen=True)
class _NarrativeBinding:
    narrative: PublicH2Narrative


def _validated_legacy_saved_result(
    *,
    record: CompanyReportRecord,
    job: CompanyCardNarrativeJob,
    artifact: CompanyCardNarrativeArtifact,
    outbox_generation_key: str,
) -> _NarrativeBinding:
    expected_identity = _legacy_generation_identity(record=record)
    expected_generation_key = identity_key(expected_identity)
    if (
        outbox_generation_key != expected_generation_key
        or str(job.report_id) != str(record.id)
        or job.snapshot_hash != record.snapshot_hash
        or job.generation_key != expected_generation_key
        or job.identity_version != "GenerationIdentityV2"
        or job.generation_identity != asdict(expected_identity)
        or job.state != "fallback_finalized"
        or job.artifact_id != artifact.id
        or job.lease_token is not None
        or job.lease_expires_at is not None
        or not _one_safe_validation_code(job.validation_codes)
        or any(
            value is not None
            for value in (
                job.gateway_dispatch_id,
                job.dispatch_started_at,
                job.response_received_at,
                job.resolved_model_version,
            )
        )
        or str(artifact.report_id) != str(record.id)
        or artifact.snapshot_hash != record.snapshot_hash
        or artifact.generation_key != expected_generation_key
    ):
        raise ValueError("legacy saved narrative generation identity is invalid")
    return _validated_saved_fallback(
        artifact,
        report_id=str(record.id),
        snapshot_hash=record.snapshot_hash,
    )


def _legacy_generation_identity(
    *,
    record: CompanyReportRecord,
) -> GenerationIdentityV2:
    snapshot_schema_version = LEGACY_SNAPSHOT_VERSIONS.get(record.report_version)
    if snapshot_schema_version is None or not _is_hex64(record.snapshot_hash):
        raise ValueError("legacy narrative snapshot identity is invalid")
    return GenerationIdentityV2(
        report_id=str(record.id),
        snapshot_hash=record.snapshot_hash,
        chart_facts_hash=EMPTY_CHART_FACTS_HASH,
        evidence_registry_version=NARRATIVE_EVIDENCE_ABSENT,
        statement_catalog_version=STATEMENT_CATALOG_VERSION,
        template_catalog_version=TEMPLATE_CATALOG_VERSION,
        prompt_version=PROMPT_VERSION,
        json_schema_version=OUTPUT_SCHEMA_VERSION,
        policy_version=POLICY_VERSION,
        renderer_version=RENDERER_VERSION,
        gateway_profile_version=GATEWAY_PROFILE_VERSION,
        fallback_catalog_version=FALLBACK_CATALOG_VERSION,
        snapshot_schema_version=snapshot_schema_version,
        narrative_evidence_schema_version=NARRATIVE_EVIDENCE_ABSENT,
        primary_activity_parser_version=NOT_APPLICABLE,
        primary_activity_evidence_version=NOT_APPLICABLE,
        insight_catalog_version=INSIGHT_CATALOG_VERSION,
        connector_catalog_version=CONNECTOR_CATALOG_VERSION,
        input_schema_version=INPUT_SCHEMA_VERSION,
    )


def _validated_v3_saved_result(
    *,
    record: CompanyReportRecord,
    snapshot: CompanyCardV2SnapshotV1,
    pin: CompanyReportPresentationPin,
    job: CompanyCardNarrativeJob,
    artifact: CompanyCardNarrativeArtifact,
) -> _NarrativeBinding:
    expected_identity = _v3_generation_identity(
        record=record,
        snapshot=snapshot,
    )
    expected_generation_key = identity_key(expected_identity)
    if (
        job.report_id != record.id
        or job.snapshot_hash != record.snapshot_hash
        or job.generation_key != expected_generation_key
        or job.identity_version != "GenerationIdentityV2"
        or job.generation_identity != asdict(expected_identity)
        or job.artifact_id != artifact.id
        or job.lease_token is not None
        or job.lease_expires_at is not None
        or artifact.report_id != record.id
        or artifact.snapshot_hash != record.snapshot_hash
        or artifact.generation_key != expected_generation_key
        or artifact.binding_kind != pin.narrative_binding_kind
        or artifact.binding_key != pin.narrative_binding_key
    ):
        raise ValueError("saved narrative generation identity is invalid")

    if artifact.binding_kind == "fallback":
        if (
            job.state != "fallback_finalized"
            or not _one_safe_validation_code(job.validation_codes)
            or (job.response_received_at is None)
            != (job.resolved_model_version is None)
            or (
                job.gateway_dispatch_id is None
                and any(
                    value is not None
                    for value in (
                        job.dispatch_started_at,
                        job.response_received_at,
                        job.resolved_model_version,
                    )
                )
            )
            or (
                job.gateway_dispatch_id is not None
                and job.dispatch_started_at is None
            )
        ):
            raise ValueError("saved fallback job state is invalid")
        return _validated_saved_fallback(
            artifact,
            report_id=str(record.id),
            snapshot_hash=record.snapshot_hash,
        )

    if (
        artifact.binding_kind != "artifact"
        or job.state != "finalized"
        or job.gateway_dispatch_id is None
        or job.dispatch_started_at is None
        or job.response_received_at is None
        or not isinstance(job.resolved_model_version, str)
        or job.resolved_model_version != artifact.resolved_model_version
        or job.validation_codes != []
    ):
        raise ValueError("saved narrative artifact job state is invalid")
    return _validated_ai_artifact(
        snapshot=snapshot,
        job=job,
        artifact=artifact,
    )


def _v3_generation_identity(
    *,
    record: CompanyReportRecord,
    snapshot: CompanyCardV2SnapshotV1,
) -> GenerationIdentityV2:
    if isinstance(snapshot, CompanyCardV2SnapshotV2):
        evidence = snapshot.narrative_evidence
        snapshot_schema_version = snapshot.snapshot_schema_version
        narrative_evidence_schema_version = evidence.schema_version
        primary_activity_parser_version = evidence.primary_activity_parser_version
        primary_activity_evidence_version = evidence.primary_activity_evidence_version
    else:
        snapshot_schema_version = FROZEN_V3_SNAPSHOT_VERSION
        narrative_evidence_schema_version = NARRATIVE_EVIDENCE_ABSENT
        primary_activity_parser_version = NOT_APPLICABLE
        primary_activity_evidence_version = NOT_APPLICABLE
    return GenerationIdentityV2(
        report_id=str(record.id),
        snapshot_hash=record.snapshot_hash,
        chart_facts_hash=snapshot.chart_facts.hash,
        evidence_registry_version=snapshot.evidence_version,
        statement_catalog_version=STATEMENT_CATALOG_VERSION,
        template_catalog_version=TEMPLATE_CATALOG_VERSION,
        prompt_version=PROMPT_VERSION,
        json_schema_version=OUTPUT_SCHEMA_VERSION,
        policy_version=POLICY_VERSION,
        renderer_version=RENDERER_VERSION,
        gateway_profile_version=GATEWAY_PROFILE_VERSION,
        fallback_catalog_version=FALLBACK_CATALOG_VERSION,
        snapshot_schema_version=snapshot_schema_version,
        narrative_evidence_schema_version=narrative_evidence_schema_version,
        primary_activity_parser_version=primary_activity_parser_version,
        primary_activity_evidence_version=primary_activity_evidence_version,
        insight_catalog_version=INSIGHT_CATALOG_VERSION,
        connector_catalog_version=CONNECTOR_CATALOG_VERSION,
        input_schema_version=INPUT_SCHEMA_VERSION,
    )


def _validated_ai_artifact(
    *,
    snapshot: CompanyCardV2SnapshotV1,
    job: CompanyCardNarrativeJob,
    artifact: CompanyCardNarrativeArtifact,
) -> _NarrativeBinding:
    if (
        not isinstance(snapshot, CompanyCardV2SnapshotV2)
        or snapshot.narrative_evidence.primary_activity is None
        or artifact.binding_key != artifact.artifact_identity
        or artifact.fallback_identity is not None
        or not _is_hex64(artifact.artifact_identity)
        or not isinstance(artifact.resolved_model_version, str)
        or not artifact.resolved_model_version.strip()
        or len(artifact.resolved_model_version) > 255
        or not isinstance(artifact.raw_model_output, str)
        or len(artifact.raw_model_output.encode("utf-8")) > 16384
        or artifact.validated_render_plan_cjson is None
        or artifact.validated_render_plan_bytes_sha256 is None
    ):
        raise ValueError("saved narrative artifact shape is invalid")

    plan_bytes = bytes(artifact.validated_render_plan_cjson)
    if (
        len(plan_bytes) > 16384
        or not _is_hex64(artifact.validated_render_plan_bytes_sha256)
        or hashlib.sha256(plan_bytes).hexdigest()
        != artifact.validated_render_plan_bytes_sha256
    ):
        raise ValueError("saved narrative plan hash is invalid")
    raw_plan = _json_without_duplicate_keys(artifact.raw_model_output)
    stored_plan = _json_without_duplicate_keys(plan_bytes.decode("utf-8"))
    raw_model = RenderPlan.model_validate(raw_plan)
    stored_model = RenderPlan.model_validate(stored_plan)
    canonical_plan = canonical_json_bytes(stored_model.model_dump(mode="json"))
    if raw_model != stored_model or canonical_plan != plan_bytes:
        raise ValueError("saved narrative plan bytes are invalid")

    evidence = NarrativeEvidenceEnvelope(
        evidence_registry_version=snapshot.evidence_version,
        primary_activity_label=(
            snapshot.narrative_evidence.primary_activity.label
        ),
    )
    rendered = validate_render_plan(stored_plan, evidence)
    if normalize_text(rendered.description) != rendered.description:
        raise ValueError("saved narrative description is not normalized")

    phrase_trace: list[dict[str, object]] = []
    evidence_ids: list[str] = []
    for index, trace in enumerate(rendered.phrase_trace):
        statement_id = rendered.statement_ids[index]
        expected_evidence_ids = EVIDENCE_BY_STATEMENT.get(statement_id)
        if (
            statement_id != trace.statement_id
            or expected_evidence_ids is None
            or trace.evidence_ids != expected_evidence_ids
        ):
            raise ValueError("saved narrative catalog evidence is invalid")
        phrase_trace.append({
            "scalar_start": trace.start,
            "scalar_end": trace.end,
            "statement_id": trace.statement_id,
            "evidence_ids": list(trace.evidence_ids),
        })
        for evidence_id in trace.evidence_ids:
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)

    rendered_digest = hashlib.sha256(
        rendered.description.encode("utf-8")
    ).hexdigest()
    expected_artifact_identity = identity_key(ArtifactIdentityV1(
        generation_key=job.generation_key,
        resolved_model_version=artifact.resolved_model_version,
        validated_render_plan_bytes_sha256=(
            artifact.validated_render_plan_bytes_sha256
        ),
        rendered_output_bytes_sha256=rendered_digest,
    ))
    if (
        tuple(rendered.statement_ids) != PUBLIC_STATEMENT_IDS
        or artifact.artifact_identity != expected_artifact_identity
        or artifact.rendered_description != rendered.description
        or artifact.rendered_comments != []
        or artifact.statement_ids != list(rendered.statement_ids)
        or artifact.evidence_ids != evidence_ids
        or artifact.phrase_trace != phrase_trace
        or artifact.validation_codes != []
        or artifact.renderer_version != RENDERER_VERSION
        or artifact.rendered_output_bytes_sha256 != rendered_digest
        or rendered.render_digest != rendered_digest
    ):
        raise ValueError("saved narrative render identity is invalid")

    return _NarrativeBinding(PublicH2Narrative(
        mode="artifact",
        renderer_version=RENDERER_VERSION,
        description=rendered.description,
        statement_ids=rendered.statement_ids,
        comments=(),
        render_digest=rendered_digest,
    ))


def _json_without_duplicate_keys(raw: str) -> object:
    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs_hook)


def _one_safe_validation_code(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 1
        and isinstance(value[0], str)
        and bool(value[0])
        and len(value[0]) <= 64
    )


def _validated_saved_fallback(
    artifact: CompanyCardNarrativeArtifact,
    *,
    report_id: str,
    snapshot_hash: str,
) -> _NarrativeBinding:
    digest = hashlib.sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest()
    fallback_identity = identity_key(FallbackIdentityV1(
        generation_key=artifact.generation_key,
        fallback_catalog_version=FALLBACK_CATALOG_VERSION,
        fallback_profile_id=FALLBACK_PROFILE_ID,
        renderer_version=FALLBACK_RENDERER_VERSION,
        rendered_output_bytes_sha256=digest,
    )) if _is_hex64(artifact.generation_key) else None
    expected_trace = [{
        "scalar_start": 0,
        "scalar_end": len(FALLBACK_DESCRIPTION),
        "statement_id": FALLBACK_PROFILE_ID,
        "evidence_ids": [],
    }]
    if (
        str(artifact.report_id) != report_id
        or artifact.snapshot_hash != snapshot_hash
        or artifact.binding_kind != "fallback"
        or fallback_identity is None
        or artifact.binding_key != fallback_identity
        or artifact.fallback_identity != fallback_identity
        or artifact.artifact_identity is not None
        or artifact.resolved_model_version is not None
        or artifact.raw_model_output is not None
        or artifact.validated_render_plan_cjson is not None
        or artifact.validated_render_plan_bytes_sha256 is not None
        or artifact.rendered_description != FALLBACK_DESCRIPTION
        or artifact.rendered_comments != []
        or artifact.statement_ids != [FALLBACK_PROFILE_ID]
        or artifact.evidence_ids != []
        or artifact.phrase_trace != expected_trace
        or artifact.validation_codes != []
        or artifact.renderer_version != FALLBACK_RENDERER_VERSION
        or artifact.rendered_output_bytes_sha256 != digest
    ):
        raise ValueError("saved fallback binding is invalid")
    return _NarrativeBinding(PublicH2Narrative(
        mode="deterministic_fallback",
        renderer_version=FALLBACK_RENDERER_VERSION,
        description=FALLBACK_DESCRIPTION,
        statement_ids=(FALLBACK_PROFILE_ID,),
        comments=(),
        render_digest=digest,
    ))


def _validate_saved_snapshot_policy(
    record: CompanyReportRecord,
    snapshot: CompanyCardV2SnapshotV1,
    policy: object,
) -> None:
    enabled = record.arbitration_collection_enabled
    if enabled is None:
        enabled = False
    key_id = record.arbitration_mask_key_id
    try:
        WriterDecision(
            writer_profile=record.writer_profile,
            report_version=record.report_version,
            presentation_contract=record.presentation_contract,
            rollout_generation=record.rollout_generation,
            arbitration_collection_enabled=enabled,
            arbitration_mask_key_id=key_id,
        )
    except ValueError as exc:
        raise ValueError("saved arbitration decision is invalid") from exc
    if type(enabled) is not bool or (not enabled and key_id is not None):
        raise ValueError("saved arbitration decision is invalid")
    if policy == H2_PUBLICATION_POLICY_V1:
        valid = type(snapshot) in {
            CompanyCardV2SnapshotV1,
            CompanyCardV2SnapshotV2,
        } and not enabled
    elif policy == H2_PUBLICATION_POLICY_V2:
        valid = type(snapshot) is CompanyCardV2SnapshotV2 and not enabled
    elif policy == H2_PUBLICATION_POLICY_V3:
        valid = type(snapshot) is CompanyCardV2SnapshotV3 and enabled
        if valid:
            effective_key_id = snapshot.arbitration_basis.mask_key_id
            valid = effective_key_id is None or effective_key_id == key_id
    else:
        valid = False
    if not valid:
        raise ValueError("saved snapshot/publication policy is invalid")


def _is_hex64(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "ExactPublicH2Dependencies",
    "PublicH2Error",
    "PublicH2Failed",
    "PublicH2Invalid",
    "PublicH2NotEligible",
    "PublicH2NotFound",
    "PublicH2Pending",
    "build_active_public_h2_for_pin",
    "h2_cohort_selected",
    "resolve_public_h2",
]
