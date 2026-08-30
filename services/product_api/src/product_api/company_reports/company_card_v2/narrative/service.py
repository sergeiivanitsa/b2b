from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas import ChatRequest, ChatResponse

from product_api.company_reports.company_card_v2.finance import build_chart_facts
from product_api.company_reports.company_card_v2.models import (
    CompanyCardV2SnapshotV1,
    CompanyCardV2SnapshotV2,
    CompanyCardV2SnapshotV3,
    FinanceBasisV1,
)
from product_api.company_reports.company_card_v2.public_h2 import (
    PublicH2ProjectionBindingV1,
    build_public_h2,
)
from product_api.company_reports.company_card_v2.public_h2_models import PublicH2Narrative
from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeBudgetReservation,
    CompanyCardNarrativeJob,
    CompanyReportRecord,
    CompanyReportPresentationPin,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.presentations import (
    H2_PUBLICATION_POLICY_V1,
    H2_PUBLICATION_POLICY_V2,
    H2_PUBLICATION_POLICY_V3,
)
from product_api.company_reports.persistence.jobs import WriterDecision
from product_api.company_reports.persistence.errors import CompanyReportSnapshotError
from product_api.company_reports.persistence.narrative_outbox import (
    NarrativeOutboxLease,
    claim_narrative_outbox,
    get_claimed_narrative_outbox,
    mark_narrative_outbox_processed,
    mark_narrative_outbox_terminal,
    outbox_lease,
)
from product_api.company_reports.persistence.narratives import (
    NarrativeArtifactDraft,
    NarrativeBudgetUnavailable,
    NarrativeJobLease,
    NarrativePersistenceError,
    expire_pre_dispatch_job,
    finalize_expired_post_dispatch_fallback,
    finalize_unleased_fallback,
    finalize_unpublishable_job,
    initialize_narrative_generation,
    job_lease,
    reserve_or_rereserve_dispatch_credit,
    select_expired_narrative_job,
)
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
    company_report_from_snapshot,
)
from product_api.company_reports.persistence.v3 import (
    calculate_company_card_v2_snapshot_hash,
    company_card_v2_from_snapshot,
    validate_company_card_v2_finalization,
)

from ..canonical_json import canonical_json_bytes
from .catalog import (
    CONNECTOR_CATALOG_VERSION,
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
    FALLBACK_CATALOG_VERSION,
    FROZEN_V3_SNAPSHOT_VERSION,
    GATEWAY_PROFILE_VERSION,
    INPUT_SCHEMA_VERSION,
    INSIGHT_CATALOG_VERSION,
    LEGACY_SNAPSHOT_VERSIONS,
    MODEL_PROFILE,
    NARRATIVE_EVIDENCE_ABSENT,
    NOT_APPLICABLE,
    OUTPUT_SCHEMA_VERSION,
    POLICY_VERSION,
    PROMPT_VERSION,
    RENDERER_VERSION,
    STATEMENT_CATALOG_VERSION,
    TEMPLATE_CATALOG_VERSION,
)
from .identity import ArtifactIdentityV1, GenerationIdentityV2, identity_key
from .models import NarrativeEvidenceEnvelope, RenderPlan, RenderedNarrative
from .prompt import build_narrative_gateway_body
from .validation import NarrativeValidationError, normalize_text, validate_render_plan


_EMPTY_CHART_FACTS_HASH = build_chart_facts(FinanceBasisV1()).hash
_REPORT_VALIDATION_ERRORS = (
    CompanyReportSnapshotError,
    NarrativePersistenceError,
    TypeError,
    ValueError,
)


