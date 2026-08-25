"""Read-only H2 adapter shared by SSR/crawler callers.

It intentionally delegates to the exact persistence resolver and contains no
writer, queue, provider, AI or fallback-renderer dependency.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from .service import _resolve_exact_v3, resolve_public_h2
from .public_h2_models import CompanyPublicH2Response


async def resolve_public_h2_ssr(session: AsyncSession, *, inn: str) -> CompanyPublicH2Response:
    return await resolve_public_h2(session, inn=inn)


async def resolve_exact_assigned_public_h2(
    session: AsyncSession, *, subject: object, assignment: object, pin: object, report: object
) -> CompanyPublicH2Response:
    """Reproduce exactly the H2 tuple captured by canonical selection.

    This function deliberately does not look up assignments, staged pointers,
    lifecycle heads or alternate reports.  It delegates only the artifact
    validation that is intrinsic to the supplied immutable pin.
    """
    if (
        getattr(assignment, "subject_id", None) != getattr(subject, "id", None)
        or getattr(assignment, "presentation_contract", None) != "company_public_h2_v1"
        or getattr(assignment, "pin_generation", None) != getattr(pin, "generation", None)
        or getattr(pin, "subject_id", None) != getattr(subject, "id", None)
        or getattr(pin, "report_id", None) != getattr(report, "id", None)
        or getattr(report, "subject_id", None) != getattr(subject, "id", None)
    ):
        raise ValueError("assigned H2 binding is invalid")
    return await _resolve_exact_v3(
        session,
        report,
        pin=pin,
        expected_subject_id=getattr(subject, "id"),
        expected_inn=getattr(subject, "normalized_identifier"),
    )
