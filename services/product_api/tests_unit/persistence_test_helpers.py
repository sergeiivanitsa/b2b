from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.sql import Select

from product_api.company_reports.persistence.models import (
    CompanyReportDataset,
    CompanyReportProviderRequest,
    CompanyReportRecord,
    CompanyReportSubject,
)


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeAsyncSession:
    """Small in-memory AsyncSession double; it never creates a DB engine."""

    def __init__(self) -> None:
        self.subjects: list[CompanyReportSubject] = []
        self.reports: list[CompanyReportRecord] = []
        self.datasets: list[CompanyReportDataset] = []
        self.journals: list[CompanyReportProviderRequest] = []
        self.added: list[object] = []
        self.flush_count = 0
        self.commit_count = 0

    def add(self, value: object) -> None:
        self.added.append(value)
        if isinstance(value, CompanyReportSubject) and value not in self.subjects:
            self.subjects.append(value)
        elif isinstance(value, CompanyReportRecord) and value not in self.reports:
            self.reports.append(value)
        elif isinstance(value, CompanyReportDataset) and value not in self.datasets:
            self.datasets.append(value)
        elif isinstance(value, CompanyReportProviderRequest) and value not in self.journals:
            self.journals.append(value)

    async def flush(self) -> None:
        self.flush_count += 1
        now = datetime.now(timezone.utc)
        for subject in self.subjects:
            if subject.id is None:
                subject.id = uuid4()
            if subject.created_at is None:
                subject.created_at = now
            if subject.updated_at is None:
                subject.updated_at = now
        for report in self.reports:
            if report.id is None:
                report.id = uuid4()
            if report.created_at is None:
                report.created_at = now
            if report.updated_at is None:
                report.updated_at = now
        for dataset in self.datasets:
            if dataset.id is None:
                dataset.id = uuid4()
        for journal in self.journals:
            if journal.id is None:
                journal.id = uuid4()

    async def commit(self) -> None:
        self.commit_count += 1

    async def execute(self, statement: Select) -> ScalarResult:
        entity = statement.column_descriptions[0]["entity"]
        params = statement.compile().params
        if entity is CompanyReportSubject:
            subject_id = next(
                (value for key, value in params.items() if key.startswith("id") and isinstance(value, UUID)),
                None,
            )
            identifier = next(
                (
                    value
                    for value in params.values()
                    if isinstance(value, str) and value.isdigit() and len(value) in {10, 12, 13, 15}
                ),
                None,
            )
            value = next(
                (
                    subject
                    for subject in self.subjects
                    if (subject_id is not None and subject.id == subject_id)
                    or (identifier is not None and subject.normalized_identifier == identifier)
                ),
                None,
            )
            return ScalarResult(value)

        report_id = next(
            (value for key, value in params.items() if key.startswith("id") and isinstance(value, UUID)),
            None,
        )
        identifier = next(
            (
                value
                for value in params.values()
                if isinstance(value, str) and value.isdigit() and len(value) in {10, 12, 13, 15}
            ),
            None,
        )
        subject_id = next(
            (
                value
                for key, value in params.items()
                if key.startswith("subject_id")
                and isinstance(value, UUID)
                and any(subject.id == value for subject in self.subjects)
            ),
            None,
        )
        candidates = self.reports
        if report_id is not None:
            candidates = [report for report in candidates if report.id == report_id]
        if subject_id is not None:
            candidates = [report for report in candidates if report.subject_id == subject_id]
        if identifier is not None:
            subject_ids = {
                subject.id for subject in self.subjects if subject.normalized_identifier == identifier
            }
            candidates = [report for report in candidates if report.subject_id in subject_ids]
        lifecycle = next(
            (
                value
                for value in params.values()
                if isinstance(value, str)
                and value in {"pending", "complete", "partial", "failed"}
            ),
            None,
        )
        if lifecycle is not None:
            candidates = [report for report in candidates if report.lifecycle_status == lifecycle]
        statement_text = str(statement)
        where_text = statement_text.split("WHERE", 1)[1] if "WHERE" in statement_text else ""
        if "normalized_snapshot IS NOT NULL" in where_text:
            candidates = [report for report in candidates if report.normalized_snapshot is not None]
            candidates = [
                report
                for report in candidates
                if report.lifecycle_status in {"complete", "partial"}
            ]
        if "fresh_until >" in where_text:
            now = next(
                (value for value in params.values() if isinstance(value, datetime)),
                None,
            )
            candidates = [
                report
                for report in candidates
                if report.fresh_until is not None
                and now is not None
                and report.fresh_until > now
                and report.usable_for_public_page
            ]
        candidates = sorted(
            candidates,
            key=lambda report: (
                report.generated_at or report.created_at or datetime.min.replace(tzinfo=timezone.utc),
                report.created_at or datetime.min.replace(tzinfo=timezone.utc),
                str(report.id),
            ),
            reverse=True,
        )
        return ScalarResult(candidates[0] if candidates else None)
