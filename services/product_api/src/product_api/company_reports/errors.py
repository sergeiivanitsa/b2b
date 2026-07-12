from __future__ import annotations


class CompanyReportNormalizationError(ValueError):
    """Base error for safe, deterministic provider payload normalization."""

    def __init__(
        self,
        message: str,
        *,
        dataset: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.dataset = dataset
        self.endpoint = endpoint


class DatasetMismatchError(CompanyReportNormalizationError):
    def __init__(
        self,
        *,
        expected_dataset: str,
        actual_dataset: str,
        expected_endpoint: str,
        actual_endpoint: str,
    ) -> None:
        super().__init__(
            "DataNewton result does not match the requested dataset",
            dataset=actual_dataset,
            endpoint=actual_endpoint,
        )
        self.expected_dataset = expected_dataset
        self.expected_endpoint = expected_endpoint


class InvalidDatasetPayloadError(CompanyReportNormalizationError):
    pass


class CompanyReportInputError(CompanyReportNormalizationError):
    """The report input cannot be normalized before provider calls."""
