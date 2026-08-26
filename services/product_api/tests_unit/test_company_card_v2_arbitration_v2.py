from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from product_api.company_reports.company_card_v2.arbitration_v2 import (
    arbitration_basis_metadata_reserve_mapping_v2,
    arbitration_chart_facts_hash,
    build_arbitration_chart_facts,
    normalize_arbitration_result_v2,
    reserved_arbitration_basis_size_v2,
)
from product_api.company_reports.company_card_v2.arbitration import private_opponent_token
from product_api.company_reports.company_card_v2.canonical_json import canonical_json_bytes
from product_api.company_reports.company_card_v2.models import (
    ArbitrationCollectionCountersV2,
    ArbitrationPageManifestV2,
    PrivateOpponentTokenV2,
    SanitizedArbitrationCaseV2,
)
from product_api.providers.datanewton import DataNewtonResult, calculate_response_hash


TARGET_INN = "7700000000"
REPORT_ID = UUID("00000000-0000-4000-8000-000000000001")
RECEIVED_AT = datetime(2026, 8, 26, 12, 34, 56, 123456, tzinfo=timezone.utc)
SECRET = b"iteration-24-test-mask-secret-32b"


def _fixture() -> dict[str, object]:
    path = Path(__file__).parent / "fixtures" / "company_card_v2" / "arbitration_v2_single_page.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _result(payload: dict[str, object], *, lexical=True, manifest=None, **changes: object) -> DataNewtonResult:
    values: dict[str, object] = {
        "dataset": "arbitration_cases",
        "endpoint": "/v1/arbitration-cases",
        "requested_identifier": TARGET_INN,
        "requested_identifiers": [],
        "request_parameters": {"inn": TARGET_INN, "company_role": "ALL", "offset": 0, "limit": 1000},
        "request_body": None,
        "status_code": 200,
        "attempts": 1,
        "duration_ms": 1,
        "request_id": f"company-report:{REPORT_ID}",
        "received_at": RECEIVED_AT,
        "raw_payload": payload,
        "lexical_transport_valid": lexical,
        "lexical_number_lexemes": manifest or {
            "/total_cases": str(payload.get("total_cases", 0)),
            "/offset": str(payload.get("offset", 0)),
            "/limit": str(payload.get("limit", 1000)),
            "/data/0/year": "2026",
            "/data/0/sum": "-12.3400",
        },
        "response_hash": calculate_response_hash(payload),
    }
    values.update(changes)
    return DataNewtonResult(**values)


def _normalize(result: DataNewtonResult):
    return normalize_arbitration_result_v2(
        result,
        target_inn=TARGET_INN,
        report_id=REPORT_ID,
        mask_key_id="active_2026",
        mask_secret=SECRET,
    )


def test_v2_normalizes_only_closed_private_shape_and_exact_decimal() -> None:
    payload = _fixture()
    basis = _normalize(_result(payload))

    assert basis.completion_reasons == ("complete",)
    assert basis.provider_received_at == RECEIVED_AT
    assert basis.counters.model_dump() == {
        "pages_requested": 1,
        "pages_accepted": 1,
        "rows_observed": 1,
        "rows_processed": 1,
        "rows_shape_valid": 1,
        "malformed_count": 0,
        "oversized_case_count": 0,
        "storage_cap_rejected_count": 0,
        "duplicate_identical_count": 0,
        "duplicate_conflict_row_count": 0,
        "duplicate_conflict_key_count": 0,
        "unique_case_count": 1,
        "opponent_token_count": 1,
        "opponent_group_count": 1,
        "opponent_group_probe_count": 1,
    }
    case = basis.sanitized_cases[0]
    assert (case.role, case.outcome, case.duration_days) == ("plaintiff", "won", 3)
    assert (case.amount_state, case.amount, case.currency_state) == ("available", Decimal("-12.34"), "rub")
    assert case.first_number == "А40-123/2026"
    assert case.opponent_tokens[0].value == private_opponent_token(
        secret=SECRET,
        key_id="active_2026",
        opponent_identifier="7800000000",
        stable_identifier_kind="inn",
        report_id=REPORT_ID,
    ).value
    dumped = canonical_json_bytes(basis.model_dump(mode="json"))
    for forbidden in (
        b"RAW TARGET NAME",
        b"RAW OPPONENT NAME",
        b"7800000000",
        b"1027800000000",
        b"raw.example.invalid",
        b"name_src",
        b"inn_src",
    ):
        assert forbidden not in dumped
    assert basis.model_validate(basis.model_dump(mode="json")) == basis

    facts = build_arbitration_chart_facts(basis)
    assert facts.collection_state == "complete"
    assert facts.role_counts[0].count == 1
    assert arbitration_chart_facts_hash(facts) == arbitration_chart_facts_hash(build_arbitration_chart_facts(basis))


