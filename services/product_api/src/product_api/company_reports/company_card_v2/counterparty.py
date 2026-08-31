from __future__ import annotations

from datetime import date
from typing import Any

from .models import CompanyCardCounterpartyCoreV1, LimitationV1


class CounterpartyShapeError(ValueError):
    pass


_PRIVATE_MARKERS = {"contact", "phone", "email", "manager", "owner", "innfl", "passport", "person"}


def parse_observed_counterparty(payload: object) -> tuple[CompanyCardCounterpartyCoreV1, tuple[LimitationV1, ...]]:
    """Parse only an allowlisted core and deliberately discard all deferred leaves.

    Observed external payloads vary by provider revision. The parser supports
    the existing normalized core spellings only; it does not infer semantics
    from an unknown leaf name.
    """
    if not isinstance(payload, dict):
        raise CounterpartyShapeError("counterparty payload must be an object")
    source = payload.get("company") if isinstance(payload.get("company"), dict) else payload
    inn = _string(source.get("inn"))
    if inn is None:
        raise CounterpartyShapeError("counterparty INN is missing")
    registration = _date(source.get("registration_date"))
    dissolution = _date(source.get("dissolved_date") or source.get("dissolution_date"))
    address_value = source.get("address")
    address = _string(address_value.get("line_address")) if isinstance(address_value, dict) else _string(address_value)
    address_inaccuracy = address_value.get("is_inaccuracy") if isinstance(address_value, dict) and isinstance(address_value.get("is_inaccuracy"), bool) else None
    core = CompanyCardCounterpartyCoreV1(
        inn=inn, ogrn=_string(source.get("ogrn")), kpp=_string(source.get("kpp")),
        short_name=_string(source.get("short_name")), full_name=_string(source.get("full_name")),
        registration_date=registration, dissolution_date=dissolution, address=address,
        address_inaccuracy=address_inaccuracy,
    )
    limitations = tuple(LimitationV1(code="counterparty_deferred_hidden", field=field) for field in (
        "status", "legal_form", "charter_capital", "tax_modes", "okved", "managers", "owners", "workers", "tax_authority", "contacts",
    ))
    return core, limitations


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _date(value: Any) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CounterpartyShapeError("counterparty date must be a string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CounterpartyShapeError("counterparty date is invalid") from exc


__all__ = ["CounterpartyShapeError", "parse_observed_counterparty"]
