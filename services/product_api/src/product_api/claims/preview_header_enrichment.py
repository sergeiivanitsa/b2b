from __future__ import annotations

import logging
from typing import Any

from product_api.models import Claim
from product_api.settings import Settings

from .datanewton_client import fetch_datanewton_party_by_inn
from .normalization import normalize_inn
from .preview_header_formatter import build_preview_header, infer_kind_from_inn

logger = logging.getLogger(__name__)


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

    claim.preview_header_json = build_preview_header(from_party=from_party, to_party=to_party)
    return claim.preview_header_json


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
