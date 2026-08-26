from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CHAR, JSON, DateTime, LargeBinary, SmallInteger, String

from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeArtifact,
    CompanyCardNarrativeJob,
    CompanyCardNarrativeOutbox,
    CompanyCardNarrativeRuntimeControl,
    CompanyReportDataset,
    CompanyReportJob,
    CompanyReportPresentationPin,
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


def test_report_and_job_models_expose_default_off_arbitration_decision() -> None:
    for table in (CompanyReportRecord.__table__, CompanyReportJob.__table__):
        enabled = table.c.arbitration_collection_enabled
        key_id = table.c.arbitration_mask_key_id
        decision = next(
            constraint
            for constraint in table.constraints
            if constraint.name.endswith(f"{table.name}_arbitration_decision")
        )

        assert isinstance(enabled.type, Boolean)
        assert enabled.nullable is False
        assert enabled.default is not None and enabled.default.arg is False
        assert enabled.server_default is not None
        assert str(enabled.server_default.arg) == "false"
        assert isinstance(key_id.type, String)
        assert key_id.type.length == 32
        assert key_id.nullable is True
        assert str(decision.sqltext) == (
            "arbitration_collection_enabled OR arbitration_mask_key_id IS NULL"
        )


def test_narrative_orm_matches_resolved_pin_and_runtime_migration_shape():
    pin = CompanyReportPresentationPin.__table__
    pin_shape = next(
        constraint
        for constraint in pin.constraints
        if constraint.name.endswith("company_report_presentation_pins_contract_shape")
    )
    pin_shape_sql = str(pin_shape.sqltext)
    assert "narrative_binding_status = 'resolved'" in pin_shape_sql
    assert "projection_digest ~ '^[0-9a-f]{64}$'" in pin_shape_sql
    assert "AND projection_digest IS NULL AND chart_facts_version" not in pin_shape_sql
    binding_fk = next(
        constraint
        for constraint in pin.constraints
        if constraint.name == "fk_company_report_h2_pin_narrative_binding"
    )
    assert binding_fk.deferrable is True
    assert binding_fk.initially == "DEFERRED"

    assert isinstance(
        CompanyCardNarrativeArtifact.__table__.c.validated_render_plan_cjson.type,
        LargeBinary,
    )
    assert isinstance(
        CompanyCardNarrativeJob.__table__.c.local_attempt_count.type,
        SmallInteger,
    )
    artifact_fk = next(
        foreign_key
        for foreign_key in CompanyCardNarrativeJob.__table__.c.artifact_id.foreign_keys
        if foreign_key.constraint.name == "fk_company_card_narrative_job_artifact"
    )
    assert artifact_fk.constraint.deferrable is True
    assert artifact_fk.constraint.initially == "DEFERRED"
    assert isinstance(
        CompanyCardNarrativeOutbox.__table__.c.attempt_count.type,
        SmallInteger,
    )
    for table, columns in (
        (CompanyCardNarrativeOutbox.__table__, ("snapshot_hash", "generation_key")),
        (CompanyCardNarrativeJob.__table__, ("snapshot_hash", "generation_key")),
        (
            CompanyCardNarrativeArtifact.__table__,
            (
                "snapshot_hash",
                "generation_key",
                "binding_key",
                "artifact_identity",
                "fallback_identity",
                "validated_render_plan_bytes_sha256",
                "rendered_output_bytes_sha256",
            ),
        ),
    ):
        assert all(
            isinstance(table.c[column].type, CHAR)
            and table.c[column].type.length == 64
            for column in columns
        )
    assert {
        "ix_company_card_narrative_jobs_ready_selection",
        "ix_company_card_narrative_jobs_expired_selection",
    } <= {index.name for index in CompanyCardNarrativeJob.__table__.indexes}
    assert "ix_company_card_narrative_outbox_pending_selection" in {
        index.name for index in CompanyCardNarrativeOutbox.__table__.indexes
    }
    assert "ix_company_card_narrative_artifacts_exact_lookup" in {
        index.name for index in CompanyCardNarrativeArtifact.__table__.indexes
    }
    runtime_check = next(
        constraint
        for constraint in CompanyCardNarrativeRuntimeControl.__table__.constraints
        if constraint.name.endswith("company_card_narrative_runtime_nonnegative")
    )
    assert "concurrency_limit = 0" in str(runtime_check.sqltext)
    assert "concurrency_limit >= leased_count" in str(runtime_check.sqltext)
