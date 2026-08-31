from decimal import Decimal

import pytest

from product_api.company_reports.company_card_v2.canonical_json import CanonicalJsonError, canonical_json_bytes, script_safe_json_bytes


def test_canonical_json_normalizes_nfc_and_decimal_without_float_truth():
    assert canonical_json_bytes({"z": Decimal("-0.00"), "a": "e\u0301"}) == '{"a":"é","z":"0"}'.encode()
    assert script_safe_json_bytes({"text": "<>&\u2028\u2029"}) == b'{"text":"\\u003C\\u003E\\u0026\\u2028\\u2029"}'


@pytest.mark.parametrize("value", [{"number": 1.0}, {"\ud800": "x"}, {"e\u0301": 1, "é": 2}])
def test_canonical_json_rejects_float_surrogate_and_nfc_collision(value):
    with pytest.raises(CanonicalJsonError):
        canonical_json_bytes(value)
