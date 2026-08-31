import pytest

from product_api.company_reports.company_card_v2.privacy import PrivacyBoundaryError, assert_public_boundary_safe


@pytest.mark.parametrize("payload", [{"case_id": "x"}, {"opponent": {"value": "a" * 64}}, {"contact": "x"}])
def test_public_boundary_rejects_private_markers(payload: object) -> None:
    with pytest.raises(PrivacyBoundaryError):
        assert_public_boundary_safe(payload)


def test_public_projection_digest_is_not_a_private_token() -> None:
    assert_public_boundary_safe({"projection_digest": "a" * 64})
