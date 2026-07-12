from __future__ import annotations


class CompanyReportPersistenceError(RuntimeError):
    """Safe base error for report persistence operations."""


class CompanyReportNotFoundError(CompanyReportPersistenceError):
    pass


class CompanyReportStateConflictError(CompanyReportPersistenceError):
    pass


class CompanyReportSnapshotError(CompanyReportPersistenceError):
    pass


class PendingCompanyReportAlreadyExistsError(CompanyReportPersistenceError):
    pass
