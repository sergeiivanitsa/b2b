from __future__ import annotations

import re
from typing import Any, Literal

PartyKind = Literal["legal_entity", "individual_entrepreneur", "unknown"]
PartySide = Literal["from", "to"]

_GENERAL_DIRECTOR_PATTERN = re.compile(r"\bгенеральн\w*\s+директор\w*\b", re.IGNORECASE)
_DIRECTOR_PATTERN = re.compile(r"\bдиректор\w*\b", re.IGNORECASE)
_RENDERED_POSITION_ALIASES: dict[str, str] = {
    "генеральный директор": "general_director",
    "директор": "director",
    "президент": "president",
    "general director": "general_director",
    "director": "director",
    "president": "president",
}
_IP_PREFIXES = (
    "ип ",
    "ип. ",
    "индивидуальный предприниматель ",
    "индивидуального предпринимателя ",
    "индивидуальному предпринимателю ",
)


def build_preview_header(
    *,
    from_party: dict[str, Any] | None,
    to_party: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    return {
        "from_party": build_preview_header_party(from_party, side="from"),
        "to_party": build_preview_header_party(to_party, side="to"),
    }


def build_preview_header_party(
    payload: dict[str, Any] | None,
    *,
    side: PartySide,
) -> dict[str, Any]:
    source = payload or {}
    kind = _normalize_kind(source.get("kind"))
    company_name = _normalize_string(source.get("company_name"))
    position_raw = _normalize_string(source.get("position_raw"))
    person_name = _normalize_string(source.get("person_name"))
    line1 = _build_line1(
        kind=kind,
        company_name=company_name,
        position_raw=position_raw,
        side=side,
    )
    rendered = _build_rendered_lines(
        kind=kind,
        company_name=company_name,
        position_raw=position_raw,
        person_name=person_name,
        side=side,
    )
    return {
        "kind": kind,
        "company_name": company_name,
        "position_raw": position_raw,
        "person_name": person_name,
        "line1": line1,
        "line2": person_name,
        "rendered": rendered,
    }


def infer_kind_from_inn(inn: str | None) -> PartyKind:
    if not inn:
        return "unknown"
    if len(inn) == 12:
        return "individual_entrepreneur"
    if len(inn) == 10:
        return "legal_entity"
    return "unknown"


def _build_line1(
    *,
    kind: PartyKind,
    company_name: str | None,
    position_raw: str | None,
    side: PartySide,
) -> str:
    if kind == "individual_entrepreneur":
        return (
            "Индивидуального предпринимателя"
            if side == "from"
            else "Индивидуальному предпринимателю"
        )

    position_form = _render_position_form(position_raw=position_raw, side=side)
    if company_name:
        return f"{position_form} {company_name}"
    return position_form


def _render_position_form(*, position_raw: str | None, side: PartySide) -> str:
    normalized_position = _normalize_position(position_raw)
    if normalized_position == "general_director":
        return (
            "Генерального директора"
            if side == "from"
            else "Генеральному директору"
        )
    if normalized_position == "director":
        return "Директора" if side == "from" else "Директору"
    return "Руководителя" if side == "from" else "Руководителю"


def _normalize_position(position_raw: str | None) -> str:
    if not position_raw:
        return "unknown"
    normalized = " ".join(position_raw.split())
    # More specific position must have higher priority than generic "director".
    if _GENERAL_DIRECTOR_PATTERN.search(normalized):
        return "general_director"
    if _DIRECTOR_PATTERN.search(normalized):
        return "director"
    return "unknown"


def _normalize_kind(value: Any) -> PartyKind:
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower()
    if normalized in {"individual_entrepreneur", "ip", "individual"}:
        return "individual_entrepreneur"
    if normalized in {"legal_entity", "ul", "company", "organization"}:
        return "legal_entity"
    return "unknown"


def _normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    normalized = value.strip()
    return normalized or None


def _build_rendered_lines(
    *,
    kind: PartyKind,
    company_name: str | None,
    position_raw: str | None,
    person_name: str | None,
    side: PartySide,
) -> dict[str, str | None]:
    rendered_line1 = _build_rendered_line1(kind=kind, position_raw=position_raw, side=side)
    rendered_line2 = company_name
    rendered_line3 = person_name

    if (
        kind == "individual_entrepreneur"
        and rendered_line2 is not None
        and rendered_line3 is not None
        and _normalize_ip_identity(rendered_line2) == _normalize_ip_identity(rendered_line3)
    ):
        rendered_line3 = None

    return {
        "line1": rendered_line1,
        "line2": rendered_line2,
        "line3": rendered_line3,
    }


def _build_rendered_line1(*, kind: PartyKind, position_raw: str | None, side: PartySide) -> str:
    if kind == "individual_entrepreneur":
        return (
            "От индивидуального предпринимателя"
            if side == "from"
            else "Индивидуальному предпринимателю"
        )

    normalized_position = _normalize_rendered_position(position_raw)
    if side == "from":
        if normalized_position == "general_director":
            return "От генерального директора"
        if normalized_position == "director":
            return "От директора"
        if normalized_position == "president":
            return "От президента"
        return "От руководителя"

    if normalized_position == "general_director":
        return "Генеральному директору"
    if normalized_position == "director":
        return "Директору"
    if normalized_position == "president":
        return "Президенту"
    return "Руководителю"


def _normalize_rendered_position(position_raw: str | None) -> str:
    if not position_raw:
        return "unknown"
    normalized = _normalize_for_exact_equality(position_raw)
    return _RENDERED_POSITION_ALIASES.get(normalized, "unknown")


def _normalize_for_exact_equality(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _normalize_ip_identity(value: str) -> str:
    normalized = _normalize_for_exact_equality(value)
    for prefix in _IP_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return " ".join(normalized.split())
