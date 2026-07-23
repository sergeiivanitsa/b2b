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


class CompanyReportJobStateConflictError(CompanyReportPersistenceError):
    """Stored report/job lifecycle invariants do not match."""


class CompanyReportJobFencingError(CompanyReportPersistenceError):
    """The caller no longer owns a live running job."""


class CompanyReportJobNotFoundError(CompanyReportPersistenceError):
    """The durable job does not exist."""
