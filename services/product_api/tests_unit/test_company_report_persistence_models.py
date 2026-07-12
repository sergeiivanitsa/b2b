from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime

from product_api.company_reports.persistence.models import (
    CompanyReportDataset,
    CompanyReportProviderRequest,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.db.base import Base


def test_four_persistence_tables_are_separate_from_companies():
    expected = {
        "company_report_subjects",
        "company_reports",
        "company_report_datasets",
        "company_report_provider_requests",
    }
    assert expected.issubset(Base.metadata.tables)
    assert "companies" not in expected


def test_models_have_foreign_keys_unique_constraints_indexes_and_json_columns():
    subject = CompanyReportSubject.__table__
    report = CompanyReportRecord.__table__
    dataset = CompanyReportDataset.__table__
    journal = CompanyReportProviderRequest.__table__

    assert any(column.name == "normalized_identifier" for column in subject.primary_key.columns) is False
    assert any(constraint.name == "uq_company_report_subjects_normalized_identifier" for constraint in subject.constraints)
    assert any(constraint.name == "uq_company_report_datasets_report_id_dataset" for constraint in dataset.constraints)
    assert any(fk.target_fullname == "company_report_subjects.id" for fk in report.c.subject_id.foreign_keys)
    assert any(fk.target_fullname == "company_reports.id" for fk in dataset.c.report_id.foreign_keys)
    assert any(fk.target_fullname == "company_report_datasets.id" for fk in journal.c.dataset_record_id.foreign_keys)
    assert isinstance(report.c.normalized_snapshot.type, JSON)
    assert isinstance(dataset.c.source_metadata.type, JSON)
    assert isinstance(journal.c.provider_limit_metadata.type, JSON)
    assert isinstance(report.c.started_at.type, DateTime)
    assert report.c.started_at.type.timezone is True
    assert any(index.name == "ix_company_reports_subject_generated_created" for index in report.indexes)
    assert any(index.name == "uq_company_reports_pending_subject" for index in report.indexes)


def test_orm_repr_is_safe():
    subject = CompanyReportSubject(
        id=uuid4(), normalized_identifier="0000000000", identifier_type="legal_entity_inn"
    )
    report = CompanyReportRecord(
        id=uuid4(),
        subject_id=subject.id,
        report_version="1",
        lifecycle_status="pending",
        started_at=datetime.now(timezone.utc),
        normalized_snapshot={"secret_marker": "must-not-be-in-repr"},
    )
    dataset = CompanyReportDataset(
        id=uuid4(),
        report_id=report.id,
        dataset="finance",
        status="available",
        normalized_snapshot={"secret_marker": "must-not-be-in-repr"},
    )

    assert "0000000000" not in repr(subject)
    assert "secret_marker" not in repr(report)
    assert "secret_marker" not in repr(dataset)