@pytest.mark.parametrize(
    ("party_result", "target_role"),
    (([], "plaintiff"), ({}, "respondent")),
)
def test_non_string_party_result_is_unknown_without_normalizer_failure(
    party_result: object,
    target_role: str,
) -> None:
    payload = _fixture()
    row = payload["data"][0]
    row["party_result"] = party_result
    if target_role == "respondent":
        row["plaintiffs"], row["respondents"] = (
            [{"inn": "7800000000", "inn_src": "INN"}],
            [{"inn": TARGET_INN}],
        )

    case = _normalize(_result(payload)).sanitized_cases[0]

    assert case.role == target_role
    assert case.outcome == "unknown"


@pytest.mark.parametrize(
    ("change", "reason", "keeps_received_at"),
    [
        ({"request_parameters": {"inn": TARGET_INN, "company_role": "ALL", "offset": False, "limit": 1000}}, "provider_binding_invalid", False),
        ({"request_id": "company-report:not-the-report"}, "provider_binding_invalid", False),
        ({"response_hash": "0" * 64}, "provider_binding_invalid", False),
        ({"lexical_transport_valid": False}, "lexical_transport_invalid", True),
    ],
)
def test_binding_and_lexical_fail_before_rows(change, reason, keeps_received_at) -> None:
    payload = _fixture()
    basis = _normalize(_result(payload, **change))

    assert basis.completion_reasons == (reason,)
    assert basis.counters.pages_requested == 1
    assert basis.counters.pages_accepted == 0
    assert basis.sanitized_cases == ()
    assert basis.source_total is None
    assert (basis.provider_received_at == RECEIVED_AT) is keeps_received_at


def test_envelope_failure_retains_only_bound_receipt() -> None:
    payload = _fixture()
    payload["offset"] = False
    basis = _normalize(_result(payload))
    assert basis.completion_reasons == ("envelope_invalid",)
    assert basis.provider_received_at == RECEIVED_AT
    assert basis.counters.rows_observed == 0


def test_conflict_reclassifies_first_and_identical_rows() -> None:
    original = _fixture()["data"][0]
    same = deepcopy(original)
    conflict = deepcopy(original)
    conflict["currency"] = "OTHER"
    payload = {"total_cases": 3, "offset": 0, "limit": 1000, "data": [original, same, conflict]}
    manifest = {
        "/data/0/sum": "-12.3400",
        "/data/1/sum": "-12.3400",
        "/data/2/sum": "-12.3400",
    }
    basis = _normalize(_result(payload, manifest=manifest))

    assert basis.sanitized_cases == ()
    assert basis.counters.rows_shape_valid == 3
    assert basis.counters.duplicate_conflict_row_count == 3
    assert basis.counters.duplicate_conflict_key_count == 1
    assert basis.counters.duplicate_identical_count == 0
    assert basis.counters.unique_case_count == 0
    assert basis.completion_reasons == ("duplicate_conflict",)


def test_first_number_collision_scans_a_later_malformed_row() -> None:
    valid = deepcopy(_fixture()["data"][0])
    valid["first_number"] = "А40-999/2026"
    malformed = {"case_id": "А40-999/2026"}
    payload = {"total_cases": 2, "offset": 0, "limit": 1000, "data": [valid, malformed]}
    basis = _normalize(_result(payload, manifest={"/data/0/sum": "-12.3400"}))

    assert basis.sanitized_cases[0].first_number is None
    assert "arbitration_first_number_identity_collision" in basis.sanitized_cases[0].limitations
    assert basis.counters.malformed_count == 1
    assert basis.completion_reasons == ("malformed_rows",)


