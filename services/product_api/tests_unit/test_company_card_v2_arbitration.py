import pytest

from product_api.company_reports.company_card_v2.arbitration import ArbitrationGateClosedError, public_arbitration_nulls, require_arbitration_provider_gate


def test_shipped_arbitration_gate_is_closed() -> None:
    with pytest.raises(ArbitrationGateClosedError):
        require_arbitration_provider_gate()
    assert public_arbitration_nulls() == {"A1": None, "A2": None, "A3": None, "A4": None, "A5": None}
