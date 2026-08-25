"""Canonical public H1/H2 document selection.

This is intentionally separate from the generic H2 API resolver: staged H2
work may be inspected through that API, but it cannot displace the canonical
H1 page until a durable assignment exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .company_card_v2.public_h2_models import CompanyPublicH2Response
from .company_card_v2.public_h2_ssr_adapter import resolve_exact_assigned_public_h2
from .company_card_v2.service import PublicH2Failed, PublicH2NotEligible, PublicH2Pending
from .persistence.public_documents import get_public_document_assignment_row
from .public_h1 import CompanyPublicH1Response
from .public_h1_service import (
    PublicH1Error,
    PublicH1UnavailableError,
    resolve_public_h1,
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


__all__ = [
    "PublicDocumentInvalid", "PublicDocumentKind", "ResolvedPublicDocument",
    "resolve_public_document",
]
