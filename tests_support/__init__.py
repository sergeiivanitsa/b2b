"""Repository-owned fail-closed helpers for hermetic test suites."""

from .junit_guard import JUnitEvidenceError, JUnitSummary, validate_junit_evidence
from .network_guard import (
    NetworkAccessDenied,
    TestEnvironmentError,
    install_test_network_guard,
    prepare_test_environment,
)

__all__ = [
    "JUnitEvidenceError",
    "JUnitSummary",
    "NetworkAccessDenied",
    "TestEnvironmentError",
    "install_test_network_guard",
    "prepare_test_environment",
    "validate_junit_evidence",
]