def test_missing_and_invalid_amount_currency_states_are_not_zero_or_collapsed() -> None:
    missing = deepcopy(_fixture()["data"][0])
    missing.pop("sum")
    missing.pop("currency")
    invalid = deepcopy(_fixture()["data"][0])
    invalid["case_id"] = "private-case-v2-b"
    invalid["sum"] = "0"
    invalid["currency"] = []
    payload = {"total_cases": 2, "offset": 0, "limit": 1000, "data": [missing, invalid]}
    basis = _normalize(_result(payload, manifest={}))

    first, second = basis.sanitized_cases
    assert (first.amount_state, first.amount, first.currency_state) == ("missing", None, "missing")
    assert (second.amount_state, second.amount, second.currency_state) == ("invalid", None, "invalid")
    assert "arbitration_amount_missing" in first.limitations
    assert "arbitration_amount_invalid" in second.limitations
    assert "arbitration_currency_invalid" in second.limitations


@pytest.mark.parametrize(
    ("decoded", "lexeme"),
    ((1, "2"), (1, "1.0"), (1.0, "1")),
)
def test_amount_lexeme_must_bind_the_exact_decoded_number_leaf(
    decoded: int | float,
    lexeme: str,
) -> None:
    payload = _fixture()
    payload["data"][0]["sum"] = decoded
    basis = _normalize(_result(
        payload,
        manifest={"/data/0/sum": lexeme},
    ))

    case = basis.sanitized_cases[0]
    assert (case.amount_state, case.amount) == ("invalid", None)
    assert "arbitration_amount_invalid" in case.limitations
    assert "arbitration_amount_invalid" in {
        item.code for item in basis.limitations
    }


def test_float_rounding_collision_keeps_the_exact_bound_source_lexeme() -> None:
    payload = _fixture()
    source_lexeme = "0.10000000000000001"
    payload["data"][0]["sum"] = json.loads(source_lexeme)

    basis = _normalize(_result(
        payload,
        manifest={"/data/0/sum": source_lexeme},
    ))

    case = basis.sanitized_cases[0]
    assert (case.amount_state, case.amount) == (
        "available",
        Decimal(source_lexeme),
    )


@pytest.mark.parametrize("field", ArbitrationCollectionCountersV2.model_fields)
def test_v2_counters_reject_bool_and_string_coercion(field: str) -> None:
    value = False if field.startswith("pages_") else "0"
    with pytest.raises(ValidationError):
        ArbitrationCollectionCountersV2(**{field: value})


def test_page_fixed_integers_are_strict() -> None:
    with pytest.raises(ValidationError):
        ArbitrationPageManifestV2(offset=False, limit=1000, returned_count=0, accepted_count=0, response_hash="a" * 64)


def test_decimal_model_wire_round_trip_is_canonical_and_bool_is_not_amount() -> None:
    case = SanitizedArbitrationCaseV2(
        case_id="private",
        role="unattributed",
        outcome="unknown",
        amount_state="available",
        amount=Decimal("-1.200"),
        currency_state="rub",
        limitations=("arbitration_unknown_year", "arbitration_first_number_unavailable"),
    )
    assert case.amount == Decimal("-1.2")
    assert case.model_dump(mode="json")["amount"] == "-1.2"
    assert SanitizedArbitrationCaseV2.model_validate(case.model_dump(mode="json")) == case
    with pytest.raises(ValidationError):
        SanitizedArbitrationCaseV2.model_validate({**case.model_dump(mode="json"), "amount": True})


