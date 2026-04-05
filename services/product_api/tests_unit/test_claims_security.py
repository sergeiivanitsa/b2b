import pytest
from fastapi import HTTPException

from product_api.claims.security import hash_claim_edit_token, require_claim_access
from product_api.models import Claim

pytestmark = pytest.mark.asyncio


class DummyResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


async def test_require_claim_access_missing_token_401(mock_session):
    with pytest.raises(HTTPException) as exc:
        await require_claim_access(claim_id=123, x_claim_edit_token=None, session=mock_session)

    assert exc.value.status_code == 401
    assert exc.value.detail == "claim edit token required"


async def test_require_claim_access_invalid_token_404(mock_session):
    claim = Claim(
        id=123,
        status="draft",
        generation_state="insufficient_data",
        price_rub=990,
        input_text="test",
        edit_token_hash=hash_claim_edit_token("good-token"),
    )
    mock_session.execute.return_value = DummyResult(claim)

    with pytest.raises(HTTPException) as exc:
        await require_claim_access(
            claim_id=123,
            x_claim_edit_token="bad-token",
            session=mock_session,
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "claim not found"