@dataclass(frozen=True)
class NarrativeLimits:
    enabled: bool = False
    kill_switch: bool = True
    quota_mode: Literal["bounded", "unlimited"] = "bounded"
    daily_limit: int = 0
    monthly_limit: int = 0
    concurrency: int = 0

    def __post_init__(self) -> None:
        if min(self.daily_limit, self.monthly_limit, self.concurrency) < 0:
            raise ValueError("narrative limits must be non-negative")
        if self.quota_mode not in {"bounded", "unlimited"}:
            raise ValueError("narrative quota mode is invalid")
        if self.quota_mode == "unlimited" and (
            self.daily_limit != 0 or self.monthly_limit != 0
        ):
            raise ValueError(
                "unlimited narrative requires zero daily and monthly limits"
            )

    def permits_dispatch(self) -> bool:
        return (
            self.enabled
            and not self.kill_switch
            and self.concurrency > 0
            and (
                self.quota_mode == "unlimited"
                or (self.daily_limit > 0 and self.monthly_limit > 0)
            )
        )


@dataclass(frozen=True)
class ValidatedNarrativeReport:
    record: CompanyReportRecord
    snapshot: object
    identity: GenerationIdentityV2
    generation_key: str
    activity_label: str | None
    publication_policy_version: str | None = None

    @property
    def is_v3(self) -> bool:
        return self.record.report_version == "3"

    @property
    def eligible_for_ai(self) -> bool:
        return isinstance(self.snapshot, CompanyCardV2SnapshotV2) and self.activity_label is not None


@dataclass(frozen=True)
class PreparedNarrativeDispatch:
    lease: NarrativeJobLease
    report: ValidatedNarrativeReport
    evidence: NarrativeEvidenceEnvelope
    request: ChatRequest


@dataclass(frozen=True)
class NarrativeResponseValidationContextV1:
    gateway_dispatch_id: UUID
    generation_key: str
    evidence: NarrativeEvidenceEnvelope

    def __post_init__(self) -> None:
        if type(self.gateway_dispatch_id) is not UUID:
            raise TypeError("narrative validation dispatch id must be an exact UUID")
        if re.fullmatch(r"[0-9a-f]{64}", self.generation_key) is None:
            raise ValueError("narrative validation generation key is invalid")
        if type(self.evidence) is not NarrativeEvidenceEnvelope:
            raise TypeError("narrative validation evidence has an invalid type")


@dataclass(frozen=True)
class ValidatedGatewayArtifact:
    draft: NarrativeArtifactDraft
    public_narrative: PublicH2Narrative


class _NarrativeBinding:
    def __init__(self, narrative: PublicH2Narrative) -> None:
        self.narrative = narrative


def _matches_stored_generation_identity(
    expected: GenerationIdentityV2,
    stored: object,
) -> bool:
    """Compare one exact identity through its durable JSON representation.

    The ``identity_version`` field is ``init=False``: ``dataclasses.asdict``
    persists it, while the instance ``__dict__`` omits it.  JSONB also has its
    own durable container representation.  Reconstructing the closed dataclass
    and comparing canonical bytes avoids both representation traps while still
    binding every key, scalar type and value exactly; malformed or
    non-serializable stored data fails closed.
    """
    expected_payload = asdict(expected)
    if (
        not isinstance(stored, dict)
        or set(stored) != set(expected_payload)
        or stored.get("identity_version") != expected.identity_version
    ):
        return False
    try:
        reconstructed = GenerationIdentityV2(
            **{
                key: value
                for key, value in stored.items()
                if key != "identity_version"
            }
        )
        return (
            identity_key(reconstructed) == identity_key(expected)
            and canonical_json_bytes(asdict(reconstructed))
            == canonical_json_bytes(expected_payload)
            == canonical_json_bytes(stored)
        )
    except (TypeError, ValueError):
        return False


def _fallback_public_narrative() -> PublicH2Narrative:
    digest = sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest()
    return PublicH2Narrative(
        mode="deterministic_fallback",
        renderer_version=FALLBACK_RENDERER_VERSION,
        description=FALLBACK_DESCRIPTION,
        statement_ids=(FALLBACK_PROFILE_ID,),
        comments=(),
        render_digest=digest,
    )


def _artifact_public_narrative(rendered: RenderedNarrative) -> PublicH2Narrative:
    return PublicH2Narrative(
        mode="artifact",
        renderer_version=RENDERER_VERSION,
        description=rendered.description,
        statement_ids=rendered.statement_ids,
        comments=(),
        render_digest=rendered.render_digest,
    )


