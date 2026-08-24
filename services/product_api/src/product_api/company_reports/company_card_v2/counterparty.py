from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Any
import unicodedata

from .models import CompanyCardCounterpartyCoreV1, LimitationV1


class CounterpartyShapeError(ValueError):
    pass


@dataclass(frozen=True)
class CounterpartyFieldManifest:
    """Exact observed source paths and closed output bounds."""

    root_inn_path: str = "$.inn"
    root_ogrn_path: str = "$.ogrn"
    company_path: str = "$.company"
    names_path: str = "$.company.company_names"
    address_path: str = "$.company.address"


COUNTERPARTY_FIELD_MANIFEST_V1 = CounterpartyFieldManifest()
_INN_RE = re.compile(r"^(?:[0-9]{10}|[0-9]{12})$")
_OGRN_RE = re.compile(r"^(?:[0-9]{13}|[0-9]{15})$")
_KPP_RE = re.compile(r"^[0-9]{9}$")
_HIDDEN_FIELDS = (
    "status", "legal_form", "charter_capital", "tax_modes", "okved",
    "managers", "owners", "workers", "tax_authority", "contacts",
)


def parse_observed_counterparty(payload: object) -> tuple[CompanyCardCounterpartyCoreV1, tuple[LimitationV1, ...]]:
    """Parse the observed envelope without inferring alternate spellings.

    Only the H1-approved core identity and address leaves leave this boundary.
    A present allowed leaf with a wrong type fails closed; deferred provider
    blocks are neither retained nor interpreted.
    """
    if not isinstance(payload, dict):
        raise CounterpartyShapeError("counterparty payload must be an object")
    source = _object(payload.get("company"), "$.company")
    inn = _identifier(payload.get("inn"), "$.inn", _INN_RE, required=True)
    names = _optional_object(source.get("company_names"), "$.company.company_names")
    address_value = _optional_object(source.get("address"), "$.company.address")
    core = CompanyCardCounterpartyCoreV1(
        inn=inn,
        ogrn=_identifier(payload.get("ogrn"), "$.ogrn", _OGRN_RE),
        kpp=_identifier(source.get("kpp"), "$.company.kpp", _KPP_RE),
        short_name=_bounded_string(names.get("short_name"), "$.company.company_names.short_name", 512) if names else None,
        full_name=_bounded_string(names.get("full_name"), "$.company.company_names.full_name", 1024) if names else None,
        registration_date=_date(source.get("registration_date"), "$.company.registration_date"),
        dissolution_date=_date(source.get("dissolved_date"), "$.company.dissolved_date"),
        address=_bounded_string(address_value.get("line_address"), "$.company.address.line_address", 2048) if address_value else None,
        address_inaccuracy=_optional_bool(address_value.get("is_inaccuracy"), "$.company.address.is_inaccuracy") if address_value else None,
    )
    limitations = tuple(LimitationV1(code="counterparty_deferred_hidden", field=field) for field in _HIDDEN_FIELDS)
    return core, limitations


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CounterpartyShapeError(f"{path} must be an object")
    return value


def _optional_object(value: object, path: str) -> dict[str, Any] | None:
    if value is None:
        return None
    return _object(value, path)


def _identifier(value: object, path: str, pattern: re.Pattern[str], *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise CounterpartyShapeError(f"{path} is invalid")
    return value


def _bounded_string(value: object, path: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CounterpartyShapeError(f"{path} must be a string")
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized or len(normalized) > maximum:
        raise CounterpartyShapeError(f"{path} is invalid")
    if any(ord(character) < 0x20 or 0xD800 <= ord(character) <= 0xDFFF for character in normalized):
        raise CounterpartyShapeError(f"{path} contains prohibited characters")
    return normalized


def _optional_bool(value: object, path: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise CounterpartyShapeError(f"{path} must be a boolean")
    return value


def _date(value: Any, path: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CounterpartyShapeError(f"{path} must be a string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CounterpartyShapeError(f"{path} is invalid") from exc


__all__ = ["COUNTERPARTY_FIELD_MANIFEST_V1", "CounterpartyFieldManifest", "CounterpartyShapeError", "parse_observed_counterparty"]
