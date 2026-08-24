from datetime import datetime, timezone
from uuid import uuid4

from product_api.company_reports.persistence.models import (
    JOB_FAILED_STATE,
    JOB_QUEUED_STATE,
    JOB_RUNNING_STATE,
    JOB_SUCCEEDED_STATE,
    CompanyReportJob,
)


def test_company_report_job_metadata_has_exact_lifecycle_shape():
    table = CompanyReportJob.__table__

    assert {column.name for column in table.columns} == {
        "id",
        "report_id",
        "subject_id",
        "state",
        "writer_profile",
        "presentation_contract",
        "rollout_generation",
        "fence_generation",
        "worker_token",
        "attempt_count",
        "claimed_at",
        "heartbeat_at",
        "lease_expires_at",
        "finished_at",
        "safe_failure_code",
        "created_at",
        "updated_at",
    }
    assert table.columns.report_id.nullable is False
    assert table.columns.subject_id.nullable is False
    assert table.columns.worker_token.nullable is True
    assert table.columns.attempt_count.server_default is not None
    assert {
        JOB_QUEUED_STATE,
        JOB_RUNNING_STATE,
        JOB_SUCCEEDED_STATE,
        JOB_FAILED_STATE,
    } == {"queued", "running", "succeeded", "failed"}

    constraint_names = {constraint.name for constraint in table.constraints}
    assert "uq_company_report_jobs_report_id" in constraint_names
    for suffix in (
        "company_report_job_state",
        "company_report_job_attempt_count",
        "company_report_job_state_shape",
    ):
        assert any(name and name.endswith(suffix) for name in constraint_names)
    index_names = {index.name for index in table.indexes}
    assert index_names == {
        "uq_company_report_jobs_active_subject",
        "ix_company_report_jobs_queued_claim",
        "ix_company_report_jobs_running_lease",
    }
    assert next(
        index for index in table.indexes
        if index.name == "uq_company_report_jobs_active_subject"
    ).unique


def test_company_report_job_foreign_keys_are_cascading():
    table = CompanyReportJob.__table__
    targets = {
        foreign_key.parent.name: (
            foreign_key.target_fullname,
            foreign_key.ondelete,
        )
        for foreign_key in table.foreign_keys
    }

    assert targets == {
        "report_id": ("company_reports.id", "CASCADE"),
        "subject_id": ("company_report_subjects.id", "CASCADE"),
    }


def test_company_report_job_has_no_provider_scoring_or_ai_storage_and_safe_repr():
    forbidden = {
        "raw_payload",
        "headers",
        "authorization",
        "api_key",
        "provider",
        "request_id",
        "scoring",
        "signals",
        "ai",
        "error_text",
    }
    assert not forbidden.intersection(CompanyReportJob.__table__.columns)

    token = uuid4()
    job = CompanyReportJob(
        id=uuid4(),
        report_id=uuid4(),
        subject_id=uuid4(),
        state="running",
        worker_token=token,
        attempt_count=1,
        claimed_at=datetime.now(timezone.utc),
        heartbeat_at=datetime.now(timezone.utc),
        lease_expires_at=datetime.now(timezone.utc),
        safe_failure_code=None,
    )
    rendered = repr(job)
    assert str(token) not in rendered
    assert "safe_failure_code" not in rendered
    assert "running" in rendered
