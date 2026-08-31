from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from decimal import Decimal
from typing import Any


class CanonicalJsonError(ValueError):
    pass


_CANONICAL_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")


def canonical_json_bytes(value: Any) -> bytes:
    """Stable JSON without float truth or non-finite values."""
    value = _normalise(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=_decimal).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalJsonError("value is not canonical-json serializable") from exc


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def script_safe_json_bytes(value: Any) -> bytes:
    """Return non-hashed H2 state-script bytes under the closed escape rule."""
    encoded = canonical_json_bytes(value).decode("utf-8")
    encoded = (encoded.replace("<", "\\u003C").replace(">", "\\u003E")
        .replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    result = encoded.encode("utf-8")
    if len(result) > 786432:
        raise CanonicalJsonError("script_safe_projection_too_large")
    return result


def _decimal(value: object) -> str:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalJsonError("non-finite Decimal is forbidden")
        rendered = format(value, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        if rendered in {"-0", ""}:
            rendered = "0"
        if not _CANONICAL_DECIMAL.fullmatch(rendered):
            raise CanonicalJsonError("Decimal is not canonical")
        return rendered
    raise TypeError(type(value).__name__)


def _normalise(value: object) -> object:
    if isinstance(value, float):
        raise CanonicalJsonError("float values are forbidden")
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise CanonicalJsonError("object key is not a string")
            clean_key = _normalise_string(key)
            if clean_key in normalized:
                raise CanonicalJsonError("duplicate key after NFC normalization")
            normalized[clean_key] = _normalise(nested)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalise(nested) for nested in value]
    if isinstance(value, str):
        return _normalise_string(value)
    return value


def _normalise_string(value: str) -> str:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise CanonicalJsonError("unpaired UTF-16 surrogate is forbidden")
    return unicodedata.normalize("NFC", value)


__all__ = ["CanonicalJsonError", "canonical_digest", "canonical_json_bytes", "script_safe_json_bytes"]
