from datetime import datetime, timezone

import pytest

from product_api.claims.admin_service import (
    apply_admin_final_text,
    apply_admin_status_transition,
    build_admin_claim_detail_snapshot,
    normalize_claim_generation_state_filter,
    normalize_claim_status_filter,
)
from product_api.models import Claim

pytestmark = pytest.mark.asyncio


def _base_claim(*, status: str = "paid", generation_state: str = "ready") -> Claim:
    return Claim(
        id=701,
        status=status,
        generation_state=generation_state,
        price_rub=990,
        input_text="Claim text",
        edit_token_hash="hidden",
        created_at=datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 16, 12, 5, tzinfo=timezone.utc),
    )


async def test_apply_admin_status_transition_paid_to_in_review_sets_reviewed_at():
    claim = _base_claim(status="paid")

    from_status, changed_fields = apply_admin_status_transition(
        claim,
        target_status="in_review",
    )

    assert from_status == "paid"
    assert claim.status == "in_review"
    assert claim.reviewed_at is not None
    assert "status" in changed_fields
    assert "reviewed_at" in changed_fields


async def test_apply_admin_status_transition_in_review_to_sent_sets_sent_at():
    claim = _base_claim(status="in_review")

    from_status, changed_fields = apply_admin_status_transition(
        claim,
        target_status="sent",
    )

    assert from_status == "in_review"
    assert claim.status == "sent"
    assert claim.sent_at is not None
    assert "status" in changed_fields
    assert "sent_at" in changed_fields


async def test_apply_admin_status_transition_invalid_raises_value_error():
    claim = _base_claim(status="draft")

    with pytest.raises(ValueError, match="invalid_transition"):
        apply_admin_status_transition(
            claim,
            target_status="in_review",
        )


async def test_apply_admin_final_text_trims_value():
    claim = _base_claim(status="in_review")

    changed_fields = apply_admin_final_text(
        claim,
        final_text="  Final claim text  ",
    )

    assert claim.final_text == "Final claim text"
    assert changed_fields == ["final_text"]


async def test_apply_admin_final_text_blank_raises_value_error():
    claim = _base_claim(status="in_review")

    with pytest.raises(ValueError, match="final_text is required"):
        apply_admin_final_text(claim, final_text="   ")


async def test_admin_filters_validation():
    assert normalize_claim_status_filter("PAID") == "paid"
    assert normalize_claim_generation_state_filter("READY") == "ready"
    with pytest.raises(ValueError, match="invalid status filter"):
        normalize_claim_status_filter("unknown")
    with pytest.raises(ValueError, match="invalid generation_state filter"):
        normalize_claim_generation_state_filter("unknown")


async def test_build_admin_claim_detail_snapshot_is_safe():
    claim = _base_claim(status="paid", generation_state="manual_review_required")
    claim.final_text = "Final"
    claim.risk_flags_json = ["risk_1"]
    claim.allowed_blocks_json = ["header"]
    claim.blocked_blocks_json = ["attachments"]
    claim.normalized_data_json = {"debtor_name": "OOO Vector", "missing_fields": []}

    snapshot = build_admin_claim_detail_snapshot(claim)

    assert snapshot["id"] == 701
    assert snapshot["manual_review_required"] is True
    assert snapshot["final_text"] == "Final"
    assert snapshot["risk_flags"] == ["risk_1"]
    assert "edit_token_hash" not in snapshot
