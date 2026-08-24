"""Narrow, fail-closed admission of a single primary OKVED activity.

This module deliberately knows only the evidence shape approved for iteration
21.  It neither retains nor exposes additional activities or provider payloads.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .canonical_json import canonical_json_bytes

PRIMARY_ACTIVITY_PARSER_VERSION = "company_card_v2_primary_activity_parser_v1"
PRIMARY_ACTIVITY_EVIDENCE_VERSION = "company_card_v2_okved_primary_activity_evidence_v1"
SOURCE_PROFILE_VERSION = "company_card_v2_counterparty_okved_primary_v1"
_CODE = re.compile(r"^[0-9]{2}(?:\.[0-9]{1,2}){0,2}$")


class PrimaryActivityError(ValueError):
    pass


@dataclass(frozen=True)
class PrimaryActivityV1:
    code: str
    label: str
    is_primary: bool = True


def _normalized_text(value: object, *, maximum_scalars: int, maximum_bytes: int) -> str:
    # canonical_json_bytes validates NFC/scalars; input must already be a text
    # leaf and, unlike presentation strings, is not silently trimmed/repaired.
    if not isinstance(value, str):
        raise PrimaryActivityError("primary activity text is invalid")
    if any(0xD800 <= ord(c) <= 0xDFFF or c == "\0" or 0x202A <= ord(c) <= 0x202E or (ord(c) < 32 and c not in "\t\n\r") or 0x7F <= ord(c) <= 0x9F for c in value):
        raise PrimaryActivityError("primary activity text is invalid")
    value = " ".join(unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n").split())
    if not value or len(value) > maximum_scalars:
        raise PrimaryActivityError("primary activity text is invalid")
    try:
        payload = canonical_json_bytes(value)
    except Exception as exc:  # canonical profile owns surrogate/NFC handling
        raise PrimaryActivityError("primary activity text is invalid") from exc
    # quoted canonical JSON is a conservative byte guard; the admitted label
    # itself is checked with UTF-8 bytes below.
    del payload
    if len(value.encode("utf-8")) > maximum_bytes:
        raise PrimaryActivityError("primary activity text is too large")
    return value


def parse_primary_activity(
    payload: object,
    *,
    expected_inn: str,
    requested_okved_block: bool,
    dataset_success: bool,
    target_inn: str | None = None,
) -> PrimaryActivityV1 | None:
    """Return the one admitted row, otherwise ``None``.

    The caller keeps failure semantics in its dataset/result layer.  A failed
    admission is intentionally indistinguishable from unavailable activity at
    this public boundary.
    """
    if not (requested_okved_block and dataset_success and target_inn == expected_inn):
        return None
    try:
        if not isinstance(payload, dict):
            raise PrimaryActivityError("payload is invalid")
        company = payload.get("company")
        if not isinstance(company, dict):
            raise PrimaryActivityError("company is invalid")
        rows = company.get("okveds")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
            raise PrimaryActivityError("okveds are invalid")
        normalized_rows: list[tuple[str, str, bool, str]] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"code", "value", "main", "mode"}:
                raise PrimaryActivityError("okved row is invalid")
            code = row["code"]
            label = row["value"]
            main = row["main"]
            mode = row["mode"]
            if not isinstance(main, bool) or not isinstance(mode, str) or not 1 <= len(mode) <= 16:
                raise PrimaryActivityError("okved row is invalid")
            if not isinstance(code, str) or not _CODE.fullmatch(code) or not 2 <= len(code) <= 8:
                raise PrimaryActivityError("okved code is invalid")
            # All rows have the broad source-row boundary.  The stricter
            # selected-label public boundary applies only after selection.
            label = _normalized_text(label, maximum_scalars=2048, maximum_bytes=2048)
            # The source row boundary includes all strict leaves and has its
            # own byte limit under the approved canonical profile.
            normalized_row = {"code": code, "value": label, "main": main, "mode": mode}
            if len(canonical_json_bytes(normalized_row)) > 2048:
                raise PrimaryActivityError("okved row is too large")
            normalized_rows.append((code, label, main, mode))
        if len(canonical_json_bytes([
            {"code": c, "value": v, "main": m, "mode": mode}
            for c, v, m, mode in normalized_rows
        ])) > 65536:
            raise PrimaryActivityError("okved block is too large")
        primary = [row for row in normalized_rows if row[2]]
        if len(primary) != 1 or primary[0][3] != "new":
            raise PrimaryActivityError("primary activity is unavailable")
        code, label, _main, mode = primary[0]
        if len(label) > 128 or len(label.encode("utf-8")) > 512:
            raise PrimaryActivityError("selected primary label is too large")
        for other_code, other_label, other_main, other_mode in normalized_rows:
            if other_main:
                continue
            if (other_code == code and (other_label != label or other_mode != mode)) or (
                other_label == label and other_code != code
            ):
                raise PrimaryActivityError("primary duplicate conflicts")
        return PrimaryActivityV1(code=code, label=label)
    except (PrimaryActivityError, UnicodeEncodeError, ValueError):
        return None


__all__ = [
    "PRIMARY_ACTIVITY_EVIDENCE_VERSION", "PRIMARY_ACTIVITY_PARSER_VERSION",
    "SOURCE_PROFILE_VERSION", "PrimaryActivityError", "PrimaryActivityV1",
    "parse_primary_activity",
]
