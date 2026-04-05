import pytest

from product_api.claims.extraction import (
    build_empty_normalized_data,
    parse_claim_extraction_response,
)


def test_parse_claim_extraction_response_normalizes_payload():
    result = parse_claim_extraction_response(
        """
        {
          "case_type": "supply",
          "creditor_name": "OOO Alpha",
          "debtor_name": "OOO Vector",
          "contract_signed": true,
          "contract_number": "17",
          "contract_date": "12.01.2026",
          "debt_amount": "380 000 rub",
          "payment_due_date": "01.02.2026",
          "partial_payments_present": false,
          "partial_payments": [],
          "penalty_exists": "yes",
          "penalty_rate_text": "0.1% per day",
          "documents_mentioned": ["contract", "UPD", "invoice"]
        }
        """
    )

    assert result["error_code"] is None
    assert result["case_type"] == "supply"
    normalized = result["normalized_data"]
    assert normalized["creditor_name"] == "OOO Alpha"
    assert normalized["debtor_name"] == "OOO Vector"
    assert normalized["contract_date"] == "2026-01-12"
    assert normalized["debt_amount"] == 380000
    assert normalized["payment_due_date"] == "2026-02-01"
    assert normalized["penalty_exists"] is True
    assert normalized["documents_mentioned"] == ["contract", "upd", "invoice"]
    assert normalized["missing_fields"] == []


def test_parse_claim_extraction_response_handles_fenced_json():
    result = parse_claim_extraction_response(
        """```json
        {
          "case_type": "services",
          "debtor_name": "OOO Vector"
        }
        ```"""
    )

    assert result["error_code"] is None
    assert result["case_type"] == "services"
    assert result["normalized_data"]["debtor_name"] == "OOO Vector"
    assert "creditor_name" in result["normalized_data"]["missing_fields"]


def test_parse_claim_extraction_response_returns_fallback_on_invalid_json():
    result = parse_claim_extraction_response("not a json payload")

    assert result["error_code"] == "invalid_response"
    assert result["case_type"] is None
    assert result["normalized_data"] == build_empty_normalized_data()


def test_parse_claim_extraction_response_ru_normalization_and_case_type_enum():
    result = parse_claim_extraction_response(
        """
        {
          "case_type": "договор подряда",
          "creditor_name": "ООО Альфа",
          "debtor_name": "ООО Вектор",
          "contract_signed": "да",
          "debt_amount": "380 000 ₽",
          "payment_due_date": "01.02.2026",
          "penalty_exists": "нет",
          "documents_mentioned": ["Договор", "УПД", "Накладная", "КС-2", "Счёт"]
        }
        """
    )

    assert result["error_code"] is None
    assert result["case_type"] == "contract_work"
    normalized = result["normalized_data"]
    assert normalized["contract_signed"] is True
    assert normalized["penalty_exists"] is False
    assert normalized["debt_amount"] == 380000
    assert normalized["payment_due_date"] == "2026-02-01"
    assert normalized["documents_mentioned"] == [
        "contract",
        "upd",
        "waybill",
        "ks_2",
        "invoice",
    ]
