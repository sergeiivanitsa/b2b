from __future__ import annotations

import re
from typing import Any

from .models import ArbitrationBasisV1


class PrivacyBoundaryError(ValueError):
    pass


_PUBLIC_FORBIDDEN_KEYS = frozenset({
    "raw_payload", "raw_headers", "headers", "authorization", "api_key", "secret",
    "token", "opponent", "opponent_identifier", "opponent_name", "case_id",
    "internal_case_identity", "key_id", "provider_free_text", "provider", "raw",
    "contact", "contacts", "email", "phone", "url", "innfl", "passport",
    "manager_inn", "owner_inn", "kad_arbitr_link",
})
_FORBIDDEN_KEY_PARTS = frozenset({"authorization", "api", "key", "secret", "token", "opponent", "case", "contact", "email", "phone", "url", "raw", "provider", "innfl"})
_SECRET_VALUE_RE = re.compile(r"(?:^|\s)(?:bearer|basic)\s+\S+|(?:api[_ -]?key|authorization)\s*[:=]", re.IGNORECASE)
_URL_RE = re.compile(r"https?://", re.IGNORECASE)


def validate_private_arbitration_basis(basis: ArbitrationBasisV1) -> None:
    """Validate the private object independently from the public scanner."""
    for case in basis.cases:
        if case.identity.source_kind not in {"case_id", "id"} or not case.identity.value:
            raise PrivacyBoundaryError("invalid private case identity")
        if case.opponent is not None:
            if len(case.opponent.value) != 64 or not re.fullmatch(r"[0-9a-f]{64}", case.opponent.value):
                raise PrivacyBoundaryError("invalid private opponent token")
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", case.opponent.key_id):
                raise PrivacyBoundaryError("invalid private masking key id")


def assert_public_boundary_safe(value: object) -> None:
    _scan(value)


def _scan(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            parts = tuple(part for part in re.split(r"[_\-.\s]+", normalized) if part)
            if (
                normalized in _PUBLIC_FORBIDDEN_KEYS
                or normalized.endswith("_token")
                or normalized.startswith("x-") and any(part in _FORBIDDEN_KEY_PARTS for part in parts)
                or any(part in {"authorization", "secret", "token", "opponent", "contact", "email", "phone", "innfl"} for part in parts)
            ):
                raise PrivacyBoundaryError("public value contains a private marker")
            _scan(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _scan(nested)
    elif isinstance(value, str):
        # HMACs are legitimate under a safe named digest key.  Credentials and
        # identifier-bearing URLs are never legitimate at a public sink.
        if _SECRET_VALUE_RE.search(value) or _URL_RE.search(value):
            raise PrivacyBoundaryError("public value contains secret-like content")


__all__ = ["PrivacyBoundaryError", "assert_public_boundary_safe", "validate_private_arbitration_basis"]
