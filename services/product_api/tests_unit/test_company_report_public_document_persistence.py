from __future__ import annotations

from product_api.company_reports.persistence.public_documents import get_public_document_assignment_row


class _Result:
    def one_or_none(self):
        return None


class _Session:
    def __init__(self): self.statements = []
    async def execute(self, statement):
        self.statements.append(statement)
        return _Result()


def test_assignment_lookup_is_one_joined_statement_without_second_assignment_read() -> None:
    # The function body deliberately owns exactly one session execute; the
    # assertion protects canonical selection against future N+1 assignment IO.
    import inspect
    source = inspect.getsource(get_public_document_assignment_row)
    assert source.count("session.execute") == 1
    assert "outerjoin" in source
    assert "CompanyReportPresentationAssignment" in source
    assert "CompanyReportPresentationPin" in source
    assert "CompanyReportRecord" in source


async def test_assignment_lookup_executes_one_compilable_outer_join_statement() -> None:
    session = _Session()
    row = await get_public_document_assignment_row(session, "7701234567")
    assert row.subject is row.assignment is row.pin is row.report is None
    assert len(session.statements) == 1
    sql = str(session.statements[0])
    assert sql.count("LEFT OUTER JOIN") == 3
    assert "company_report_presentation_assignments" in sql
    assert "company_report_presentation_pins" in sql
    assert "company_reports" in sql
