"""Trusted, deliberately narrow CompanyReport-to-Claims projection."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.persistence.models import (
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
    company_report_from_snapshot,
)
from product_api.company_reports.persistence.errors import CompanyReportSnapshotError
from product_api.company_reports.persistence.v3 import (
    calculate_company_card_v2_snapshot_hash,
    company_card_v2_from_snapshot,
)


@dataclass(frozen=True, slots=True)
class CompanyReportHandoff:
    report_id: UUID
    debtor_name: str | None
    debtor_inn: str

    def debtor_fields(self) -> dict[str, str | None]:
        return {"debtor_name": self.debtor_name, "debtor_inn": self.debtor_inn}


@dataclass(frozen=True, slots=True)
class HandoffResolution:
    handoff: CompanyReportHandoff | None
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.handoff is not None


async def resolve_company_report_handoff(
    session: AsyncSession, report_id: UUID
) -> HandoffResolution:
    """Resolve a report without accepting client-side company identity data.

    A snapshot is accepted only if both its immutable hash and all record/subject
    correspondence checks hold.  This rejects a valid snapshot copied from a
    different report record.
    """
    result = await session.execute(
        select(CompanyReportRecord, CompanyReportSubject)
        .join(CompanyReportSubject, CompanyReportRecord.subject_id == CompanyReportSubject.id)
        .where(CompanyReportRecord.id == report_id)
    )
    row = result.one_or_none()
    if row is None:
        return HandoffResolution(None, "report_not_found")
    record, subject = row
    if record.lifecycle_status == "pending":
        return HandoffResolution(None, "report_pending")
    if record.lifecycle_status == "failed":
        return HandoffResolution(None, "report_failed")
    if record.lifecycle_status not in {"complete", "partial"}:
        return HandoffResolution(None, "report_unavailable")
    if not isinstance(record.normalized_snapshot, dict) or not record.snapshot_hash:
        return HandoffResolution(None, "identity_unavailable")

    snapshot = deepcopy(record.normalized_snapshot)
    if record.report_version == "3":
        return _resolve_v3_handoff(record, subject.normalized_identifier, snapshot)
    try:
        if calculate_company_report_snapshot_hash(snapshot) != record.snapshot_hash:
            return HandoffResolution(None, "invalid_report")
        report = company_report_from_snapshot(snapshot)
    except (CompanyReportSnapshotError, TypeError, ValueError):
        return HandoffResolution(None, "invalid_report")

    counterparty = report.counterparty
    if (
        report.report_id != record.id
        or report.report_version != record.report_version
        or report.status.value != record.lifecycle_status
        or report.target_identifier != subject.normalized_identifier
        or counterparty is None
        or counterparty.inn != subject.normalized_identifier
    ):
        return HandoffResolution(None, "invalid_report")

    debtor_name = _first_non_empty(counterparty.short_name, counterparty.full_name)
    return HandoffResolution(
        CompanyReportHandoff(
            report_id=record.id,
            debtor_name=debtor_name,
            debtor_inn=counterparty.inn,
        )
    )


def _resolve_v3_handoff(record: CompanyReportRecord, subject_inn: str, snapshot: dict[object, object]) -> HandoffResolution:
    """V3 Claims handoff remains exact-report and exposes identity only."""
    try:
        card = company_card_v2_from_snapshot(snapshot)
        if (
            record.report_version != "3"
            or record.writer_profile != "company_card_v2_writer_v3"
            or record.presentation_contract != "company_public_h2_v1"
            or not isinstance(getattr(record, "rollout_generation", None), int)
            or record.rollout_generation <= 0
            or record.snapshot_hash != calculate_company_card_v2_snapshot_hash(card)
            or card.report_id != str(record.id)
            or card.rollout_config_generation != record.rollout_generation
            or card.subject_inn != subject_inn
            or card.target_inn != subject_inn
            or card.counterparty.inn != subject_inn
        ):
            return HandoffResolution(None, "invalid_report")
    except (CompanyReportSnapshotError, TypeError, ValueError):
        return HandoffResolution(None, "invalid_report")
    return HandoffResolution(CompanyReportHandoff(
        report_id=record.id,
        debtor_name=_first_non_empty(card.counterparty.short_name, card.counterparty.full_name),
        debtor_inn=card.counterparty.inn,
    ))


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
