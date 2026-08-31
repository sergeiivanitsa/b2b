"""Read-only records for the public-H1 resolver."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import CompanyReportPublication, CompanyReportRecord, CompanyReportSubject

@dataclass(frozen=True)
class PublicationResolutionRecord:
    publication: CompanyReportPublication
    subject: CompanyReportSubject
    report: CompanyReportRecord | None

@dataclass(frozen=True)
class ReportResolutionRecord:
    report: CompanyReportRecord
    subject: CompanyReportSubject
    normalized_snapshot: dict[str, Any] | None

async def get_publication_resolution_record(session: AsyncSession, inn: str) -> PublicationResolutionRecord | None:
    row = (await session.execute(select(CompanyReportPublication, CompanyReportSubject, CompanyReportRecord).join(CompanyReportSubject, CompanyReportSubject.id == CompanyReportPublication.subject_id).outerjoin(CompanyReportRecord, CompanyReportRecord.id == CompanyReportPublication.report_id).where(CompanyReportSubject.normalized_identifier == inn, CompanyReportRecord.writer_profile == "h1_legacy_writer_v2", CompanyReportRecord.presentation_contract == "company_public_h1_v1", CompanyReportRecord.report_version.in_(("1", "2"))))).one_or_none()
    return PublicationResolutionRecord(row[0], row[1], row[2]) if row else None

async def list_report_resolution_records(session: AsyncSession, inn: str) -> list[ReportResolutionRecord]:
    rows = (await session.execute(select(CompanyReportRecord, CompanyReportSubject).join(CompanyReportSubject, CompanyReportSubject.id == CompanyReportRecord.subject_id).where(CompanyReportSubject.normalized_identifier == inn, CompanyReportRecord.writer_profile == "h1_legacy_writer_v2", CompanyReportRecord.presentation_contract == "company_public_h1_v1", CompanyReportRecord.report_version.in_(("1", "2"))).order_by(desc(CompanyReportRecord.created_at), desc(CompanyReportRecord.id)))).all()
    return [ReportResolutionRecord(record, subject, deepcopy(record.normalized_snapshot) if record.normalized_snapshot is not None else None) for record, subject in rows]
