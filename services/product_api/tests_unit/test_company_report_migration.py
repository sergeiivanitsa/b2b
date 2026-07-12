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