def _projection_digest(
    snapshot: CompanyCardV2SnapshotV1,
    narrative: PublicH2Narrative,
    publication_policy_version: str | None = None,
) -> str:
    canonical_path = f"/company/{snapshot.subject_inn}-company"
    return build_public_h2(
        snapshot,
        narrative_binding=_NarrativeBinding(narrative),
        projection_binding=PublicH2ProjectionBindingV1(
            projection_scope="staged_publication",
            canonical_path=canonical_path,
            indexable=False,
            published_lastmod=None,
        ),
        finance_enabled=publication_policy_version
        in {H2_PUBLICATION_POLICY_V2, H2_PUBLICATION_POLICY_V3},
        arbitration_enabled=publication_policy_version == H2_PUBLICATION_POLICY_V3,
    ).projection_digest


def _fallback_projection(report: ValidatedNarrativeReport) -> str | None:
    if not report.is_v3:
        return None
    if not isinstance(report.snapshot, CompanyCardV2SnapshotV1):
        raise NarrativePersistenceError("v3 narrative snapshot is unavailable")
    return _projection_digest(
        report.snapshot, _fallback_public_narrative(), report.publication_policy_version,
    )


def fallback_projection_digest(report: ValidatedNarrativeReport) -> str | None:
    """Expose the already-validated write-side fallback projection digest."""
    return _fallback_projection(report)


def projection_digest_for_narrative(
    report: ValidatedNarrativeReport,
    narrative: PublicH2Narrative,
) -> str:
    """Bind a validated narrative to the separately held durable snapshot."""
    if type(report) is not ValidatedNarrativeReport:
        raise TypeError("narrative projection report has an invalid type")
    if type(narrative) is not PublicH2Narrative:
        raise TypeError("public narrative has an invalid type")
    if not report.is_v3 or not isinstance(report.snapshot, CompanyCardV2SnapshotV1):
        raise NarrativePersistenceError("v3 narrative snapshot is unavailable")
    return _projection_digest(
        report.snapshot,
        narrative,
        report.publication_policy_version,
    )


