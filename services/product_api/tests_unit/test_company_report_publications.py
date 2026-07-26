from product_api.company_reports.persistence.models import (
    CompanyReportPublication,
    CompanyReportPublicationBatch,
    CompanyReportPublicationBatchItem,
    CompanyReportPublicationControl,
    CompanyReportPublicationJournal,
)


def test_publication_schema_has_five_separate_fail_closed_tables():
    assert CompanyReportPublicationControl.__table__.name == "company_report_publication_control"
    assert CompanyReportPublication.__table__.name == "company_report_publications"
    assert CompanyReportPublicationBatch.__table__.name == "company_report_publication_batches"
    assert CompanyReportPublicationBatchItem.__table__.name == "company_report_publication_batch_items"
    assert CompanyReportPublicationJournal.__table__.name == "company_report_publication_journal"
    assert any(index.name == "ix_company_report_publications_sitemap" for index in CompanyReportPublication.__table__.indexes)
    assert str(CompanyReportPublication.__table__.c.indexable.server_default.arg) == "false"
    assert str(CompanyReportPublicationBatch.__table__.c.next_ordinal.server_default.arg) == "0"


def test_publication_reason_constraints_cover_every_policy_outcome():
    item_constraints = {
        str(constraint.name): str(constraint.sqltext)
        for constraint in CompanyReportPublicationBatchItem.__table__.constraints
        if getattr(constraint, "name", None) and hasattr(constraint, "sqltext")
    }
    journal_constraints = {
        str(constraint.name): str(constraint.sqltext)
        for constraint in CompanyReportPublicationJournal.__table__.constraints
        if getattr(constraint, "name", None) and hasattr(constraint, "sqltext")
    }
    item_reason = next(
        value
        for name, value in item_constraints.items()
        if name.endswith("company_report_publication_batch_item_reason")
    )
    journal_reason = next(
        value
        for name, value in journal_constraints.items()
        if name.endswith("company_report_publication_journal_reason")
    )
    for reason in ("report_not_finalized", "report_not_usable"):
        assert reason in item_reason
        assert reason in journal_reason
