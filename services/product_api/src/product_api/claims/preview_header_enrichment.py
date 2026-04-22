from __future__ import annotations

import logging
import re
from typing import Any

from product_api.models import Claim
from product_api.settings import Settings

from .datanewton_client import fetch_datanewton_party_by_inn
from .normalization import normalize_inn
from .person_name_ai_service import transform_person_name_with_ai
from .preview_header_formatter import build_preview_header, infer_kind_from_inn

logger = logging.getLogger(__name__)
PREVIEW_HEADER_FORMAT_VERSION = 2
_ALL_CAPS_CYRILLIC_FIO_ALLOWED_PATTERN = re.compile(r"^[А-ЯЁ -]+$")
_ALL_CAPS_CYRILLIC_FIO_TOKEN_PATTERN = re.compile(r"^[А-ЯЁ]+(?:-[А-ЯЁ]+)*$")
_LOWERCASE_CYRILLIC_PATTERN = re.compile(r"[а-яё]")


def build_preview_header_from_normalized_data(
    normalized_data: dict[str, Any] | None,
) -> dict[str, Any]:
    source = normalized_data if isinstance(normalized_data, dict) else {}
    creditor_inn = normalize_inn(source.get("creditor_inn"), field_name="creditor_inn", strict=False)
    debtor_inn = normalize_inn(source.get("debtor_inn"), field_name="debtor_inn", strict=False)
    from_party = {
        "kind": infer_kind_from_inn(creditor_inn),
        "company_name": _normalize_string(source.get("creditor_name")),
        "position_raw": None,
        "person_name": None,
    }
    to_party = {
        "kind": infer_kind_from_inn(debtor_inn),
        "company_name": _normalize_string(source.get("debtor_name")),
        "position_raw": None,
        "person_name": None,
    }
    return build_preview_header(from_party=from_party, to_party=to_party)


async def rebuild_claim_preview_header(
    settings: Settings,
    claim: Claim,
) -> dict[str, Any]:
    normalized_data = (
        claim.normalized_data_json if isinstance(claim.normalized_data_json, dict) else {}
    )
    header = build_preview_header_from_normalized_data(normalized_data)

    from_party = dict(header.get("from_party") or {})
    to_party = dict(header.get("to_party") or {})
    creditor_inn = normalize_inn(
        normalized_data.get("creditor_inn"),
        field_name="creditor_inn",
        strict=False,
    )
    debtor_inn = normalize_inn(
        normalized_data.get("debtor_inn"),
        field_name="debtor_inn",
        strict=False,
    )

    if settings.datanewton_enabled:
        if creditor_inn:
            creditor_party = await _safe_fetch_party(settings, creditor_inn)
            if creditor_party:
                from_party = _merge_party(from_party, creditor_party)
        if debtor_inn:
            debtor_party = await _safe_fetch_party(settings, debtor_inn)
            if debtor_party:
                to_party = _merge_party(to_party, debtor_party)

    rebuilt_header = build_preview_header(from_party=from_party, to_party=to_party)
    await _apply_fio_ai_for_legal_entities(settings, rebuilt_header)
    await _apply_fio_ai_for_individual_entrepreneurs(settings, rebuilt_header)
    claim.preview_header_json = _as_preview_header_v2(rebuilt_header)
    return claim.preview_header_json


async def _apply_fio_ai_for_legal_entities(
    settings: Settings,
    header: dict[str, Any],
) -> None:
    if not settings.claims_fio_ai_enabled:
        return

    await _apply_fio_ai_to_party_line3(
        settings,
        header=header,
        party_key="from_party",
        target_case="genitive",
    )
    await _apply_fio_ai_to_party_line3(
        settings,
        header=header,
        party_key="to_party",
        target_case="dative",
    )


async def _apply_fio_ai_to_party_line3(
    settings: Settings,
    *,
    header: dict[str, Any],
    party_key: str,
    target_case: str,
) -> None:
    party = header.get(party_key)
    if not isinstance(party, dict):
        return
    if party.get("kind") != "legal_entity":
        return

    raw_person_name = _normalize_string(party.get("person_name"))
    if raw_person_name is None:
        return

    rendered = party.get("rendered")
    if not isinstance(rendered, dict):
        return
    formatter_line3 = rendered.get("line3")
    formatter_line3_text = formatter_line3 if isinstance(formatter_line3, str) else None

    result = await transform_person_name_with_ai(
        settings,
        raw_fio=raw_person_name,
        target_case=target_case,
        entity_kind="legal_entity",
        strip_ip_prefix=False,
    )
    final_line3 = formatter_line3_text
    if result.status == "ok" and result.fio:
        final_line3 = result.fio
    elif result.preprocessed_fio:
        final_line3 = result.preprocessed_fio
    rendered["line3"] = _normalize_all_caps_cyrillic_fio_display_value(final_line3)