async def validate_narrative_report(
    session: AsyncSession,
    *,
    record: CompanyReportRecord,
) -> ValidatedNarrativeReport:
    """Validate the exact stored JSON/hash without mutating or rewriting it."""
    if (
        record.lifecycle_status not in {"complete", "partial"}
        or record.snapshot_hash is None
        or not isinstance(record.normalized_snapshot, dict)
    ):
        raise NarrativePersistenceError("narrative report is not finalized")
    subject = await session.get(CompanyReportSubject, record.subject_id)
    if subject is None:
        raise NarrativePersistenceError("narrative report subject is missing")

    raw_snapshot = deepcopy(record.normalized_snapshot)
    if record.report_version in {"1", "2"}:
        legacy = company_report_from_snapshot(raw_snapshot)
        if (
            legacy.report_id != record.id
            or legacy.report_version != record.report_version
            or legacy.target_identifier != subject.normalized_identifier
            or calculate_company_report_snapshot_hash(raw_snapshot) != record.snapshot_hash
        ):
            raise NarrativePersistenceError("legacy narrative report identity is invalid")
        snapshot_schema_version = LEGACY_SNAPSHOT_VERSIONS[record.report_version]
        chart_facts_hash = _EMPTY_CHART_FACTS_HASH
        evidence_registry_version = NARRATIVE_EVIDENCE_ABSENT
        narrative_evidence_schema_version = NARRATIVE_EVIDENCE_ABSENT
        parser_version = NOT_APPLICABLE
        activity_evidence_version = NOT_APPLICABLE
        activity_label = None
        snapshot: object = legacy
    elif record.report_version == "3":
        card = company_card_v2_from_snapshot(raw_snapshot)
        _serialized, digest = validate_company_card_v2_finalization(
            card,
            report_id=record.id,
            subject_inn=subject.normalized_identifier,
            writer_profile=record.writer_profile,
            report_version=record.report_version,
            presentation_contract=record.presentation_contract,
            rollout_config_generation=record.rollout_generation,
        )
        if digest != record.snapshot_hash or calculate_company_card_v2_snapshot_hash(card) != record.snapshot_hash:
            raise NarrativePersistenceError("v3 narrative snapshot hash is invalid")
        chart_facts_version = card.chart_facts.version
        chart_facts_hash = card.chart_facts.hash
        evidence_registry_version = card.evidence_version
        snapshot = card
        if isinstance(card, CompanyCardV2SnapshotV2):
            snapshot_schema_version = card.snapshot_schema_version
            narrative_evidence_schema_version = card.narrative_evidence.schema_version
            parser_version = card.narrative_evidence.primary_activity_parser_version
            activity_evidence_version = card.narrative_evidence.primary_activity_evidence_version
            activity_label = (
                card.narrative_evidence.primary_activity.label
                if card.narrative_evidence.primary_activity is not None
                else None
            )
        else:
            snapshot_schema_version = FROZEN_V3_SNAPSHOT_VERSION
            narrative_evidence_schema_version = NARRATIVE_EVIDENCE_ABSENT
            parser_version = NOT_APPLICABLE
            activity_evidence_version = NOT_APPLICABLE
            activity_label = None
    else:
        raise NarrativePersistenceError("narrative report version is invalid")

    publication_policy_version: str | None = None
    # A production narrative must bind the one durable predecessor written by
    # the fenced report finalizer.  Selecting a first row would make a corrupt
    # duplicate lineage silently observable, so reject missing and ambiguous
    # predecessors before any dispatch/outbox work starts.  Minimal unit
    # adapters do not expose ``scalars`` and model only historical closed v1.
    if record.report_version == "3" and hasattr(session, "scalars"):
        policy_pins = list((await session.scalars(
            select(CompanyReportPresentationPin)
            .where(
                CompanyReportPresentationPin.report_id == record.id,
                CompanyReportPresentationPin.presentation_contract == "company_public_h2_v1",
                CompanyReportPresentationPin.narrative_binding_status == "unresolved",
            )
            .order_by(CompanyReportPresentationPin.generation)
        )).all())
        if len(policy_pins) != 1:
            raise NarrativePersistenceError("v3 publication lineage is missing or ambiguous")
        predecessor = policy_pins[0]
        if (
            predecessor.subject_id != record.subject_id
            or predecessor.report_id != record.id
            or predecessor.snapshot_hash != record.snapshot_hash
            or predecessor.chart_facts_version != chart_facts_version
            or predecessor.chart_facts_hash != chart_facts_hash
            or predecessor.evidence_registry_version != evidence_registry_version
            or predecessor.presentation_contract != "company_public_h2_v1"
            or predecessor.generation <= 0
            or predecessor.indexable is not False
            or predecessor.canonical_path is not None
            or predecessor.published_lastmod is not None
            or predecessor.projection_digest is not None
            or predecessor.narrative_binding_status != "unresolved"
            or predecessor.narrative_binding_kind is not None
            or predecessor.narrative_binding_key is not None
        ):
            raise NarrativePersistenceError("v3 publication predecessor identity is invalid")
        publication_policy_version = predecessor.publication_policy_version
        if publication_policy_version not in {
            H2_PUBLICATION_POLICY_V1,
            H2_PUBLICATION_POLICY_V2,
            H2_PUBLICATION_POLICY_V3,
        }:
            raise NarrativePersistenceError("v3 publication policy is invalid")
        arbitration_enabled = getattr(
            record,
            "arbitration_collection_enabled",
            False,
        )
        arbitration_key_id = getattr(record, "arbitration_mask_key_id", None)
        try:
            WriterDecision(
                writer_profile=record.writer_profile,
                report_version=record.report_version,
                presentation_contract=record.presentation_contract,
                rollout_generation=record.rollout_generation,
                arbitration_collection_enabled=arbitration_enabled,
                arbitration_mask_key_id=arbitration_key_id,
            )
        except ValueError as exc:
            raise NarrativePersistenceError(
                "v3 arbitration decision is invalid"
            ) from exc
        if type(arbitration_enabled) is not bool or (
            not arbitration_enabled and arbitration_key_id is not None
        ):
            raise NarrativePersistenceError("v3 arbitration decision is invalid")
        if publication_policy_version == H2_PUBLICATION_POLICY_V3:
            if type(card) is not CompanyCardV2SnapshotV3 or not arbitration_enabled:
                raise NarrativePersistenceError("v3 publication policy is invalid")
            effective_key_id = card.arbitration_basis.mask_key_id
            if effective_key_id is not None and effective_key_id != arbitration_key_id:
                raise NarrativePersistenceError("v3 arbitration decision is invalid")
        elif publication_policy_version == H2_PUBLICATION_POLICY_V2:
            if type(card) is not CompanyCardV2SnapshotV2 or arbitration_enabled:
                raise NarrativePersistenceError("v3 publication policy is invalid")
        elif (
            type(card) not in {CompanyCardV2SnapshotV1, CompanyCardV2SnapshotV2}
            or arbitration_enabled
        ):
            raise NarrativePersistenceError("v3 publication policy is invalid")

    identity = GenerationIdentityV2(
        report_id=str(record.id),
        snapshot_hash=record.snapshot_hash,
        chart_facts_hash=chart_facts_hash,
        evidence_registry_version=evidence_registry_version,
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
        primary_activity_parser_version=parser_version,
        primary_activity_evidence_version=activity_evidence_version,
        insight_catalog_version=INSIGHT_CATALOG_VERSION,
        connector_catalog_version=CONNECTOR_CATALOG_VERSION,
        input_schema_version=INPUT_SCHEMA_VERSION,
    )
    return ValidatedNarrativeReport(
        record=record,
        snapshot=snapshot,
        identity=identity,
        generation_key=identity_key(identity),
        activity_label=activity_label,
        publication_policy_version=publication_policy_version,
    )


