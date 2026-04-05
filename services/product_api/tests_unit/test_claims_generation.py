import pytest

from product_api.claims import generation
from product_api.gateway_client import GatewayError
from product_api.settings import get_settings
from shared.schemas import ChatResponse

pytestmark = pytest.mark.asyncio


def _decision() -> dict:
    return {
        "generation_state": "ready",
        "risk_flags": [],
        "allowed_blocks": ["header", "facts", "demands"],
        "blocked_blocks": [],
        "missing_fields": [],
    }


async def test_generate_claim_preview_success(monkeypatch):
    async def fake_send_chat(_settings, payload):
        assert payload.stream is False
        assert payload.metadata.company_id == 15
        return ChatResponse(text="Черновик претензии готов.")

    monkeypatch.setattr(generation, "send_chat", fake_send_chat)

    result = await generation.generate_claim_preview(
        get_settings(),
        claim_id=15,
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={"debtor_name": "ООО Вектор"},
        decision=_decision(),
    )

    assert result["used_fallback"] is False
    assert result["error_code"] is None
    assert result["generated_preview_text"] == "Черновик претензии готов."


async def test_generate_claim_preview_fallback_on_gateway_error(monkeypatch):
    async def fake_send_chat(_settings, payload):
        raise GatewayError("boom")

    monkeypatch.setattr(generation, "send_chat", fake_send_chat)

    result = await generation.generate_claim_preview(
        get_settings(),
        claim_id=16,
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={
            "creditor_name": "ООО Альфа",
            "debtor_name": "ООО Вектор",
            "debt_amount": 380000,
            "payment_due_date": "2026-02-01",
        },
        decision=_decision(),
    )

    assert result["used_fallback"] is True
    assert result["error_code"] == "preview_fallback"
    assert "Черновик досудебной претензии" in result["generated_preview_text"]


async def test_generate_claim_preview_fallback_on_empty_text(monkeypatch):
    async def fake_send_chat(_settings, payload):
        return ChatResponse(text="   ")

    monkeypatch.setattr(generation, "send_chat", fake_send_chat)

    result = await generation.generate_claim_preview(
        get_settings(),
        claim_id=17,
        input_text="ООО Вектор не оплатило поставку",
        case_type=None,
        normalized_data={},
        decision=_decision(),
    )

    assert result["used_fallback"] is True
    assert result["generated_preview_text"]