@pytest.mark.parametrize("role", ("other", "unattributed"))
@pytest.mark.parametrize("invalid_fact", ("outcome", "opponent"))
def test_nonparty_case_role_rejects_party_derived_facts(
    role: str,
    invalid_fact: str,
) -> None:
    values: dict[str, object] = {
        "case_id": f"private-{role}-{invalid_fact}",
        "role": role,
        "outcome": "unknown",
        "amount_state": "missing",
        "currency_state": "missing",
        "limitations": (
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    }
    if invalid_fact == "outcome":
        values["outcome"] = "won"
    else:
        values["opponent_tokens"] = (
            PrivateOpponentTokenV2(
                key_id="active_2026",
                value="a" * 64,
            ),
        )

    with pytest.raises(ValidationError, match="non-party arbitration role"):
        SanitizedArbitrationCaseV2(**values)


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        (
            {
                "date_start": date(2025, 1, 1),
                "date_update": date(2025, 1, 2),
                "duration_days": 1,
                "limitations": (
                    "arbitration_date_invalid",
                    "arbitration_amount_missing",
                    "arbitration_currency_missing",
                ),
            },
            "invalid-date limitation",
        ),
        (
            {
                "year": None,
                "date_start": None,
                "limitations": (
                    "arbitration_unknown_year",
                    "arbitration_year_conflict",
                    "arbitration_amount_missing",
                    "arbitration_currency_missing",
                ),
            },
            "year-conflict limitation",
        ),
    ),
)
def test_case_rejects_inferably_impossible_date_and_year_limitations(
    changes: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "case_id": "private-impossible-limitation",
        "first_number": "A40-1/2025",
        "year": 2025,
        "role": "plaintiff",
        "outcome": "unknown",
        "amount_state": "missing",
        "currency_state": "missing",
        "limitations": (
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    }
    values.update(changes)

    with pytest.raises(ValidationError, match=message):
        SanitizedArbitrationCaseV2(**values)


def test_metadata_reserve_has_exact_keys_and_bounds_actual_basis() -> None:
    basis = _normalize(_result(_fixture()))
    mapping = arbitration_basis_metadata_reserve_mapping_v2(basis.sanitized_cases)
    assert reserved_arbitration_basis_size_v2(()) == 2992
    assert set(mapping) == set(type(basis).model_fields)
    assert len(mapping["limitations"]) == 25
    assert mapping["counters"]["opponent_group_probe_count"] == 20_001
    assert reserved_arbitration_basis_size_v2(basis.sanitized_cases) == len(canonical_json_bytes(mapping))
    assert reserved_arbitration_basis_size_v2(basis.sanitized_cases) >= len(canonical_json_bytes(basis.model_dump(mode="json")))


def _opponent_cap_payload(*, last_party_count: int) -> dict[str, object]:
    rows = []
    next_inn = 8_000_000_000
    for row_index in range(1000):
        party_count = last_party_count if row_index == 999 else 20
        opponents = []
        for _ in range(party_count):
            opponents.append({"inn": str(next_inn), "inn_src": "INN"})
            next_inn += 1
        rows.append({
            "case_id": f"private-case-{row_index:04d}",
            "year": 2026,
            "plaintiffs": [{"inn": TARGET_INN}],
            "respondents": opponents,
            "third_parties": [],
            "interested_persons": [],
            "creditors": [],
            "creditors_current_payments": [],
            "debtors": [],
            "applicants": [],
            "others": [],
        })
    return {"total_cases": 1000, "offset": 0, "limit": 1000, "data": rows}


def test_20000_distinct_opponents_are_retained_at_equality() -> None:
    basis = _normalize(_result(_opponent_cap_payload(last_party_count=20), manifest={}))

    assert basis.completion_reasons == ("complete",)
    assert basis.counters.opponent_group_probe_count == 20_000
    assert basis.counters.opponent_group_count == 20_000
    assert basis.counters.opponent_token_count == 20_000


def test_20001_distinct_opponents_are_atomically_scrubbed_without_case_loss() -> None:
    basis = _normalize(_result(_opponent_cap_payload(last_party_count=21), manifest={}))

    assert basis.completion_reasons == ("opponent_group_cap_exhausted",)
    assert basis.counters.unique_case_count == 1000
    assert basis.counters.opponent_group_probe_count == 20_001
    assert basis.counters.opponent_group_count == 0
    assert basis.counters.opponent_token_count == 0
    assert all(case.opponent_tokens == () for case in basis.sanitized_cases)
    facts = build_arbitration_chart_facts(basis)
    assert (facts.opponent_group_count, facts.cases_without_safe_opponent, facts.multi_opponent_case_count) == (None, None, None)