def _fallback_reason(report: ValidatedNarrativeReport, limits: NarrativeLimits) -> str | None:
    if report.record.report_version in {"1", "2"}:
        return "legacy_snapshot"
    if isinstance(report.snapshot, CompanyCardV2SnapshotV1) and not isinstance(
        report.snapshot, CompanyCardV2SnapshotV2
    ):
        return "frozen_v3_snapshot"
    if report.activity_label is None:
        return "primary_activity_unavailable"
    if not limits.enabled:
        return "feature_disabled"
    if limits.kill_switch:
        return "kill_switch_enabled"
    if not limits.permits_dispatch():
        return "runtime_limits_closed"
    return None


async def claim_narrative_reconciliation(
    session: AsyncSession,
    *,
    now: datetime,
    lease_seconds: int = 60,
) -> NarrativeOutboxLease | None:
    row = await claim_narrative_outbox(session, now=now, lease_seconds=lease_seconds)
    return None if row is None else outbox_lease(row)


async def reconcile_claimed_narrative_outbox(
    session: AsyncSession,
    *,
    lease: NarrativeOutboxLease,
    now: datetime,
    limits: NarrativeLimits,
) -> int:
    outbox = await get_claimed_narrative_outbox(session, lease=lease, now=now)
    record = await session.get(CompanyReportRecord, outbox.report_id, with_for_update=True)
    if record is None or record.snapshot_hash != outbox.snapshot_hash:
        await mark_narrative_outbox_terminal(
            session,
            lease=lease,
            failure_code="invalid_report_identity",
            now=now,
        )
        return 1
    try:
        validated = await validate_narrative_report(session, record=record)
    except _REPORT_VALIDATION_ERRORS:
        await mark_narrative_outbox_terminal(
            session,
            lease=lease,
            failure_code="invalid_report_snapshot",
            now=now,
        )
        return 1

    job = await initialize_narrative_generation(
        session,
        report_id=record.id,
        snapshot_hash=record.snapshot_hash,
        generation_key=validated.generation_key,
        identity=validated.identity,
        now=now,
    )
    if job.state != "ready":
        await mark_narrative_outbox_processed(
            session,
            lease=lease,
            generation_key=validated.generation_key,
            now=now,
        )
        return 1
    existing_reservation = await session.get(
        CompanyCardNarrativeBudgetReservation,
        validated.generation_key,
        with_for_update=True,
    )
    if existing_reservation is not None and existing_reservation.state == "reserved":
        await mark_narrative_outbox_processed(
            session,
            lease=lease,
            generation_key=validated.generation_key,
            now=now,
        )
        return 1

    fallback_reason = _fallback_reason(validated, limits)
    if fallback_reason is None:
        try:
            await reserve_or_rereserve_dispatch_credit(
                session,
                generation_key=validated.generation_key,
                now=now,
            )
        except NarrativeBudgetUnavailable as exc:
            fallback_reason = exc.code
    if fallback_reason is not None:
        await finalize_unleased_fallback(
            session,
            generation_key=validated.generation_key,
            validation_code=fallback_reason,
            projection_digest=_fallback_projection(validated),
            now=now,
        )
    await mark_narrative_outbox_processed(
        session,
        lease=lease,
        generation_key=validated.generation_key,
        now=now,
    )
    return 1


