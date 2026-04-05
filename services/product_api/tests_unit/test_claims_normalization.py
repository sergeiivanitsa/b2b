from datetime import date

import pytest

from product_api.claims.normalization import (
    build_step2_contract,
    merge_normalized_data_patch,
    normalize_case_type,
)


def _base_normalized_data() -> dict:
    return {
        "creditor_name": "OOO Alpha",
        "debtor_name": "OOO Vector",
        "contract_signed": True,
        "contract_number": "17",
        "contract_date": "2026-01-12",
        "debt_amount": 380000,
        "payment_due_date": "2026-02-01",
        "partial_payments_present": False,
        "partial_payments": [],
        "penalty_exists": True,
        "penalty_rate_text": "0.1% per day",
        "documents_mentioned": ["contract"],
        "missing_fields": [],
    }


def test_merge_normalized_data_patch_and_build_step2_contract():
    merged, changed_fields = merge_normalized_data_patch(
        _base_normalized_data(),
        patch_values={
            "partial_payments_present": "да",
            "partial_payments": [
                {"amount": "50 000 ₽", "date": "20.01.2026"},
                {"amount": 30000, "date": "2026-01-28"},
            ],
            "penalty_exists": "нет",
            "penalty_rate_text": "0.1% per day",
            "documents_mentioned": ["Договор", "Счёт"],
        },
        patch_fields={
            "partial_payments_present",
            "partial_payments",
            "penalty_exists",
            "penalty_rate_text",
            "documents_mentioned",
        },
    )

    assert set(changed_fields) == {
        "partial_payments_present",
        "partial_payments",
        "penalty_exists",
        "penalty_rate_text",
        "documents_mentioned",
    }
    assert merged["partial_payments_present"] is True
    assert merged["partial_payments"] == [
        {"amount": 50000, "date": "2026-01-20"},
        {"amount": 30000, "date": "2026-01-28"},
    ]
    assert merged["penalty_exists"] is False
    assert merged["penalty_rate_text"] is None
    assert merged["documents_mentioned"] == ["contract", "invoice"]
    assert merged["missing_fields"] == []

    step2 = build_step2_contract(merged, today=date(2026, 3, 1))
    assert step2["conditional_visibility"]["show_partial_payments"] is True
    assert step2["conditional_visibility"]["show_penalty_rate"] is False
    assert step2["derived"]["total_paid_amount"] == 80000
    assert step2["derived"]["remaining_debt_amount"] == 300000
    assert step2["derived"]["overdue_days"] == 28
    assert step2["derived"]["is_overdue"] is True


def test_merge_normalized_data_patch_branching_rules_for_partial_payments():
    merged, changed_fields = merge_normalized_data_patch(
        _base_normalized_data(),
        patch_values={
            "partial_payments_present": True,
            "partial_payments": [],
        },
        patch_fields={"partial_payments_present", "partial_payments"},
    )

    assert merged["partial_payments_present"] is True
    assert merged["partial_payments"] == []
    assert "partial_payments_present" in changed_fields
    assert "partial_payments" in merged["missing_fields"]

    merged_off, changed_fields_off = merge_normalized_data_patch(
        merged,
        patch_values={
            "partial_payments_present": False,
            "partial_payments": [{"amount": 1000, "date": "2026-01-01"}],
        },
        patch_fields={"partial_payments_present", "partial_payments"},
    )
    assert merged_off["partial_payments_present"] is False
    assert merged_off["partial_payments"] == []
    assert "partial_payments" in changed_fields_off


def test_normalize_case_type_uses_canonical_enum():
    assert normalize_case_type("supply") == "supply"
    assert normalize_case_type("подряд") == "contract_work"
    assert normalize_case_type("оказание услуг") == "services"
    assert normalize_case_type(None) is None
    with pytest.raises(ValueError):
        normalize_case_type("other")
