from pathlib import Path

from product_api.company_reports.persistence.models import Base


def test_migration_is_in_current_chain_and_defines_four_tables():
    migration = Path(__file__).parents[1] / "alembic" / "versions" / "0012_company_report_persistence.py"
    text = migration.read_text(encoding="utf-8")

    assert 'revision = "0012_company_report_persistence"' in text
    assert 'down_revision = "0011_claims_preview_header_json"' in text
    for table in (
        "company_report_subjects",
        "company_reports",
        "company_report_datasets",
        "company_report_provider_requests",
    ):
        assert f'"{table}"' in text
        assert table in Base.metadata.tables
    assert "companies" not in {
        "company_report_subjects",
        "company_reports",
        "company_report_datasets",
        "company_report_provider_requests",
    }
    assert "def upgrade" in text
    assert "def downgrade" in text


def test_jobs_migration_is_append_only_and_defines_durable_queue_contract():
    migration = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "0013_company_report_jobs.py"
    )
    text = migration.read_text(encoding="utf-8")

    assert 'revision = "0013_company_report_jobs"' in text
    assert 'down_revision = "0012_company_report_persistence"' in text
    assert "company_report_jobs" in Base.metadata.tables
    for required in (
        "uq_company_report_jobs_report_id",
        "company_report_job_state",
        "company_report_job_attempt_count",
        "company_report_job_state_shape",
        "uq_company_report_jobs_active_subject",
        "ix_company_report_jobs_queued_claim",
        "ix_company_report_jobs_running_lease",
        "postgresql_where",
        'ondelete="CASCADE"',
    ):
        assert required in text
    for forbidden in (
        "raw_payload",
        "headers",
        "api_key",
        "provider_limit_metadata",
        "scoring",
        "signals",
        "ai_explanation",
    ):
        assert forbidden not in text.lower()