async def _apply_fio_ai_for_individual_entrepreneurs(
    settings: Settings,
    header: dict[str, Any],
) -> None:
    if not settings.claims_fio_ai_enabled:
        return

    await _apply_fio_ai_to_ip_party_line2(
        settings,
        header=header,
        party_key="from_party",
        target_case="genitive",
    )
    await _apply_fio_ai_to_ip_party_line2(
        settings,
        header=header,
        party_key="to_party",
        target_case="dative",
    )


async def _apply_fio_ai_to_ip_party_line2(
    settings: Settings,
    *,
    header: dict[str, Any],
    party_key: str,
    target_case: str,
) -> None:
    party = header.get(party_key)
    if not isinstance(party, dict):
        return
    if party.get("kind") != "individual_entrepreneur":
        return

    rendered = party.get("rendered")
    if not isinstance(rendered, dict):
        return
    formatter_line2 = rendered.get("line2")
    formatter_line2_text = formatter_line2 if isinstance(formatter_line2, str) else None

    raw_person_name = _normalize_string(party.get("person_name"))
    raw_company_name = _normalize_string(party.get("company_name"))
    raw_source_fio = raw_person_name or raw_company_name
    if raw_source_fio is None:
        return

    result = await transform_person_name_with_ai(
        settings,
        raw_fio=raw_source_fio,
        target_case=target_case,
        entity_kind="individual_entrepreneur",
        strip_ip_prefix=True,
    )
    final_line2 = formatter_line2_text
    if result.status == "ok" and result.fio:
        final_line2 = result.fio
    elif result.preprocessed_fio:
        final_line2 = result.preprocessed_fio
    rendered["line2"] = _normalize_all_caps_cyrillic_fio_display_value(final_line2)


def _normalize_all_caps_cyrillic_fio_display_value(value: str | None) -> str | None:
    if value is None:
        return None
    if not _looks_like_all_caps_cyrillic_fio(value):
        return value
    normalized_tokens: list[str] = []
    for token in value.split():
        normalized_parts = [
            part[:1].upper() + part[1:].lower()
            for part in token.split("-")
            if part
        ]
        if not normalized_parts:
            return value
        normalized_tokens.append("-".join(normalized_parts))
    return " ".join(normalized_tokens)


def _looks_like_all_caps_cyrillic_fio(value: str) -> bool:
    if _LOWERCASE_CYRILLIC_PATTERN.search(value):
        return False
    if not _ALL_CAPS_CYRILLIC_FIO_ALLOWED_PATTERN.fullmatch(value):
        return False
    tokens = value.split()
    if len(tokens) < 2:
        return False
    return all(_ALL_CAPS_CYRILLIC_FIO_TOKEN_PATTERN.fullmatch(token) for token in tokens)


def _merge_party(base_party: dict[str, Any], incoming_party: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base_party)
    for field_name in ("kind", "company_name", "position_raw", "person_name"):
        incoming_value = _normalize_string(incoming_party.get(field_name))
        if incoming_value is None and field_name != "kind":
            continue
        if field_name == "kind":
            merged[field_name] = incoming_party.get(field_name) or merged.get(field_name)
            continue
        merged[field_name] = incoming_value
    return merged


def _normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    normalized = value.strip()
    return normalized or None


async def _safe_fetch_party(settings: Settings, inn: str) -> dict[str, Any] | None:
    try:
        return await fetch_datanewton_party_by_inn(settings, inn)
    except Exception as exc:
        logger.warning("datanewton_enrichment_failed inn=%s err=%s", inn, str(exc))
        return None


def _as_preview_header_v2(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    from_party = dict(source.get("from_party") or {})
    to_party = dict(source.get("to_party") or {})

    from_rendered = from_party.get("rendered")
    if isinstance(from_rendered, dict):
        from_party["rendered"] = dict(from_rendered)

    to_rendered = to_party.get("rendered")
    if isinstance(to_rendered, dict):
        to_party["rendered"] = dict(to_rendered)

    return {
        "format_version": PREVIEW_HEADER_FORMAT_VERSION,
        "from_party": from_party,
        "to_party": to_party,
    }
