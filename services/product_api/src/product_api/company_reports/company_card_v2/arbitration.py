from __future__ import annotations

import hmac
import hashlib
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

from .evidence import arbitration_provider_allowed
from .models import ArbitrationBasisV1, InternalCaseIdentityV1, LimitationV1, PrivateArbitrationCaseV1, PrivateOpponentTokenV1

MAX_ROWS = 1000
MAX_CASES = 1000


class ArbitrationGateClosedError(RuntimeError):
    code = "arbitration_provider_gate_closed"


def require_arbitration_provider_gate(registry: object = None) -> None:
    if not arbitration_provider_allowed(registry if isinstance(registry, dict) else None):
        raise ArbitrationGateClosedError("arbitration provider envelope is not verified")


def private_opponent_token(*, secret: bytes, key_id: str, opponent_identifier: str) -> PrivateOpponentTokenV1:
    if not secret:
        raise ValueError("masking secret is required")
    value = hmac.new(secret, opponent_identifier.encode("utf-8"), hashlib.sha256).hexdigest()
    return PrivateOpponentTokenV1(key_id=key_id, value=value)


def build_fixture_arbitration_basis(rows: Iterable[dict[str, Any]], *, secret: bytes, key_id: str) -> ArbitrationBasisV1:
    """Bounded synthetic-page normalization; never makes a provider call."""
    dedup: dict[tuple[str, str], PrivateArbitrationCaseV1] = {}
    for index, row in enumerate(rows):
        if index >= MAX_ROWS:
            break
        if not isinstance(row, dict):
            continue
        identity = _identity(row)
        if identity is None:
            continue
        candidate = PrivateArbitrationCaseV1(
            identity=identity, roles=tuple(sorted(set(role for role in row.get("roles", ()) if isinstance(role, str)))),
            started_at=_as_date(row.get("started_at")), updated_at=_as_date(row.get("updated_at")),
            opponent=private_opponent_token(secret=secret, key_id=key_id, opponent_identifier=row["opponent_identifier"]) if isinstance(row.get("opponent_identifier"), str) else None,
            amount=_as_decimal(row.get("amount")),
        )
        key = (identity.source_kind, identity.value)
        existing = dedup.get(key)
        if existing is None:
            dedup[key] = candidate
        elif existing != candidate:
            # Conflicting duplicates are removed instead of selecting an arbitrary fact.
            dedup.pop(key, None)
    cases = tuple(sorted(dedup.values(), key=lambda item: (item.identity.source_kind, item.identity.value)))[:MAX_CASES]
    return ArbitrationBasisV1(cases=cases, limitations=(LimitationV1(code="arbitration_public_gate_closed", field="arbitration"),))


def public_arbitration_nulls() -> dict[str, None]:
    return {f"A{number}": None for number in range(1, 6)}


def _identity(row: dict[str, Any]) -> InternalCaseIdentityV1 | None:
    for key in ("case_id", "id"):
        value = row.get(key)
        if isinstance(value, (str, int)) and str(value):
            return InternalCaseIdentityV1(source_kind=key, value=str(value))
    return None


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _as_decimal(value: object) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        try:
            return Decimal(value)
        except Exception:
            return None
    return None


__all__ = ["ArbitrationGateClosedError", "MAX_CASES", "MAX_ROWS", "build_fixture_arbitration_basis", "private_opponent_token", "public_arbitration_nulls", "require_arbitration_provider_gate"]
