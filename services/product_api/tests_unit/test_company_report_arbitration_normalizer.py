from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from company_report_test_helpers import arbitration_result, load_fixture
from product_api.company_reports import (
    ArbitrationResultType,
    ArbitrationRole,
    ArbitrationStatus,
    normalize_arbitration,
)


def test_arbitration_normalizes_case_fields_amount_and_documents():
    facts = normalize_arbitration(arbitration_result(), target_identifier="0000000000")
    case = facts.cases[0]

    assert case.internal_id == "synthetic-internal-1"
    assert case.case_number == "SYNTH-CASE-001"
    assert case.date_start == date(2022, 1, 10)
    assert case.last_document_date == date(2022, 2, 12)
    assert case.claim_amount == Decimal("100.25")
    assert case.document_count == 1
    assert case.document_types == ["SYNTH_DECISION"]
    assert case.latest_document_date == date(2022, 2, 12)


def test_arbitration_target_roles_match_inn_ogrn_and_keep_multiple_roles():
    by_inn = normalize_arbitration(arbitration_result(), target_identifier="0000000000")
    by_ogrn = normalize_arbitration(
        arbitration_result(), target_identifier="0000000000000"
    )

    assert by_inn.cases[0].company_roles == [ArbitrationRole.PLAINTIFF]
    assert by_ogrn.cases[1].company_roles == [ArbitrationRole.RESPONDENT]
    assert by_inn.cases[2].company_roles == [
        ArbitrationRole.PLAINTIFF,
        ArbitrationRole.RESPONDENT,
    ]


def test_arbitration_maps_statuses_results_and_preserves_raw_values():
    facts = normalize_arbitration(arbitration_result(), target_identifier="0000000000")

    assert [case.normalized_status for case in facts.cases] == [
        ArbitrationStatus.OPEN,
        ArbitrationStatus.COMPLETED,
        ArbitrationStatus.COMPLETED,
        ArbitrationStatus.UNKNOWN,
        ArbitrationStatus.OPEN,
    ]
    assert [case.normalized_result_type for case in facts.cases] == [
        ArbitrationResultType.SATISFIED_FULL,
        ArbitrationResultType.REFUSED,
        ArbitrationResultType.RETURNED,
        ArbitrationResultType.UNDEFINED,
        ArbitrationResultType.OTHER,
    ]
    assert facts.cases[3].raw_status == 9
    assert facts.cases[4].raw_result_type == "SYNTH_OTHER"


def test_arbitration_pagination_and_summaries():
    payload = deepcopy(load_fixture("arbitration_success.json"))
    payload["data"].append("synthetic-malformed-entry")
    facts = normalize_arbitration(
        arbitration_result(payload), target_identifier="0000000000"
    )

    assert facts.total_cases == 7
    assert facts.returned_cases == 6
    assert len(facts.cases) + facts.malformed_entry_count == facts.returned_cases
    assert facts.malformed_entry_count == 1
    assert facts.is_complete is False
    assert facts.role_summary.model_dump() == {
        "plaintiff_count": 2,
        "respondent_count": 2,
        "applicant_count": 1,
        "creditor_count": 0,
        "debtor_count": 0,
        "other_count": 0,
        "unknown_count": 1,
    }
    assert facts.status_summary.model_dump() == {
        "open_count": 2,
        "completed_count": 2,
        "unknown_count": 1,
    }
    assert facts.result_summary.model_dump() == {
        "satisfied_full_count": 1,
        "refused_count": 1,
        "returned_count": 1,
        "undefined_count": 1,
        "other_count": 1,
    }

    payload = load_fixture("arbitration_success.json")
    payload["total_cases"] = 5
    complete = normalize_arbitration(
        arbitration_result(payload), target_identifier="0000000000"
    )
    assert complete.is_complete is True


def test_arbitration_sums_only_unambiguous_roles():
    facts = normalize_arbitration(arbitration_result(), target_identifier="0000000000")

    assert facts.claim_amount_as_plaintiff == Decimal("100.25")
    assert facts.claim_amount_as_respondent == Decimal("200")
    assert facts.claim_amounts_by_currency["RUBLES"].plaintiff == Decimal("100.25")
    assert facts.claim_amounts_by_currency["RUBLES"].respondent == Decimal("200")


@pytest.mark.parametrize(
    "invalid_parties",
    [
        {"inn": "0000000000"},
        [{"inn": "0000000000"}, "not-an-object"],
    ],
)
def test_arbitration_marks_whole_case_malformed_for_invalid_party_collection(
    invalid_parties,
):
    payload = deepcopy(load_fixture("arbitration_success.json"))
    payload["data"][0]["plaintiffs"] = invalid_parties

    facts = normalize_arbitration(
        arbitration_result(payload), target_identifier="0000000000"
    )

    assert facts.cases[0].party_collections_valid is False
    assert any(
        item.code in {"arbitration_parties_invalid", "arbitration_party_invalid"}
        for item in facts.warnings
    )


def test_arbitration_mixed_currency_is_not_combined():
    payload = load_fixture("arbitration_success.json")
    payload["data"][3]["plaintiffs"][0].update(
        {"inn": "0000000000", "ogrn": "0000000000000"}
    )

    facts = normalize_arbitration(
        arbitration_result(payload), target_identifier="0000000000"
    )

    assert facts.claim_amount_as_plaintiff is None
    assert set(facts.claim_amounts_by_currency) == {"RUBLES", "USD"}
    assert "arbitration_mixed_currencies" in {item.code for item in facts.warnings}


def test_arbitration_repr_hides_party_names_case_numbers_identifiers_and_amounts():
    facts = normalize_arbitration(arbitration_result(), target_identifier="0000000000")
    rendered = repr(facts)

    for sensitive_value in (
        "ООО Синтетика Альфа",
        "SYNTH-CASE-001",
        "0000000000",
        "100.25",
    ):
        assert sensitive_value not in rendered
