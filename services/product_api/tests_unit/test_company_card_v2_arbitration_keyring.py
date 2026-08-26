import base64
import json

import pytest
from pydantic import SecretStr

from product_api.company_reports.company_card_v2.arbitration_keyring import (
    ArbitrationKeyringUnavailable,
    PRIVACY_KEY_UNAVAILABLE,
    normalize_arbitration_mask_key_id,
    resolve_arbitration_mask_key,
    resolve_arbitration_mask_secret_bytes,
)


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _secret(payload: object) -> SecretStr:
    return SecretStr(json.dumps(payload, separators=(",", ":")))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("a", "a"),
        ("active_key_01", "active_key_01"),
        ("a" * 32, "a" * 32),
        ("", None),
        (" active_key", None),
        ("active_key ", None),
        ("Active_key", None),
        ("1active", None),
        ("a-b", None),
        ("a" * 33, None),
        (1, None),
    ],
)
def test_key_id_normalization_is_exact_and_never_trims(
    raw: object,
    expected: str | None,
) -> None:
    assert normalize_arbitration_mask_key_id(raw) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize("size", [32, 64])
def test_keyring_resolves_canonical_boundary_secret_without_repr_leak(size: int) -> None:
    secret = bytes(range(size))
    resolved = resolve_arbitration_mask_key(
        key_id="active_key",
        keyring_json=_secret({"old_key": _encoded(b"o" * 32), "active_key": _encoded(secret)}),
    )

    assert resolved.key_id == "active_key"
    assert resolved.secret_bytes == secret
    assert _encoded(secret) not in repr(resolved)
    assert repr(resolved) == "ResolvedArbitrationMaskKey(key_id='active_key')"


def test_bytes_helper_returns_only_exact_selected_secret_or_none() -> None:
    selected = b"s" * 32
    keyring = _secret(
        {
            "old_key": _encoded(b"o" * 32),
            "active_key": _encoded(selected),
        }
    )

    assert resolve_arbitration_mask_secret_bytes(
        key_id="active_key",
        keyring_json=keyring,
    ) == selected
    assert resolve_arbitration_mask_secret_bytes(
        key_id="missing",
        keyring_json=keyring,
    ) is None
    assert resolve_arbitration_mask_secret_bytes(
        key_id=" active_key ",
        keyring_json=keyring,
    ) is None
    assert resolve_arbitration_mask_secret_bytes(
        key_id="active_key",
        keyring_json=SecretStr('{"active_key":"private-marker"}'),
    ) is None


def test_keyring_accepts_exact_entry_and_utf8_size_boundaries() -> None:
    entries = {f"key_{index}": _encoded(bytes([index]) * 32) for index in range(16)}
    raw = json.dumps(entries, separators=(",", ":"))
    padded = raw + " " * (8192 - len(raw.encode("utf-8")))

    resolved = resolve_arbitration_mask_key(
        key_id="key_15",
        keyring_json=SecretStr(padded),
    )

    assert resolved.secret_bytes == bytes([15]) * 32


@pytest.mark.parametrize(
    ("key_id", "raw"),
    [
        (None, None),
        ("", '{}'),
        (" Active", '{}'),
        ("ACTIVE", '{}'),
        ("a" * 33, '{}'),
        ("missing", '{"active":"' + _encoded(b"a" * 32) + '"}'),
        ("active", "[]"),
        ("active", "{}"),
        ("active", '{"active":1}'),
        ("active", '{"Active":"' + _encoded(b"a" * 32) + '"}'),
        ("active", '{"active":"' + _encoded(b"a" * 31) + '"}'),
        ("active", '{"active":"' + _encoded(b"a" * 65) + '"}'),
        ("active", '{"active":"' + _encoded(b"a" * 32) + '="}'),
        ("active", '{"active":"not+base64/value"}'),
        (
            "active",
            '{"active":"' + _encoded(b"a" * 32) + '","active":"' + _encoded(b"b" * 32) + '"}',
        ),
    ],
)
def test_keyring_maps_every_malformed_or_unavailable_input_to_one_safe_error(
    key_id: str | None,
    raw: str | None,
) -> None:
    marker = _encoded(b"a" * 32)
    with pytest.raises(ArbitrationKeyringUnavailable) as caught:
        resolve_arbitration_mask_key(
            key_id=key_id,
            keyring_json=SecretStr(raw) if raw is not None else None,
        )

    assert str(caught.value) == PRIVACY_KEY_UNAVAILABLE
    assert repr(caught.value) == "ArbitrationKeyringUnavailable('privacy_key_unavailable')"
    assert marker not in str(caught.value)
    assert marker not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_keyring_rejects_entry_and_utf8_size_overflow() -> None:
    too_many = {f"key_{index}": _encoded(bytes([index]) * 32) for index in range(17)}
    too_large = json.dumps({"active": _encoded(b"a" * 32)}, separators=(",", ":"))
    too_large += " " * (8193 - len(too_large.encode("utf-8")))

    for key_id, raw in (("key_0", json.dumps(too_many)), ("active", too_large)):
        with pytest.raises(ArbitrationKeyringUnavailable, match="^privacy_key_unavailable$"):
            resolve_arbitration_mask_key(
                key_id=key_id,
                keyring_json=SecretStr(raw),
            )


def test_deeply_nested_json_maps_to_safe_unavailable_result() -> None:
    raw = "[" * 1500 + "0" + "]" * 1500

    assert resolve_arbitration_mask_secret_bytes(
        key_id="active",
        keyring_json=SecretStr(raw),
    ) is None
    with pytest.raises(
        ArbitrationKeyringUnavailable,
        match="^privacy_key_unavailable$",
    ) as caught:
        resolve_arbitration_mask_key(
            key_id="active",
            keyring_json=SecretStr(raw),
        )

    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
