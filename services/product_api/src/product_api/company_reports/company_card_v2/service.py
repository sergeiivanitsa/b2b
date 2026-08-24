from __future__ import annotations

from copy import deepcopy
import hashlib

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.persistence.models import CompanyReportH2LifecycleHead, CompanyReportPresentation, CompanyReportPresentationAssignment, CompanyReportPresentationPin, CompanyReportPresentationStagedPointer, CompanyReportRecord, CompanyReportSubject
from product_api.company_reports.persistence.v3 import calculate_company_card_v2_snapshot_hash, company_card_v2_from_snapshot
from product_api.company_reports.persistence.serialization import calculate_company_report_snapshot_hash, company_report_from_snapshot
from product_api.company_reports.company_card_v2.canonical_json import canonical_digest
from .public_h2 import build_public_h2
from .public_h2_models import (
    BLOCK_ORDER, COVERAGE_BLOCKS, CompanyPublicH2Response, PublicH2Action,
    PublicH2Blocks, PublicH2Breadcrumb, PublicH2ClaimCta, PublicH2CoverageItem,
    PublicH2Identity, PublicH2Limitation, PublicH2Narrative, PublicH2Requisites,
    PublicH2SourceItem,
)


class PublicH2Error(RuntimeError):
    code = "company_public_h2_unavailable"


class PublicH2NotFound(PublicH2Error):
    code = "company_public_h2_not_found"


class PublicH2Invalid(PublicH2Error):
    code = "company_public_h2_invalid"


class PublicH2NotEligible(PublicH2Error):
    code = "report_not_eligible"


class PublicH2Pending(PublicH2NotEligible):
    code = "report_pending"


class PublicH2Failed(PublicH2NotEligible):
    code = "report_failed"


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
            record = await session.get(CompanyReportRecord, pin.report_id)
            return _resolve_exact_v3(record, expected_hash=pin.snapshot_hash)
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
    rows = (await session.execute(select(CompanyReportRecord).join(CompanyReportSubject, CompanyReportSubject.id == CompanyReportRecord.subject_id).where(
        CompanyReportSubject.normalized_identifier == inn,
        CompanyReportRecord.writer_profile == "h1_legacy_writer_v2",
        CompanyReportRecord.presentation_contract == "company_public_h1_v1",
        CompanyReportRecord.report_version.in_(("1", "2")),
        CompanyReportRecord.lifecycle_status.in_(("complete", "partial")),
        CompanyReportRecord.normalized_snapshot.is_not(None),
    ).order_by(
        CompanyReportRecord.generated_at.desc().nullslast(),
        desc(CompanyReportRecord.id),
    ))).scalars().all()
    if not rows:
        raise PublicH2NotEligible("company card v2 has no eligible binding")
    for record in rows:
        try:
            return _legacy_preview(record, inn)
        except PublicH2Invalid:
            continue
    raise PublicH2Invalid("legacy company report is invalid")


def _resolve_exact_v3(record: CompanyReportRecord | None, *, expected_hash: str) -> CompanyPublicH2Response:
    if record is None:
        raise PublicH2Invalid("company card v2 binding is invalid")
    try:
        snapshot = company_card_v2_from_snapshot(deepcopy(record.normalized_snapshot))
        if record.snapshot_hash != expected_hash or record.snapshot_hash != calculate_company_card_v2_snapshot_hash(snapshot) or snapshot.report_id != str(record.id):
            raise PublicH2Invalid("company card v2 is invalid")
        # No runtime narrative binding exists in iteration 20.  A stored H2
        # pin is deliberately unresolved, therefore it cannot become public.
        raise PublicH2NotEligible("report_not_eligible")
    except PublicH2Error:
        raise
    except Exception as exc:
        raise PublicH2Invalid("company card v2 is invalid") from exc


def _legacy_preview(record: CompanyReportRecord, inn: str) -> CompanyPublicH2Response:
    # A legacy preview would also require a validated in-memory narrative
    # binding. Iteration 20 intentionally has no runtime source for one.
    raise PublicH2NotEligible("report_not_eligible")


__all__ = ["PublicH2Error", "PublicH2Failed", "PublicH2Invalid", "PublicH2NotEligible", "PublicH2NotFound", "PublicH2Pending", "h2_cohort_selected", "resolve_public_h2"]
