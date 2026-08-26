from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
import json
import re

from pydantic import SecretStr


PRIVACY_KEY_UNAVAILABLE = "privacy_key_unavailable"

_KEY_ID = re.compile(r"[a-z][a-z0-9_]{0,31}")
_MAX_KEYRING_UTF8_BYTES = 8192
_MAX_KEYRING_ENTRIES = 16
_MIN_SECRET_BYTES = 32
_MAX_SECRET_BYTES = 64


class ArbitrationKeyringUnavailable(ValueError):
    """One safe failure for every unavailable or malformed keyring input."""

    code = PRIVACY_KEY_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class ResolvedArbitrationMaskKey:
    key_id: str
    secret_bytes: bytes = field(repr=False)


def normalize_arbitration_mask_key_id(value: str | None) -> str | None:
    """Keep an exact valid nonsecret ID; malformed/whitespace input becomes null."""

    if not isinstance(value, str) or _KEY_ID.fullmatch(value) is None:
        return None
    return value


def resolve_arbitration_mask_key(
    *,
    key_id: str | None,
    keyring_json: SecretStr | None,
) -> ResolvedArbitrationMaskKey:
    """Resolve one claimed key without exposing or retaining the full keyring."""

    normalized_key_id = normalize_arbitration_mask_key_id(key_id)
    secret_bytes = resolve_arbitration_mask_secret_bytes(
        key_id=normalized_key_id,
        keyring_json=keyring_json,
    )
    if normalized_key_id is None or secret_bytes is None:
        raise ArbitrationKeyringUnavailable()
    return ResolvedArbitrationMaskKey(
        key_id=normalized_key_id,
        secret_bytes=secret_bytes,
    )


def resolve_arbitration_mask_secret_bytes(
    *,
    key_id: str | None,
    keyring_json: SecretStr | None,
) -> bytes | None:
    """Return exact claimed secret bytes, or null for every unavailable input."""

    resolved = _resolve_or_none(key_id=key_id, keyring_json=keyring_json)
    return None if resolved is None else resolved.secret_bytes


def _resolve_or_none(
    *,
    key_id: str | None,
    keyring_json: SecretStr | None,
) -> ResolvedArbitrationMaskKey | None:
    try:
        if key_id is None or _KEY_ID.fullmatch(key_id) is None or keyring_json is None:
            raise ValueError
        raw = keyring_json.get_secret_value()
        if len(raw.encode("utf-8")) > _MAX_KEYRING_UTF8_BYTES:
            raise ValueError
        parsed = json.loads(raw, object_pairs_hook=_unique_object)
        if (
            not isinstance(parsed, dict)
            or not 1 <= len(parsed) <= _MAX_KEYRING_ENTRIES
        ):
            raise ValueError

        selected: bytes | None = None
        for candidate_id, encoded_secret in parsed.items():
            if (
                not isinstance(candidate_id, str)
                or _KEY_ID.fullmatch(candidate_id) is None
                or not isinstance(encoded_secret, str)
            ):
                raise ValueError
            decoded = _decode_canonical_secret(encoded_secret)
            if candidate_id == key_id:
                selected = decoded
        if selected is None:
            raise ValueError
        return ResolvedArbitrationMaskKey(key_id=key_id, secret_bytes=selected)
    except (
        ValueError,
        TypeError,
        UnicodeError,
        json.JSONDecodeError,
        binascii.Error,
        RecursionError,
    ):
        # The helper returns rather than re-raising so the public safe exception
        # has no secret-bearing decoder/base64 traceback frame or exception
        # context attached to it.
        return None


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _decode_canonical_secret(value: str) -> bytes:
    if not value or "=" in value:
        raise ValueError
    encoded = value.encode("ascii")
    padded = encoded + b"=" * (-len(encoded) % 4)
    decoded = base64.b64decode(padded, altchars=b"-_", validate=True)
    if not _MIN_SECRET_BYTES <= len(decoded) <= _MAX_SECRET_BYTES:
        raise ValueError
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if canonical != value:
        raise ValueError
    return decoded


__all__ = [
    "ArbitrationKeyringUnavailable",
    "PRIVACY_KEY_UNAVAILABLE",
    "ResolvedArbitrationMaskKey",
    "normalize_arbitration_mask_key_id",
    "resolve_arbitration_mask_key",
    "resolve_arbitration_mask_secret_bytes",
]