async def reconcile_narrative_outbox(
    session: AsyncSession,
    *,
    now: datetime,
    limits: NarrativeLimits,
) -> int:
    """Compatibility helper; production worker commits the claim separately."""
    lease = await claim_narrative_reconciliation(session, now=now)
    if lease is None:
        return 0
    return await reconcile_claimed_narrative_outbox(
        session,
        lease=lease,
        now=now,
        limits=limits,
    )


async def prepare_narrative_dispatch(
    session: AsyncSession,
    *,
    lease: NarrativeJobLease,
    dispatch_id: UUID,
    now: datetime,
    timeout_seconds: int,
    max_output_tokens: int,
) -> PreparedNarrativeDispatch:
    job = await session.get(CompanyCardNarrativeJob, lease.job_id, with_for_update=True)
    if (
        job is None
        or job.state != "leased"
        or job.lease_token != lease.lease_token
        or job.fence_generation != lease.fence_generation
        or job.lease_expires_at is None
        or job.lease_expires_at <= now
    ):
        raise NarrativePersistenceError("stale narrative dispatch preparation")
    record = await session.get(CompanyReportRecord, job.report_id, with_for_update=True)
    if record is None:
        raise NarrativePersistenceError("narrative dispatch report is missing")
    validated = await validate_narrative_report(session, record=record)
    if (
        not validated.eligible_for_ai
        or validated.generation_key != job.generation_key
        or validated.identity.identity_version != job.identity_version
        or not _matches_stored_generation_identity(
            validated.identity,
            job.generation_identity,
        )
    ):
        raise NarrativePersistenceError("narrative dispatch generation changed")
    evidence = NarrativeEvidenceEnvelope(
        evidence_registry_version=validated.identity.evidence_registry_version,
        primary_activity_label=validated.activity_label,
        limitation_code=(
            None
            if validated.activity_label is not None
            else "primary_activity_not_admitted"
        ),
    )
    body = build_narrative_gateway_body(evidence, dispatch_id=dispatch_id)
    body["timeout"] = timeout_seconds
    body["max_output_tokens"] = max_output_tokens
    request = ChatRequest.model_validate(body)
    return PreparedNarrativeDispatch(
        lease=lease,
        report=validated,
        evidence=evidence,
        request=request,
    )


def _json_without_duplicate_keys(raw: str) -> object:
    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise NarrativeValidationError("duplicate JSON object key")
            result[key] = value
        return result

    try:
        return json.loads(raw, object_pairs_hook=pairs_hook)
    except NarrativeValidationError:
        raise
    except (json.JSONDecodeError, UnicodeError, TypeError) as exc:
        raise NarrativeValidationError("narrative response is not JSON") from exc


