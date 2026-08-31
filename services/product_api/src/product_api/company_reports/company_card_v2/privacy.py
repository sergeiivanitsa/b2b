from __future__ import annotations

from typing import Any

from .models import ArbitrationBasisV1


class PrivacyBoundaryError(ValueError):
    pass


_PUBLIC_FORBIDDEN_KEYS = frozenset({
    "raw_payload", "raw_headers", "headers", "authorization", "api_key", "secret", "token", "opponent", "case_id", "internal_case_identity", "key_id", "provider_free_text", "contact", "email", "phone", "url", "innfl",
})


def validate_private_arbitration_basis(basis: ArbitrationBasisV1) -> None:
    """Validate the private object independently from the public scanner."""
    for case in basis.cases:
        if case.identity.source_kind not in {"case_id", "id"} or not case.identity.value:
            raise PrivacyBoundaryError("invalid private case identity")
        if case.opponent is not None and len(case.opponent.value) != 64:
            raise PrivacyBoundaryError("invalid private opponent token")


def assert_public_boundary_safe(value: object) -> None:
    _scan(value)


def _scan(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower()
            if normalized in _PUBLIC_FORBIDDEN_KEYS or normalized.endswith("_token"):
                raise PrivacyBoundaryError("public value contains a private marker")
            _scan(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _scan(nested)
    elif isinstance(value, str):
        # HMACs are only legitimate as top-level public projection digests,
        # where their key has already been checked by the caller.
        if "authorization:" in value.lower() or "bearer " in value.lower():
            raise PrivacyBoundaryError("public value contains secret-like content")


__all__ = ["PrivacyBoundaryError", "assert_public_boundary_safe", "validate_private_arbitration_basis"]
