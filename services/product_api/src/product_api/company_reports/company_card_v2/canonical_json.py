from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import Decimal
from typing import Any


class CanonicalJsonError(ValueError):
    pass


_CANONICAL_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize the closed ``company_public_h2_cjson_v1`` profile.

    This deliberately does not delegate string escaping to :mod:`json`: its
    compact escapes (``\\n``, ``\\t`` and friends) are valid JSON but are not
    the byte-level profile used for the public projection digest.
    """
    try:
        return _encode(value).encode("utf-8")
    except CanonicalJsonError:
        raise
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


def _decimal(value: Decimal) -> str:
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


def _encode(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, Decimal):
        # Decimals intentionally remain JSON strings: public DTO decimal
        # leaves are canonical strings, never JSON numeric values.
        return _quote(_decimal(value))
    if isinstance(value, int):
        # bool was handled above. Python integers have no exponent/coercion.
        return str(value)
    if isinstance(value, float):
        raise CanonicalJsonError("float values are forbidden")
    if isinstance(value, str):
        return _quote(_normalise_string(value))
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise CanonicalJsonError("object key is not a string")
            clean_key = _normalise_string(key)
            if clean_key in normalized:
                raise CanonicalJsonError("duplicate key after NFC normalization")
            normalized[clean_key] = nested
        return "{" + ",".join(
            _quote(key) + ":" + _encode(normalized[key])
            for key in sorted(normalized)
        ) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    raise CanonicalJsonError(f"value is not canonical-json serializable: {type(value).__name__}")


def _quote(value: str) -> str:
    """Quote one NFC scalar string with the exact profile escape set."""
    pieces: list[str] = ['"']
    for character in value:
        codepoint = ord(character)
        if character == '"':
            pieces.append('\\"')
        elif character == "\\":
            pieces.append("\\\\")
        elif codepoint <= 0x1F:
            pieces.append(f"\\u{codepoint:04x}")
        else:
            pieces.append(character)
    pieces.append('"')
    return "".join(pieces)


def _normalise_string(value: str) -> str:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise CanonicalJsonError("unpaired UTF-16 surrogate is forbidden")
    return unicodedata.normalize("NFC", value)


__all__ = ["CanonicalJsonError", "canonical_digest", "canonical_json_bytes", "script_safe_json_bytes"]
