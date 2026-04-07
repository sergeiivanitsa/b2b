from product_api.claims.rules import evaluate_claim_rules


def _complete_normalized_data() -> dict:
    return {
        "creditor_name": "OOO Alpha",
        "creditor_inn": "7701234567",
        "debtor_name": "OOO Vector",
        "debtor_inn": "780123456789",
        "contract_signed": True,
        "contract_number": "17",
        "contract_date": "2026-01-12",
        "debt_amount": 380000,
        "payment_due_date": "2026-02-01",
        "partial_payments_present": False,
        "partial_payments": [],
        "penalty_exists": False,
        "penalty_rate_text": None,
        "documents_mentioned": ["contract", "invoice"],
        "missing_fields": [],
    }


def test_rules_insufficient_data_when_required_fields_missing():
    decision = evaluate_claim_rules(
        case_type="supply",
        normalized_data={"debtor_name": "OOO Vector"},
    )
    assert decision["generation_state"] == "insufficient_data"
    assert "creditor_name" in decision["missing_fields"]
    assert decision["allowed_blocks"]


def test_rules_manual_review_required_when_high_risk_present():
    payload = _complete_normalized_data()
    payload["documents_mentioned"] = []

    decision = evaluate_claim_rules(
        case_type="supply",
        normalized_data=payload,
    )
    assert decision["generation_state"] == "manual_review_required"
    assert "no_supporting_documents" in decision["risk_flags"]
    assert "attachments" in decision["blocked_blocks"]


def test_rules_ready_when_data_complete_and_risk_low():
    decision = evaluate_claim_rules(
        case_type="supply",
        normalized_data=_complete_normalized_data(),
    )
    assert decision["generation_state"] == "ready"
    assert decision["risk_flags"] == []
    assert decision["blocked_blocks"] == []
    assert "legal_basis" in decision["allowed_blocks"]
