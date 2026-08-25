from decimal import Decimal
import json
from pathlib import Path

import pytest

from product_api.company_reports.company_card_v2.canonical_json import CanonicalJsonError, canonical_digest, canonical_json_bytes, script_safe_json_bytes


def test_canonical_json_normalizes_nfc_and_decimal_without_float_truth():
    assert canonical_json_bytes({"z": Decimal("-0.00"), "a": "e\u0301"}) == '{"a":"é","z":"0"}'.encode()
    assert script_safe_json_bytes({"text": "<>&\u2028\u2029"}) == b'{"text":"\\u003C\\u003E\\u0026\\u2028\\u2029"}'


def test_canonical_json_uses_lowercase_unicode_escapes_for_every_control() -> None:
    controls = "".join(chr(value) for value in range(32))
    encoded = canonical_json_bytes({"controls": controls})
    assert b"\\b" not in encoded and b"\\t" not in encoded and b"\\n" not in encoded
    assert b"\\u0000" in encoded and b"\\u000a" in encoded and b"\\u001f" in encoded


def test_script_safe_cap_accepts_equality_and_rejects_one_byte_over() -> None:
    # ASCII keeps source and encoded byte counts equal for this boundary.
    accepted = {"payload": "x" * (786432 - len(b'{"payload":""}'))}
    assert len(script_safe_json_bytes(accepted)) == 786432
    with pytest.raises(CanonicalJsonError, match="script_safe_projection_too_large"):
        script_safe_json_bytes({"payload": accepted["payload"] + "x"})


def test_canonical_json_golden_vectors() -> None:
    fixture = Path(__file__).parent / "fixtures" / "company_card_v2" / "cjson_vectors.json"
    vectors = json.loads(fixture.read_text(encoding="utf-8"))["vectors"]
    for vector in vectors:
        assert canonical_json_bytes(vector["value"]).decode("utf-8") == vector["canonical"]
        if "script_safe" in vector:
            assert script_safe_json_bytes(vector["value"]).decode("utf-8") == vector["script_safe"]


def test_shared_h2_cjson_vectors_are_token_exact() -> None:
    fixture = Path(__file__).parents[3] / "shared" / "fixtures" / "company_public_h2_cjson_v1.json"
    for vector in json.loads(fixture.read_text(encoding="utf-8"))["vectors"]:
        assert canonical_digest(json.loads(vector["raw"])) == vector["sha256"]


@pytest.mark.parametrize("value", [{"number": 1.0}, {"\ud800": "x"}, {"e\u0301": 1, "é": 2}])
def test_canonical_json_rejects_float_surrogate_and_nfc_collision(value):
    with pytest.raises(CanonicalJsonError):
        canonical_json_bytes(value)