def validate_gateway_artifact(
    context: NarrativeResponseValidationContextV1,
    response: ChatResponse,
) -> ValidatedGatewayArtifact:
    if type(context) is not NarrativeResponseValidationContextV1:
        raise TypeError("narrative response validation context has an invalid type")
    dispatch_id = context.gateway_dispatch_id
    if (
        dispatch_id is None
        or response.gateway_dispatch_id != dispatch_id
        or response.model_profile != MODEL_PROFILE
        or not isinstance(response.resolved_model, str)
        or not response.resolved_model.strip()
        or len(response.resolved_model) > 255
        or len(response.text.encode("utf-8")) > 16384
    ):
        raise NarrativeValidationError("gateway narrative identity is invalid")
    raw_plan = _json_without_duplicate_keys(response.text)
    try:
        first_plan = RenderPlan.model_validate(deepcopy(raw_plan))
        second_plan = RenderPlan.model_validate(deepcopy(raw_plan))
    except Exception as exc:
        raise NarrativeValidationError("render plan is invalid") from exc
    if first_plan != second_plan:
        raise NarrativeValidationError("render plan validation is nondeterministic")
    first_render = validate_render_plan(deepcopy(raw_plan), context.evidence)
    second_render = validate_render_plan(deepcopy(raw_plan), context.evidence)
    if first_render != second_render:
        raise NarrativeValidationError("narrative double render mismatch")
    if normalize_text(first_render.description) != first_render.description:
        raise NarrativeValidationError("rendered narrative is not normalized")
    if first_render.render_digest != sha256(first_render.description.encode("utf-8")).hexdigest():
        raise NarrativeValidationError("rendered narrative hash is invalid")

    traces: list[dict[str, object]] = []
    evidence_ids: list[str] = []
    previous_end = -1
    for index, trace in enumerate(first_render.phrase_trace):
        if (
            trace.statement_id != first_render.statement_ids[index]
            or trace.start < 0
            or trace.end <= trace.start
            or trace.end > len(first_render.description)
            or (index == 0 and trace.start != 0)
            or (index > 0 and trace.start != previous_end + 1)
        ):
            raise NarrativeValidationError("narrative phrase trace is invalid")
        previous_end = trace.end
        traces.append(
            {
                "scalar_start": trace.start,
                "scalar_end": trace.end,
                "statement_id": trace.statement_id,
                "evidence_ids": list(trace.evidence_ids),
            }
        )
        for evidence_id in trace.evidence_ids:
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
    if previous_end != len(first_render.description):
        raise NarrativeValidationError("narrative phrase trace is incomplete")

    plan_bytes = canonical_json_bytes(first_plan.model_dump(mode="json"))
    plan_hash = sha256(plan_bytes).hexdigest()
    rendered_hash = sha256(first_render.description.encode("utf-8")).hexdigest()
    artifact_identity = identity_key(
        ArtifactIdentityV1(
            generation_key=context.generation_key,
            resolved_model_version=response.resolved_model,
            validated_render_plan_bytes_sha256=plan_hash,
            rendered_output_bytes_sha256=rendered_hash,
        )
    )
    draft = NarrativeArtifactDraft(
        artifact_identity=artifact_identity,
        resolved_model_version=response.resolved_model,
        raw_model_output=response.text,
        validated_render_plan_cjson=plan_bytes,
        validated_render_plan_bytes_sha256=plan_hash,
        rendered_description=first_render.description,
        statement_ids=first_render.statement_ids,
        evidence_ids=tuple(evidence_ids),
        phrase_trace=tuple(traces),
        validation_codes=(),
        renderer_version=RENDERER_VERSION,
        rendered_output_bytes_sha256=rendered_hash,
    )
    return ValidatedGatewayArtifact(
        draft=draft,
        public_narrative=_artifact_public_narrative(first_render),
    )


