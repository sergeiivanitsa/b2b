from __future__ import annotations


class DataNewtonError(Exception):
    """Base error carrying only context that is safe to log or display."""

    def __init__(
        self,
        message: str,
        *,
        endpoint: str,
        status_code: int | None = None,
        retryable: bool = False,
        attempts: int = 0,
        request_id: str | None = None,
        dataset: str | None = None,
        identifier_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.endpoint = endpoint
        self.status_code = status_code
        self.retryable = retryable
        self.attempts = attempts
        self.request_id = request_id
        self.dataset = dataset
        self.identifier_type = identifier_type

    def __str__(self) -> str:
        return (
            f"{self.message} (endpoint={self.endpoint!r}, "
            f"status_code={self.status_code!r}, retryable={self.retryable!r}, "
            f"attempts={self.attempts!r}, request_id={self.request_id!r}, "
            f"dataset={self.dataset!r}, identifier_type={self.identifier_type!r})"
        )

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(message={self.message!r}, "
            f"endpoint={self.endpoint!r}, status_code={self.status_code!r}, "
            f"retryable={self.retryable!r}, attempts={self.attempts!r}, "
            f"request_id={self.request_id!r}, dataset={self.dataset!r}, "
            f"identifier_type={self.identifier_type!r})"
        )


class DataNewtonDisabledError(DataNewtonError):
    """The provider is disabled by configuration."""


class DataNewtonConfigurationError(DataNewtonError):
    """The provider configuration cannot be used."""


class DataNewtonValidationError(DataNewtonError, ValueError):
    """Input data is not valid for a DataNewton operation."""


class DataNewtonAuthenticationError(DataNewtonError):
    """DataNewton rejected provider credentials."""


class DataNewtonAccessDeniedError(DataNewtonError):
    """The configured credentials cannot access this DataNewton endpoint."""


class DataNewtonRateLimitError(DataNewtonError):
    """DataNewton rate limiting persisted after retries."""


class DataNewtonNotFoundError(DataNewtonError):
    """The requested DataNewton resource was not found."""


class DataNewtonServerError(DataNewtonError):
    """DataNewton returned a server-side error."""


class DataNewtonNetworkError(DataNewtonError):
    """The request could not be completed because of a transport failure."""


class DataNewtonInvalidResponseError(DataNewtonError):
    """DataNewton returned a response that cannot be safely consumed."""


class DataNewtonUnsupportedIdentifierError(DataNewtonError):
    """The dataset does not support this otherwise valid identifier type."""

