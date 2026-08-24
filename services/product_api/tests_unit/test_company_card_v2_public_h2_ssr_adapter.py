import pytest

from product_api.company_reports.company_card_v2 import public_h2_ssr_adapter as adapter
from product_api.company_reports.company_card_v2.service import PublicH2NotEligible


@pytest.mark.asyncio
async def test_ssr_adapter_delegates_to_exact_public_resolver(monkeypatch) -> None:
    session = object()
    expected = object()
    received = {}

    async def fake_resolve(actual_session, *, inn):
        received["session"] = actual_session
        received["inn"] = inn
        return expected

    monkeypatch.setattr(adapter, "resolve_public_h2", fake_resolve)

    assert await adapter.resolve_public_h2_ssr(session, inn="7701234567") is expected
    assert received == {"session": session, "inn": "7701234567"}


@pytest.mark.asyncio
async def test_ssr_adapter_preserves_fail_closed_public_error(monkeypatch) -> None:
    async def fake_resolve(_session, *, inn):
        raise PublicH2NotEligible(f"unbound {inn}")

    monkeypatch.setattr(adapter, "resolve_public_h2", fake_resolve)

    with pytest.raises(PublicH2NotEligible):
        await adapter.resolve_public_h2_ssr(object(), inn="7701234567")
