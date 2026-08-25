"""Single-statement public document assignment lookup.

The canonical page must never compose an assignment, pin and report from
different snapshots.  This helper deliberately returns the tuple selected by
one SQL statement; callers must not re-read the assignment.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    CompanyReportPresentationAssignment,
    CompanyReportPresentationPin,
    CompanyReportRecord,
    CompanyReportSubject,
)


@dataclass(frozen=True)
class PublicDocumentAssignmentRow:
    subject: CompanyReportSubject | None
    assignment: CompanyReportPresentationAssignment | None
    pin: CompanyReportPresentationPin | None
    report: CompanyReportRecord | None


async def get_public_document_assignment_row(
    session: AsyncSession, inn: str
) -> PublicDocumentAssignmentRow:
    """Read subject and its exact assignment tuple in one SELECT."""
    statement = (
        select(
            CompanyReportSubject,
            CompanyReportPresentationAssignment,
            CompanyReportPresentationPin,
            CompanyReportRecord,
        )
        .outerjoin(
            CompanyReportPresentationAssignment,
            CompanyReportPresentationAssignment.subject_id == CompanyReportSubject.id,
        )
        .outerjoin(
            CompanyReportPresentationPin,
            and_(
                CompanyReportPresentationPin.subject_id
                == CompanyReportPresentationAssignment.subject_id,
                CompanyReportPresentationPin.presentation_contract
                == CompanyReportPresentationAssignment.presentation_contract,
                CompanyReportPresentationPin.generation
                == CompanyReportPresentationAssignment.pin_generation,
            ),
        )
        .outerjoin(
            CompanyReportRecord,
            and_(
                CompanyReportRecord.id == CompanyReportPresentationPin.report_id,
                CompanyReportRecord.subject_id == CompanyReportSubject.id,
            ),
        )
        .where(CompanyReportSubject.normalized_identifier == inn)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return PublicDocumentAssignmentRow(None, None, None, None)
    return PublicDocumentAssignmentRow(*row)


__all__ = ["PublicDocumentAssignmentRow", "get_public_document_assignment_row"]