async def requeue_pre_dispatch_failure(
    session: AsyncSession,
    *,
    now: datetime,
) -> int:
    job = await session.scalar(
        select(CompanyCardNarrativeJob)
        .where(CompanyCardNarrativeJob.state == "pre_dispatch_failed")
        .order_by(CompanyCardNarrativeJob.available_at, CompanyCardNarrativeJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return 0
    if job.local_attempt_count >= 3:
        record = await session.get(CompanyReportRecord, job.report_id, with_for_update=True)
        try:
            if record is None:
                raise NarrativePersistenceError("pre-dispatch report is missing")
            validated = await validate_narrative_report(session, record=record)
            if validated.generation_key != job.generation_key:
                raise NarrativePersistenceError("pre-dispatch generation changed")
        except _REPORT_VALIDATION_ERRORS:
            await finalize_unpublishable_job(
                session,
                job=job,
                validation_code="invalid_report_snapshot",
                now=now,
            )
            return 1
        await finalize_unleased_fallback(
            session,
            generation_key=job.generation_key,
            validation_code="local_attempts_exhausted",
            projection_digest=_fallback_projection(validated),
            now=now,
        )
        return 1
    try:
        await reserve_or_rereserve_dispatch_credit(
            session,
            generation_key=job.generation_key,
            now=now,
        )
    except NarrativeBudgetUnavailable as exc:
        record = await session.get(CompanyReportRecord, job.report_id, with_for_update=True)
        try:
            if record is None:
                raise NarrativePersistenceError("pre-dispatch report is missing")
            validated = await validate_narrative_report(session, record=record)
            if validated.generation_key != job.generation_key:
                raise NarrativePersistenceError("pre-dispatch generation changed")
        except _REPORT_VALIDATION_ERRORS:
            await finalize_unpublishable_job(
                session,
                job=job,
                validation_code="invalid_report_snapshot",
                now=now,
            )
            return 1
        await finalize_unleased_fallback(
            session,
            generation_key=job.generation_key,
            validation_code=exc.code,
            projection_digest=_fallback_projection(validated),
            now=now,
        )
    return 1


async def reconcile_expired_narrative_jobs(
    session: AsyncSession,
    *,
    now: datetime,
) -> int:
    job = await select_expired_narrative_job(session, now=now)
    if job is None:
        return 0
    record = await session.get(CompanyReportRecord, job.report_id, with_for_update=True)
    try:
        if record is None:
            raise NarrativePersistenceError("expired narrative report is missing")
        validated = await validate_narrative_report(session, record=record)
        if validated.generation_key != job.generation_key:
            raise NarrativePersistenceError("expired narrative generation changed")
    except _REPORT_VALIDATION_ERRORS:
        validated = None
    if job.state == "leased":
        await expire_pre_dispatch_job(session, job=job, now=now)
        if job.local_attempt_count >= 3:
            if validated is None:
                await finalize_unpublishable_job(
                    session,
                    job=job,
                    validation_code="invalid_report_snapshot",
                    now=now,
                )
            else:
                await finalize_unleased_fallback(
                    session,
                    generation_key=job.generation_key,
                    validation_code="local_attempts_exhausted",
                    projection_digest=_fallback_projection(validated),
                    now=now,
                )
        return 1
    if validated is None:
        await finalize_unpublishable_job(
            session,
            job=job,
            validation_code="invalid_report_snapshot",
            now=now,
        )
        return 1
    projection = _fallback_projection(validated)
    if projection is None:
        raise NarrativePersistenceError("post-dispatch narrative must be v3")
    await finalize_expired_post_dispatch_fallback(
        session,
        job=job,
        validation_code="ambiguous_worker_death",
        projection_digest=projection,
        now=now,
    )
    return 1


__all__ = [
    "NarrativeLimits",
    "NarrativeResponseValidationContextV1",
    "PreparedNarrativeDispatch",
    "ValidatedGatewayArtifact",
    "ValidatedNarrativeReport",
    "claim_narrative_reconciliation",
    "fallback_projection_digest",
    "projection_digest_for_narrative",
    "prepare_narrative_dispatch",
    "reconcile_claimed_narrative_outbox",
    "reconcile_expired_narrative_jobs",
    "reconcile_narrative_outbox",
    "requeue_pre_dispatch_failure",
    "validate_gateway_artifact",
    "validate_narrative_report",
]
