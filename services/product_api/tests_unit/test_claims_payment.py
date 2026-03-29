import pytest

from product_api.claims.repository import apply_claim_payment_stub
from product_api.models import Claim

pytestmark = pytest.mark.asyncio


async def test_apply_claim_payment_stub_success_ready(mock_session):
    claim = Claim(
        id=401,
        status="draft",
        generation_state="ready",
        price_rub=990,
        input_text="text",
        edit_token_hash="hash",
    )

    updated_claim, changed_fields = await apply_claim_payment_stub(mock_session, claim)

    assert updated_claim.status == "paid"
    assert updated_claim.paid_at is not None
    assert "status" in changed_fields
    assert "paid_at" in changed_fields
    assert mock_session.flush.await_count == 1


async def test_apply_claim_payment_stub_success_manual_review_required(mock_session):
    claim = Claim(
        id=402,
        status="preview_ready",
        generation_state="manual_review_required",
        price_rub=990,
        input_text="text",
        edit_token_hash="hash",
    )

    updated_claim, changed_fields = await apply_claim_payment_stub(mock_session, claim)

    assert updated_claim.status == "paid"
    assert updated_claim.paid_at is not None
    assert "status" in changed_fields
    assert "paid_at" in changed_fields
    assert mock_session.flush.await_count == 1


async def test_apply_claim_payment_stub_rejects_insufficient_data(mock_session):
    claim = Claim(
        id=403,
        status="draft",
        generation_state="insufficient_data",
        price_rub=990,
        input_text="text",
        edit_token_hash="hash",
    )

    with pytest.raises(ValueError, match="insufficient_data"):
        await apply_claim_payment_stub(mock_session, claim)

    assert mock_session.flush.await_count == 0


async def test_apply_claim_payment_stub_rejects_repeated_payment(mock_session):
    claim = Claim(
        id=404,
        status="paid",
        generation_state="ready",
        price_rub=990,
        input_text="text",
        edit_token_hash="hash",
    )

    with pytest.raises(ValueError, match="already_paid_or_later_state"):
        await apply_claim_payment_stub(mock_session, claim)

    assert mock_session.flush.await_count == 0
