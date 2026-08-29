"""Canonical public H1/H2 document selection.

This is intentionally separate from the generic H2 API resolver: staged H2
work may be inspected through that API, but it cannot displace the canonical
H1 page until a durable assignment exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .company_card_v2.public_h2_models import CompanyPublicH2Response
from .company_card_v2.public_h2_ssr_adapter import resolve_exact_assigned_public_h2
from .company_card_v2.service import (
    ExactPublicH2Dependencies,
    PublicH2Failed,
    PublicH2Invalid,
    PublicH2NotEligible,
    PublicH2Pending,
    _resolve_exact_v3,
)
from .persistence.public_documents import get_public_document_assignment_row
from .persistence.publications import (
    PublicPageRecord,
    PublicSitemapCandidate,
    begin_public_sitemap_snapshot,
    fetch_public_sitemap_candidate_window,
)
from .public_h1 import CompanyPublicH1Response
from .public_h1_service import (
    PublicH1Error,
    PublicH1UnavailableError,
    resolve_public_h1,
    validate_active_publication,
    validate_assigned_public_h1,
)


class PublicDocumentInvalid(RuntimeError):
    code = "public_document_invalid"


class PublicDocumentKind(StrEnum):
    H1 = "h1"
    H2 = "h2"


@dataclass(frozen=True)
class ResolvedPublicDocument:
    kind: PublicDocumentKind
    dto: CompanyPublicH1Response | CompanyPublicH2Response
    assigned: bool


@dataclass(frozen=True)
class PublicSitemapEntry:
    canonical_path: str
    published_lastmod: datetime


@dataclass(frozen=True)
class PublicSitemapScan:
    eligible_count: int
    entries: tuple[PublicSitemapEntry, ...]


async def resolve_public_document(
    session: AsyncSession, *, inn: str,
) -> ResolvedPublicDocument:
    """Resolve one canonical document without staged/head H2 precedence."""
    try:
        captured = await get_public_document_assignment_row(session, inn)
    except SQLAlchemyError as exc:
        raise PublicH1UnavailableError() from exc
    if captured.subject is None or captured.assignment is None:
        # This legacy resolver is expressly allowed only after the joined
        # statement established there is no assignment.
        dto = await resolve_public_h1(session, inn=inn)
        return ResolvedPublicDocument(PublicDocumentKind.H1, dto, False)
    if captured.pin is None or captured.report is None:
        raise PublicDocumentInvalid("assigned public document binding is incomplete")
    contract = captured.assignment.presentation_contract
    if contract == "company_public_h1_v1":
        try:
            dto = validate_assigned_public_h1(
                captured.subject, captured.assignment, captured.pin, captured.report
            )
        except PublicH1Error as exc:
            raise PublicDocumentInvalid("assigned H1 binding is invalid") from exc
        return ResolvedPublicDocument(PublicDocumentKind.H1, dto, True)
    if contract == "company_public_h2_v1":
        scope = getattr(captured.pin, "projection_scope", None)
        active_shape = (
            scope == "active_publication"
            and getattr(captured.pin, "canonical_path", None) is not None
            and getattr(captured.pin, "published_lastmod", None) is not None
            and type(getattr(captured.pin, "indexable", None)) is bool
        )
        if not active_shape:
            raise PublicDocumentInvalid("assigned H2 binding is not active")
        try:
            dto = await resolve_exact_assigned_public_h2(
                session,
                subject=captured.subject,
                assignment=captured.assignment,
                pin=captured.pin,
                report=captured.report,
            )
        except (PublicH2Pending, PublicH2Failed, PublicH2NotEligible):
            raise
        except SQLAlchemyError:
            # The router maps unavailable storage to the established exact
            # public 503 contract; it is not a malformed immutable binding.
            raise
        except Exception as exc:
            raise PublicDocumentInvalid("assigned H2 binding is invalid") from exc
        return ResolvedPublicDocument(PublicDocumentKind.H2, dto, True)
    raise PublicDocumentInvalid("assigned public document contract is invalid")


async def _validate_public_sitemap_candidate(
    session: AsyncSession,
    candidate: PublicSitemapCandidate,
) -> PublicSitemapEntry | None:
    """Apply the canonical H1/H2 validators to one already selected tuple."""
    try:
        if candidate.assignment is None:
            if candidate.publication is None or candidate.report is None:
                return None
            dto = validate_active_publication(
                PublicPageRecord(
                    publication=candidate.publication,
                    report=candidate.report,
                    subject=candidate.subject,
                )
            )
            lastmod = candidate.publication.published_lastmod
        elif candidate.pin is None or candidate.report is None:
            # Assignment presence is terminal: never recover the joined H1
            # publication when its exact tuple is incomplete.
            return None
        elif candidate.assignment.presentation_contract == "company_public_h1_v1":
            dto = validate_assigned_public_h1(
                candidate.subject,
                candidate.assignment,
                candidate.pin,
                candidate.report,
            )
            lastmod = candidate.pin.published_lastmod
        elif candidate.assignment.presentation_contract == "company_public_h2_v1":
            if (
                getattr(candidate.pin, "projection_scope", None)
                != "active_publication"
            ):
                return None
            dto = await _resolve_exact_v3(
                session,
                candidate.report,
                pin=candidate.pin,
                expected_subject_id=candidate.subject.id,
                expected_inn=candidate.subject.normalized_identifier,
                dependencies=ExactPublicH2Dependencies(
                    presentation=candidate.presentation,
                    narrative_job=candidate.narrative_job,
                    narrative_artifact=candidate.narrative_artifact,
                ),
            )
            lastmod = candidate.pin.published_lastmod
        else:
            return None
    except (
        PublicH1Error,
        PublicH2Failed,
        PublicH2Invalid,
        PublicH2NotEligible,
        PublicH2Pending,
        TypeError,
        ValueError,
    ):
        return None
    if not dto.indexable or lastmod is None:
        return None
    return PublicSitemapEntry(dto.canonical_path, lastmod)


async def scan_public_sitemap(
    session: AsyncSession,
    *,
    chunk_size: int,
    chunk_number: int | None,
    validation_window_size: int = 100,
) -> PublicSitemapScan:
    """Validate the finite overlay stream with bounded retained state."""
    if type(chunk_size) is not int or chunk_size <= 0:
        raise ValueError("sitemap chunk size is invalid")
    if chunk_number is not None and (
        type(chunk_number) is not int or chunk_number <= 0
    ):
        raise ValueError("sitemap chunk number is invalid")
    if type(validation_window_size) is not int or not 1 <= validation_window_size <= 100:
        raise ValueError("sitemap validation window is invalid")

    await begin_public_sitemap_snapshot(session)
    first_eligible = (
        0 if chunk_number is None else (chunk_number - 1) * chunk_size
    )
    after = None
    eligible_count = 0
    retained: list[PublicSitemapEntry] = []
    previous_key = None
    while True:
        window = await fetch_public_sitemap_candidate_window(
            session,
            after=after,
            limit=validation_window_size,
        )
        for candidate in window:
            key_tuple = (
                candidate.key.normalized_inn,
                candidate.key.selected_canonical_path,
                candidate.key.subject_id,
            )
            if previous_key is not None and key_tuple <= previous_key:
                raise RuntimeError("sitemap keyset order is invalid")
            previous_key = key_tuple
            entry = await _validate_public_sitemap_candidate(session, candidate)
            if entry is None:
                continue
            if (
                chunk_number is not None
                and first_eligible <= eligible_count < first_eligible + chunk_size
            ):
                retained.append(entry)
            eligible_count += 1
        if not window or len(window) < validation_window_size:
            break
        after = window[-1].key
    return PublicSitemapScan(eligible_count, tuple(retained))


__all__ = [
    "PublicDocumentInvalid", "PublicDocumentKind", "ResolvedPublicDocument",
    "PublicSitemapEntry", "PublicSitemapScan", "resolve_public_document",
    "scan_public_sitemap",
]
