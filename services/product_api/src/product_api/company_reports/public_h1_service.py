"""Read-only resolver and shared pure active-publication validator."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from .persistence.models import PUBLICATION_POLICY_VERSION
from .persistence.public_h1 import get_publication_resolution_record, list_report_resolution_records
from .persistence.serialization import calculate_company_report_snapshot_hash, company_report_from_snapshot
from .public_h1 import CompanyPublicH1Response, build_public_h1

_INN = re.compile(r"^(?:[0-9]{10}|[0-9]{12})$")
_CANONICAL = re.compile(r"^/company/(?P<inn>[0-9]{10}(?:[0-9]{2})?)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$")
_SUFFICIENCY = {
    "sufficient", "report_not_finalized", "report_not_usable",
    "invalid_or_private_snapshot", "insufficient_scoring", "thin_content",
    "partial_insufficient",
}


class PublicH1Error(RuntimeError):
    code = "public_projection_invalid"
    message = "public company projection is invalid"


class PublicH1InvalidInnError(PublicH1Error):
    code = "invalid_inn"
    message = "invalid INN"


class PublicH1NotFoundError(PublicH1Error):
    code = "company_report_not_found"
    message = "company report not found"


class PublicH1PendingError(PublicH1Error):
    code = "report_pending"
    message = "company report is pending"


class PublicH1FailedError(PublicH1Error):
    code = "report_failed"
    message = "company report failed"


class PublicH1NotEligibleError(PublicH1Error):
    code = "report_not_eligible"
    message = "company report is not eligible for public projection"


class PublicProjectionInvalidError(PublicH1Error):
    pass


class PublicH1UnavailableError(PublicH1Error):
    code = "company_report_unavailable"
    message = "company report service is unavailable"


def _inn(value: str) -> str:
    if type(value) is not str or not value.isascii() or _INN.fullmatch(value) is None:
        raise PublicH1InvalidInnError()
    return value


def _same_time(left: datetime | None, right: datetime | None) -> bool:
    if left is None or right is None or left.tzinfo is None or right.tzinfo is None:
        return False
    return left.astimezone(timezone.utc) == right.astimezone(timezone.utc)


def _validated_report(record: Any, subject: Any, expected_hash: str | None = None):
    if (
        record is None
        or record.subject_id != subject.id
        or record.lifecycle_status not in {"complete", "partial"}
        or not isinstance(record.normalized_snapshot, dict)
        or not record.snapshot_hash
        or record.generated_at is None
    ):
        raise PublicProjectionInvalidError()
    # Hash the untouched raw dictionary before the strict parser can apply any
    # defaults.  The parser then checks its explicit raw discriminator.
    try:
        raw_hash = calculate_company_report_snapshot_hash(record.normalized_snapshot)
    except Exception as exc:
        raise PublicProjectionInvalidError() from exc
    if raw_hash != record.snapshot_hash or (expected_hash is not None and raw_hash != expected_hash):
        raise PublicProjectionInvalidError()
    try:
        report = company_report_from_snapshot(record.normalized_snapshot)
    except Exception as exc:
        raise PublicProjectionInvalidError() from exc
    if (
        report.report_id != record.id
        or report.report_version != record.report_version
        or report.status.value != record.lifecycle_status
        or not _same_time(report.generated_at, record.generated_at)
        or report.target_identifier != subject.normalized_identifier
        or report.counterparty is None
        or report.counterparty.inn != subject.normalized_identifier
    ):
        raise PublicProjectionInvalidError()
    return report


def validate_active_publication(record: Any) -> CompanyPublicH1Response:
    """Pure complete pin predicate shared by resolver, SSR and sitemap."""
    publication, subject, report_record = record.publication, record.subject, record.report
    if (
        publication.status != "active"
        or publication.subject_id != subject.id
        or report_record is None
        or publication.report_id != report_record.id
        or report_record.subject_id != subject.id
        or publication.policy_version != PUBLICATION_POLICY_VERSION
        or publication.sufficiency_status not in _SUFFICIENCY
        or (publication.indexable and publication.sufficiency_status != "sufficient")
        or not publication.snapshot_hash
        or publication.published_lastmod is None
    ):
        raise PublicProjectionInvalidError()
    canonical = _CANONICAL.fullmatch(publication.canonical_path or "")
    if (
        canonical is None
        or canonical.group("inn") != subject.normalized_identifier
        or publication.canonical_slug != canonical.group("slug")
    ):
        raise PublicProjectionInvalidError()
    report = _validated_report(report_record, subject, publication.snapshot_hash)
    if not _same_time(publication.published_lastmod, report_record.generated_at):
        raise PublicProjectionInvalidError()
    try:
        dto = build_public_h1(
            report,
            projection_scope="published",
            persisted_canonical_path=publication.canonical_path,
            persisted_indexable=publication.indexable,
        )
    except Exception as exc:
        raise PublicProjectionInvalidError() from exc
    if dto.canonical_path != publication.canonical_path or dto.indexable != bool(publication.indexable):
        raise PublicProjectionInvalidError()
    return dto


def validate_assigned_public_h1(
    subject: Any, assignment: Any, pin: Any, report_record: Any
) -> CompanyPublicH1Response:
    """Validate and reproduce an exact immutable H1 presentation pin.

    Canonical selection calls this only for the tuple returned by its single
    joined SELECT.  In particular, it must not consult active publications or
    latest reports: a corrupt assigned pin fails closed.
    """
    if (
        subject is None
        or assignment is None
        or pin is None
        or report_record is None
        or assignment.subject_id != subject.id
        or assignment.presentation_contract != "company_public_h1_v1"
        or assignment.pin_generation != pin.generation
        or pin.subject_id != subject.id
        or pin.presentation_contract != "company_public_h1_v1"
        or pin.report_id != report_record.id
        or report_record.subject_id != subject.id
        or pin.publication_policy_version != PUBLICATION_POLICY_VERSION
        or pin.indexable is not True
        or not isinstance(pin.snapshot_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", pin.snapshot_hash)
        or pin.canonical_path is None
        or pin.published_lastmod is None
    ):
        raise PublicProjectionInvalidError()
    canonical = _CANONICAL.fullmatch(pin.canonical_path)
    if canonical is None or canonical.group("inn") != subject.normalized_identifier:
        raise PublicProjectionInvalidError()
    report = _validated_report(report_record, subject, pin.snapshot_hash)
    if not _same_time(pin.published_lastmod, report_record.generated_at):
        raise PublicProjectionInvalidError()
    try:
        dto = build_public_h1(
            report,
            projection_scope="published",
            persisted_canonical_path=pin.canonical_path,
            persisted_indexable=True,
        )
    except Exception as exc:
        raise PublicProjectionInvalidError() from exc
    if dto.canonical_path != pin.canonical_path or dto.indexable is not True:
        raise PublicProjectionInvalidError()
    return dto


async def resolve_public_h1(session: Any, *, inn: str) -> CompanyPublicH1Response:
    normalized = _inn(inn)
    try:
        pinned = await get_publication_resolution_record(session, normalized)
        if pinned is not None and pinned.publication.status == "active":
            # A corrupt active row is an integrity error.  Never scan history.
            return validate_active_publication(pinned)
        records = await list_report_resolution_records(session, normalized)
    except PublicH1Error:
        raise
    except SQLAlchemyError as exc:
        raise PublicH1UnavailableError() from exc
    if not records:
        raise PublicH1NotFoundError()
    for item in records:
        try:
            report = _validated_report(item.report, item.subject)
            return build_public_h1(report, projection_scope="latest_unpublished")
        except (PublicProjectionInvalidError, ValueError):
            continue
    latest = records[0].report.lifecycle_status
    if latest == "pending":
        raise PublicH1PendingError()
    if latest == "failed":
        raise PublicH1FailedError()
    raise PublicH1NotEligibleError()


__all__ = [
    "PublicH1Error", "PublicH1InvalidInnError", "PublicH1NotFoundError",
    "PublicH1PendingError", "PublicH1FailedError", "PublicH1NotEligibleError",
    "PublicProjectionInvalidError", "PublicH1UnavailableError", "resolve_public_h1",
    "validate_active_publication", "validate_assigned_public_h1",
]
