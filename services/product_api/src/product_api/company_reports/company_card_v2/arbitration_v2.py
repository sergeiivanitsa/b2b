from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import hmac
import json
import math
import re
from typing import Any
from uuid import UUID

from product_api.providers.datanewton import ARBITRATION_CASES_ENDPOINT, calculate_response_hash

from .canonical_json import canonical_digest, canonical_json_bytes
from .decimal_transport import DecimalTransportError, parse_source_decimal
from .models import (
    ARBITRATION_COMPLETION_PRECEDENCE_V2,
    ARBITRATION_LIMITATION_PRECEDENCE_V2,
    ArbitrationBasisLimitationV2,
    ArbitrationBasisV2,
    ArbitrationChartFactsV1,
    ArbitrationCollectionCountersV2,
    ArbitrationNamedCountV1,
    ArbitrationPageManifestV2,
    ArbitrationYearRoleFactV1,
    PrivateOpponentTokenV2,
    SanitizedArbitrationCaseV2,
)

MAX_CASE_CJSON_BYTES = 262_144
MAX_BASIS_CJSON_BYTES = 8_388_608
MAX_OPPONENT_GROUPS = 20_000
OPPONENT_GROUP_OVERFLOW_SENTINEL = 20_001

ARBITRATION_REGISTRY_VERSION_V2 = "datanewton_arbitration_registry_v2"
ARBITRATION_CONTRACT_BINDING_V2 = "datanewton_arbitration_openapi_v1_2026_08_26"
ARBITRATION_OPENAPI_SHA256_V2 = "2c3d34ab00a35e58e07f7c3dea32b605b9e61d112a92a1654fd54e415ef851d2"

_ROLE_COLLECTIONS = (
    "plaintiffs",
    "respondents",
    "third_parties",
    "interested_persons",
    "creditors",
    "creditors_current_payments",
    "debtors",
    "applicants",
    "others",
)
_ROLE_KEYS = ("plaintiff", "respondent", "other", "unattributed")
_OUTCOME_KEYS = ("won", "lost", "returned", "unknown")
_MASK_KEY_ID = re.compile(r"[a-z][a-z0-9_]{0,31}$")
_FIRST_NUMBER = re.compile(r"(?:(?:А|A)[0-9]{1,3}|СИП)-[0-9]{1,12}/[0-9]{4}$")
_MISSING = object()


class ArbitrationV2NormalizationError(ValueError):
    """An internal contract error, never provider text or raw payload."""


@dataclass(frozen=True)
class _CandidateState:
    case: SanitizedArbitrationCaseV2
    cjson: bytes
    row_count: int = 1


def empty_arbitration_basis_v2(
    reason: str,
    *,
    pages_requested: int = 0,
    mask_key_id: str | None = None,
    provider_received_at: datetime | None = None,
) -> ArbitrationBasisV2:
    """Build one exact pre-result/failure basis without ambient state."""
    if reason not in ARBITRATION_COMPLETION_PRECEDENCE_V2 or reason == "complete":
        raise ArbitrationV2NormalizationError("unsupported empty arbitration reason")
    if type(pages_requested) is not int or pages_requested not in (0, 1):
        raise ArbitrationV2NormalizationError("pages_requested must be zero or one")
    if mask_key_id is not None and (type(mask_key_id) is not str or _MASK_KEY_ID.fullmatch(mask_key_id) is None):
        raise ArbitrationV2NormalizationError("mask key id is invalid")
    limitations = _basis_limitations((reason, "arbitration_calendar_unverified"))
    return ArbitrationBasisV2(
        provider_received_at=provider_received_at,
        counters=ArbitrationCollectionCountersV2(pages_requested=pages_requested),
        completion_reasons=(reason,),
        mask_algorithm_version="opponent_hmac_sha256_v1" if mask_key_id is not None else None,
        mask_key_id=mask_key_id,
        limitations=limitations,
    )


def normalize_arbitration_result_v2(
    result: object,
    *,
    target_inn: str,
    report_id: UUID,
    mask_key_id: str,
    mask_secret: bytes,
) -> ArbitrationBasisV2:
    """Bind and normalize exactly one DataNewton arbitration result.

    The function is pure with respect to I/O: the supplied result is the only
    source.  Result metadata is bound before envelope leaves are inspected,
    and the whole lexical gate precedes every payload leaf read.
    """
    _require_target_and_key(
        target_inn=target_inn,
        report_id=report_id,
        mask_key_id=mask_key_id,
        mask_secret=mask_secret,
    )
    request_id = f"company-report:{str(report_id).lower()}"
    if not arbitration_result_is_exactly_bound_v2(
        result,
        target_inn=target_inn,
        request_id=request_id,
    ):
        return empty_arbitration_basis_v2(
            "provider_binding_invalid",
            pages_requested=1,
            mask_key_id=mask_key_id,
        )

    # This is captured immediately after the outer binding.  Later lexical or
    # envelope rejection must retain the safe receipt metadata.
    provider_received_at = getattr(result, "received_at")
    if getattr(result, "lexical_transport_valid", None) is not True:
        return empty_arbitration_basis_v2(
            "lexical_transport_invalid",
            pages_requested=1,
            mask_key_id=mask_key_id,
            provider_received_at=provider_received_at,
        )

    payload = getattr(result, "raw_payload")
    envelope = _validated_envelope(payload)
    if envelope is None:
        return empty_arbitration_basis_v2(
            "envelope_invalid",
            pages_requested=1,
            mask_key_id=mask_key_id,
            provider_received_at=provider_received_at,
        )
    source_total, rows = envelope
    response_hash = getattr(result, "response_hash")
    manifest = getattr(result, "lexical_number_lexemes", {})
    if not isinstance(manifest, Mapping):
        # The parser attestation covers only its own exact ephemeral manifest.
        manifest = {}

    collision_case_ids = {
        value
        for row in rows
        if type(row) is dict
        for value in (row.get("case_id"),)
        if _valid_first_number(value)
    }

    admitted: dict[str, _CandidateState] = {}
    conflicted: set[str] = set()
    conflict_rows = 0
    shape_valid = 0
    malformed = 0
    rows_processed = 0
    oversized = 0
    storage_rejected = 0
    limitation_codes: set[str] = {"arbitration_calendar_unverified"}
    case_cjson_sum = 0
    reserve_empty_size = reserved_arbitration_basis_size_v2(())

    for index, row in enumerate(rows):
        rows_processed += 1
        candidate = _sanitize_row(
            row,
            row_index=index,
            target_inn=target_inn,
            report_id=report_id,
            mask_key_id=mask_key_id,
            mask_secret=mask_secret,
            number_manifest=manifest,
            collision_case_ids=collision_case_ids,
        )
        if candidate is None:
            malformed += 1
            continue
        shape_valid += 1
        candidate_cjson = canonical_json_bytes(candidate.model_dump(mode="json"))
        if len(candidate_cjson) > MAX_CASE_CJSON_BYTES:
            oversized = 1
            limitation_codes.add("oversized_case")
            break

        case_id = candidate.case_id
        if case_id in conflicted:
            conflict_rows += 1
            continue
        prior = admitted.get(case_id)
        if prior is not None:
            if prior.cjson == candidate_cjson:
                admitted[case_id] = _CandidateState(prior.case, prior.cjson, prior.row_count + 1)
            else:
                conflict_rows += prior.row_count + 1
                case_cjson_sum -= len(prior.cjson)
                admitted.pop(case_id)
                conflicted.add(case_id)
                limitation_codes.add("duplicate_conflict")
            continue

        proposed_count = len(admitted) + 1
        proposed_cases_bytes = case_cjson_sum + len(candidate_cjson) + max(0, proposed_count - 1)
        if reserve_empty_size + proposed_cases_bytes > MAX_BASIS_CJSON_BYTES:
            storage_rejected = 1
            limitation_codes.add("storage_cap_exhausted")
            break
        admitted[case_id] = _CandidateState(candidate, candidate_cjson)
        case_cjson_sum += len(candidate_cjson)

    duplicate_identical = sum(state.row_count - 1 for state in admitted.values())
    cases = tuple(state.case for _, state in sorted(admitted.items()))
    cases, opponent_token_count, opponent_group_count, opponent_probe_count, opponent_overflow = _apply_opponent_group_cap(cases)
    if opponent_overflow:
        limitation_codes.add("opponent_group_cap_exhausted")
    for case in cases:
        limitation_codes.update(case.limitations)

    reasons: set[str] = set()
    if malformed:
        reasons.add("malformed_rows")
        limitation_codes.add("malformed_rows")
    if conflicted:
        reasons.add("duplicate_conflict")
    if oversized:
        reasons.add("oversized_case")
    if storage_rejected:
        reasons.add("storage_cap_exhausted")
    if opponent_overflow:
        reasons.add("opponent_group_cap_exhausted")
    if source_total > 1000:
        reasons.add("source_total_exceeds_cap")
        limitation_codes.add("source_total_exceeds_cap")
    completion_reasons = _ordered_completion_reasons(reasons)
    unknown_year_count = sum(case.year is None for case in cases)
    if unknown_year_count:
        limitation_codes.add("arbitration_unknown_year")

    counters = ArbitrationCollectionCountersV2(
        pages_requested=1,
        pages_accepted=1,
        rows_observed=len(rows),
        rows_processed=rows_processed,
        rows_shape_valid=shape_valid,
        malformed_count=malformed,
        oversized_case_count=oversized,
        storage_cap_rejected_count=storage_rejected,
        duplicate_identical_count=duplicate_identical,
        duplicate_conflict_row_count=conflict_rows,
        duplicate_conflict_key_count=len(conflicted),
        unique_case_count=len(cases),
        opponent_token_count=opponent_token_count,
        opponent_group_count=opponent_group_count,
        opponent_group_probe_count=opponent_probe_count,
    )
    basis = ArbitrationBasisV2(
        source_total=source_total,
        page_manifest=(
            ArbitrationPageManifestV2(
                returned_count=len(rows),
                accepted_count=len(cases),
                response_hash=response_hash,
            ),
        ),
        provider_received_at=provider_received_at,
        counters=counters,
        completion_reasons=completion_reasons,
        collection_complete=completion_reasons == ("complete",),
        unknown_year_count=unknown_year_count,
        mask_algorithm_version="opponent_hmac_sha256_v1",
        mask_key_id=mask_key_id,
        sanitized_cases=cases,
        limitations=_basis_limitations(limitation_codes),
    )
    # The reserve is an admission bound; the real model also checks this.  Keep
    # a direct pure assertion here so a future model change cannot bypass it.
    if len(canonical_json_bytes(basis.model_dump(mode="json"))) > MAX_BASIS_CJSON_BYTES:
        raise ArbitrationV2NormalizationError("final arbitration basis exceeds storage cap")
    return basis


def arbitration_result_is_exactly_bound_v2(
    result: object,
    *,
    target_inn: str,
    request_id: str,
) -> bool:
    """Check the complete result tuple without interpreting payload leaves."""
    raw_payload = getattr(result, "raw_payload", None)
    parameters = getattr(result, "request_parameters", None)
    received_at = getattr(result, "received_at", None)
    if type(raw_payload) is not dict or type(parameters) is not dict:
        return False
    if set(parameters) != {"inn", "company_role", "offset", "limit"}:
        return False
    if not (
        parameters.get("inn") == target_inn
        and type(parameters.get("inn")) is str
        and parameters.get("company_role") == "ALL"
        and type(parameters.get("company_role")) is str
        and type(parameters.get("offset")) is int
        and parameters.get("offset") == 0
        and type(parameters.get("limit")) is int
        and parameters.get("limit") == 1000
    ):
        return False
    requested_identifiers = getattr(result, "requested_identifiers", None)
    if type(requested_identifiers) is not list or requested_identifiers:
        return False
    if not isinstance(received_at, datetime) or received_at.tzinfo is None or received_at.utcoffset() != timedelta(0):
        return False
    status_code = getattr(result, "status_code", None)
    try:
        response_hash = calculate_response_hash(raw_payload)
    except (TypeError, ValueError, OverflowError, UnicodeError):
        return False
    return (
        getattr(result, "provider", None) == "datanewton"
        and getattr(result, "dataset", None) == "arbitration_cases"
        and getattr(result, "endpoint", None) == ARBITRATION_CASES_ENDPOINT
        and getattr(result, "requested_identifier", None) == target_inn
        and getattr(result, "request_body", _MISSING) is None
        and type(status_code) is int
        and status_code == 200
        and getattr(result, "request_id", None) == request_id
        and getattr(result, "response_hash", None) == response_hash
    )


def build_arbitration_chart_facts(basis: ArbitrationBasisV2) -> ArbitrationChartFactsV1:
    first_reason = basis.completion_reasons[0]
    limitation_codes = tuple(item.code for item in basis.limitations)
    if first_reason in {"operation_gate_closed", "evidence_gate_closed"}:
        return ArbitrationChartFactsV1(collection_state="gate_closed", limitation_codes=limitation_codes)
    if first_reason in {
        "privacy_key_unavailable",
        "provider_error",
        "provider_binding_invalid",
        "lexical_transport_invalid",
        "envelope_invalid",
    }:
        return ArbitrationChartFactsV1(collection_state="failed", limitation_codes=limitation_codes)

    roles = Counter(case.role for case in basis.sanitized_cases)
    outcomes = Counter(case.outcome for case in basis.sanitized_cases)
    by_year: dict[int, Counter[str]] = {}
    for case in basis.sanitized_cases:
        if case.year is not None:
            by_year.setdefault(case.year, Counter())[case.role] += 1
    opponent_facts_available = "opponent_group_cap_exhausted" not in limitation_codes
    return ArbitrationChartFactsV1(
        collection_state="complete" if basis.collection_complete else "partial",
        source_total=basis.source_total,
        rows_observed=basis.counters.rows_observed,
        unique_case_count=basis.counters.unique_case_count,
        unknown_year_count=basis.unknown_year_count,
        role_counts=tuple(ArbitrationNamedCountV1(key=key, count=roles[key]) for key in _ROLE_KEYS),
        outcome_counts=tuple(ArbitrationNamedCountV1(key=key, count=outcomes[key]) for key in _OUTCOME_KEYS),
        year_role_facts=tuple(
            ArbitrationYearRoleFactV1(
                year=year,
                plaintiff=counts["plaintiff"],
                respondent=counts["respondent"],
                other=counts["other"],
                unattributed=counts["unattributed"],
            )
            for year, counts in sorted(by_year.items())
        ),
        rub_amount_case_count=sum(case.amount_state == "available" and case.currency_state == "rub" for case in basis.sanitized_cases),
        opponent_group_count=(basis.counters.opponent_group_count if opponent_facts_available else None),
        cases_without_safe_opponent=(sum(not case.opponent_tokens for case in basis.sanitized_cases) if opponent_facts_available else None),
        multi_opponent_case_count=(sum(len(case.opponent_tokens) > 1 for case in basis.sanitized_cases) if opponent_facts_available else None),
        limitation_codes=limitation_codes,
    )


def arbitration_chart_facts_hash(facts: ArbitrationChartFactsV1) -> str:
    return canonical_digest(facts.model_dump(mode="json"))


def arbitration_basis_metadata_reserve_mapping_v2(
    cases: tuple[SanitizedArbitrationCaseV2, ...],
) -> dict[str, object]:
    """Return the exact maximal non-case sizing mapping from the contract.

    This deliberately is not a semantic ``ArbitrationBasisV2`` instance:
    maximal counter/reason combinations violate normal runtime invariants.
    """
    all_noncomplete = list(ARBITRATION_COMPLETION_PRECEDENCE_V2[:-1])
    all_limitations = [{"code": code} for code in ARBITRATION_LIMITATION_PRECEDENCE_V2]
    return {
        "basis_version": "company_card_arbitration_basis_v2",
        "normalization_version": "company_card_arbitration_normalization_v2",
        "registry_version": ARBITRATION_REGISTRY_VERSION_V2,
        "contract_binding": ARBITRATION_CONTRACT_BINDING_V2,
        "openapi_sha256": ARBITRATION_OPENAPI_SHA256_V2,
        "runtime_dataset": "arbitration_cases",
        "endpoint": "GET /v1/arbitration-cases",
        "identity_policy": "arbitration_case_identity_case_id_only_v1",
        "target_policy": "arbitration_target_exact_inn_v1",
        "collection_policy": "datanewton_arbitration_single_page_1000_v1",
        "storage_budget_policy": "arbitration_basis_metadata_reserve_v1",
        "outcome_policy": "arbitration_party_result_narrow_v1",
        "currency_policy": "arbitration_rubles_only_v1",
        "privacy_policy": "arbitration_opponents_all_masked_v1",
        "source_total": 9_223_372_036_854_775_807,
        "page_manifest": [{
            "offset": 0,
            "limit": 1000,
            "returned_count": 1000,
            "accepted_count": 1000,
            "response_hash": "f" * 64,
        }],
        "provider_received_at": "9999-12-31T23:59:59.999999Z",
        "counters": {
            "pages_requested": 1,
            "pages_accepted": 1,
            "rows_observed": 1000,
            "rows_processed": 1000,
            "rows_shape_valid": 1000,
            "malformed_count": 1000,
            "oversized_case_count": 1,
            "storage_cap_rejected_count": 1,
            "duplicate_identical_count": 1000,
            "duplicate_conflict_row_count": 1000,
            "duplicate_conflict_key_count": 500,
            "unique_case_count": 1000,
            "opponent_token_count": 20_000_000,
            "opponent_group_count": 20_000,
            "opponent_group_probe_count": 20_001,
        },
        "completion_reasons": all_noncomplete,
        "collection_complete": False,
        "calendar_complete": False,
        "calendar_scope": "unverified",
        "unknown_year_count": 1000,
        "zero_years_proven": False,
        "mask_algorithm_version": "opponent_hmac_sha256_v1",
        "mask_key_id": "z" + "9" * 31,
        "sanitized_cases": [case.model_dump(mode="json") for case in cases],
        "limitations": all_limitations,
    }


def reserved_arbitration_basis_size_v2(cases: tuple[SanitizedArbitrationCaseV2, ...]) -> int:
    return len(canonical_json_bytes(arbitration_basis_metadata_reserve_mapping_v2(cases)))


def _validated_envelope(payload: object) -> tuple[int, list[object]] | None:
    if type(payload) is not dict:
        return None
    total = payload.get("total_cases", _MISSING)
    offset = payload.get("offset", _MISSING)
    limit = payload.get("limit", _MISSING)
    if type(total) is not int or not 0 <= total <= 9_223_372_036_854_775_807:
        return None
    if type(offset) is not int or offset != 0 or type(limit) is not int or limit != 1000:
        return None
    data = payload.get("data", _MISSING)
    if total == 0:
        if data is _MISSING:
            return 0, []
        if type(data) is not list or data:
            return None
        return 0, data
    if type(data) is not list or not 1 <= len(data) <= 1000:
        return None
    if total <= 1000 and len(data) != total:
        return None
    return total, data


def _sanitize_row(
    row: object,
    *,
    row_index: int,
    target_inn: str,
    report_id: UUID,
    mask_key_id: str,
    mask_secret: bytes,
    number_manifest: Mapping[str, object],
    collision_case_ids: set[str],
) -> SanitizedArbitrationCaseV2 | None:
    if type(row) is not dict:
        return None
    case_id = row.get("case_id")
    if not _valid_case_id(case_id):
        return None
    role_values: dict[str, list[dict[str, object]]] = {}
    for collection in _ROLE_COLLECTIONS:
        value = row.get(collection, _MISSING)
        if type(value) is not list or any(type(party) is not dict for party in value):
            return None
        role_values[collection] = value

    matching = {
        collection
        for collection, parties in role_values.items()
        if any(_exact_direct_target_inn(party.get("inn"), target_inn) for party in parties)
    }
    if matching == {"plaintiffs"}:
        role = "plaintiff"
    elif matching == {"respondents"}:
        role = "respondent"
    elif matching:
        role = "other"
    else:
        role = "unattributed"

    limitations: set[str] = set()
    first_number_value = row.get("first_number", _MISSING)
    if _valid_first_number(first_number_value):
        if first_number_value in collision_case_ids:
            first_number = None
            limitations.add("arbitration_first_number_identity_collision")
        else:
            first_number = first_number_value
    else:
        first_number = None
        limitations.add("arbitration_first_number_unavailable")

    date_start, start_invalid = _strict_date(row.get("date_start", _MISSING))
    date_update, update_invalid = _strict_date(row.get("date_update", _MISSING))
    if start_invalid or update_invalid:
        limitations.add("arbitration_date_invalid")
    duration_days = None
    if date_start is not None and date_update is not None:
        if date_update < date_start:
            limitations.add("arbitration_date_inversion")
        else:
            duration_days = (date_update - date_start).days

    raw_year = row.get("year", _MISSING)
    year = raw_year if type(raw_year) is int and 1900 <= raw_year <= 2100 else None
    if year is not None and date_start is not None and year != date_start.year:
        year = None
        limitations.add("arbitration_year_conflict")
    if year is None:
        limitations.add("arbitration_unknown_year")

    party_result = row.get("party_result")
    if (
        role in {"plaintiff", "respondent"}
        and isinstance(party_result, str)
        and party_result in {"WON", "LOST", "RETURNED"}
    ):
        outcome = {"WON": "won", "LOST": "lost", "RETURNED": "returned"}[party_result]
    else:
        outcome = "unknown"

    raw_amount = row.get("sum", _MISSING)
    if raw_amount is _MISSING or raw_amount is None:
        amount_state = "missing"
        amount = None
        limitations.add("arbitration_amount_missing")
    elif isinstance(raw_amount, bool) or not isinstance(raw_amount, (int, float)):
        amount_state = "invalid"
        amount = None
        limitations.add("arbitration_amount_invalid")
    else:
        amount = _bound_source_decimal(
            raw_amount,
            number_manifest.get(f"/data/{row_index}/sum"),
        )
        if amount is None:
            amount_state = "invalid"
            limitations.add("arbitration_amount_invalid")
        else:
            amount_state = "available"

    raw_currency = row.get("currency", _MISSING)
    if raw_currency is _MISSING or raw_currency is None:
        currency_state = "missing"
        limitations.add("arbitration_currency_missing")
    elif raw_currency == "RUBLES":
        currency_state = "rub"
    elif isinstance(raw_currency, str) and raw_currency.strip():
        currency_state = "unidentified"
        limitations.add("arbitration_currency_unidentified")
    else:
        currency_state = "invalid"
        limitations.add("arbitration_currency_invalid")

    eligible_collection = "respondents" if role == "plaintiff" else "plaintiffs" if role == "respondent" else None
    tokens: list[PrivateOpponentTokenV2] = []
    if eligible_collection is not None:
        for ordinal, party in enumerate(role_values[eligible_collection]):
            tokens.append(
                _opponent_token(
                    party,
                    report_id=report_id,
                    case_id=case_id,
                    collection=eligible_collection,
                    ordinal=ordinal,
                    mask_key_id=mask_key_id,
                    mask_secret=mask_secret,
                )
            )
    unique_tokens = tuple(sorted({token.value: token for token in tokens}.values(), key=lambda token: token.value))
    return SanitizedArbitrationCaseV2(
        case_id=case_id,
        first_number=first_number,
        year=year,
        role=role,
        outcome=outcome,
        date_start=date_start,
        date_update=date_update,
        duration_days=duration_days,
        amount_state=amount_state,
        amount=amount,
        currency_state=currency_state,
        opponent_tokens=unique_tokens,
        limitations=_ordered_limitations(limitations),
    )


def _opponent_token(
    party: dict[str, object],
    *,
    report_id: UUID,
    case_id: str,
    collection: str,
    ordinal: int,
    mask_key_id: str,
    mask_secret: bytes,
) -> PrivateOpponentTokenV2:
    inn = party.get("inn")
    ogrn = party.get("ogrn")
    if _stable_identifier(inn, party.get("inn_src", _MISSING), kind="inn"):
        identity: dict[str, object] = {"kind": "inn", "value": inn}
    elif _stable_identifier(ogrn, party.get("ogrn_src", _MISSING), kind="ogrn"):
        identity = {"kind": "ogrn", "value": ogrn}
    else:
        identity = {
            "kind": "case_position",
            "case_key": case_id,
            "source_role_collection": collection,
            "zero_based_ordinal": ordinal,
        }
    payload = {
        "identity_version": "OpponentHmacIdentityV1",
        "domain": "company-card-v2:opponent:v1",
        "report_id": str(report_id).lower(),
        "entity_class": "masked_unknown",
        "identifier": identity,
    }
    value = hmac.new(mask_secret, canonical_json_bytes(payload), hashlib.sha256).hexdigest()
    return PrivateOpponentTokenV2(key_id=mask_key_id, value=value)


def _apply_opponent_group_cap(
    cases: tuple[SanitizedArbitrationCaseV2, ...],
) -> tuple[tuple[SanitizedArbitrationCaseV2, ...], int, int, int, bool]:
    distinct: set[str] = set()
    for case in cases:
        for token in case.opponent_tokens:
            distinct.add(token.value)
            if len(distinct) == OPPONENT_GROUP_OVERFLOW_SENTINEL:
                scrubbed = tuple(case_item.model_copy(update={"opponent_tokens": ()}) for case_item in cases)
                return scrubbed, 0, 0, OPPONENT_GROUP_OVERFLOW_SENTINEL, True
    token_count = sum(len(case.opponent_tokens) for case in cases)
    return cases, token_count, len(distinct), len(distinct), False


def _stable_identifier(value: object, provenance: object, *, kind: str) -> bool:
    lengths = {10, 12} if kind == "inn" else {13, 15}
    expected_provenance = kind.upper()
    return (
        isinstance(value, str)
        and value.isascii()
        and value.isdecimal()
        and len(value) in lengths
        and (provenance is _MISSING or provenance is None or provenance == expected_provenance)
    )


def _strict_date(value: object) -> tuple[date | None, bool]:
    if value is _MISSING or value is None:
        return None, False
    if not isinstance(value, str):
        return None, True
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None, True
    return (parsed, False) if parsed.isoformat() == value else (None, True)


def _bound_source_decimal(
    raw_value: object,
    manifest_lexeme: object,
) -> Decimal | None:
    """Bind an exact byte lexeme back to its decoded JSON number leaf.

    The trusted provider-parser lexeme remains the monetary source of truth.
    The decoded value is only a fail-closed consistency witness against a
    different JSON numeric topology or decoded leaf value.
    """
    if type(raw_value) not in {int, float} or type(manifest_lexeme) is not str:
        return None
    try:
        parsed = parse_source_decimal(manifest_lexeme)
    except DecimalTransportError:
        return None
    try:
        replayed = json.loads(
            manifest_lexeme,
            parse_constant=_reject_json_number_constant,
        )
    except (TypeError, ValueError):
        return None
    if (
        type(replayed) is not type(raw_value)
        or replayed != raw_value
        or (type(replayed) is float and not math.isfinite(replayed))
    ):
        return None
    return parsed.value


def _reject_json_number_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _valid_case_id(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    import unicodedata

    unsafe_scalar = any(
        ord(char) <= 0x1F
        or 0x7F <= ord(char) <= 0x9F
        or 0xD800 <= ord(char) <= 0xDFFF
        or 0x202A <= ord(char) <= 0x202E
        or 0x2066 <= ord(char) <= 0x2069
        for char in value
    )
    return (
        value == unicodedata.normalize("NFC", value)
        and value == value.strip()
        and len(value) <= 256
        and not unsafe_scalar
        and len(value.encode("utf-8")) <= 1024
    )


def _valid_first_number(value: object) -> bool:
    if not isinstance(value, str):
        return False
    import unicodedata

    return (
        value == unicodedata.normalize("NFC", value)
        and value == value.strip()
        and 1 <= len(value) <= 22
        and not any(0xD800 <= ord(char) <= 0xDFFF for char in value)
        and len(value.encode("utf-8")) <= 32
        and _FIRST_NUMBER.fullmatch(value) is not None
    )


def _exact_direct_target_inn(value: object, target_inn: str) -> bool:
    return isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) in {10, 12} and value == target_inn


def _require_target_and_key(
    *, target_inn: str, report_id: UUID, mask_key_id: str, mask_secret: bytes
) -> None:
    if not isinstance(report_id, UUID):
        raise ArbitrationV2NormalizationError("report id must be a UUID")
    if not isinstance(target_inn, str) or not target_inn.isascii() or not target_inn.isdecimal() or len(target_inn) not in {10, 12}:
        raise ArbitrationV2NormalizationError("target INN is invalid")
    if type(mask_key_id) is not str or _MASK_KEY_ID.fullmatch(mask_key_id) is None:
        raise ArbitrationV2NormalizationError("mask key id is invalid")
    if type(mask_secret) is not bytes or not 32 <= len(mask_secret) <= 64:
        raise ArbitrationV2NormalizationError("mask secret must contain 32 to 64 bytes")


def _ordered_completion_reasons(reasons: set[str]) -> tuple[str, ...]:
    if not reasons:
        return ("complete",)
    return tuple(reason for reason in ARBITRATION_COMPLETION_PRECEDENCE_V2 if reason in reasons)


def _ordered_limitations(codes: set[str]) -> tuple[str, ...]:
    return tuple(code for code in ARBITRATION_LIMITATION_PRECEDENCE_V2 if code in codes)


def _basis_limitations(codes: object) -> tuple[ArbitrationBasisLimitationV2, ...]:
    code_set = set(codes)  # type: ignore[arg-type]
    return tuple(
        ArbitrationBasisLimitationV2(code=code)  # type: ignore[arg-type]
        for code in ARBITRATION_LIMITATION_PRECEDENCE_V2
        if code in code_set
    )


__all__ = [
    "ARBITRATION_CONTRACT_BINDING_V2",
    "ARBITRATION_OPENAPI_SHA256_V2",
    "ARBITRATION_REGISTRY_VERSION_V2",
    "ArbitrationV2NormalizationError",
    "arbitration_basis_metadata_reserve_mapping_v2",
    "arbitration_chart_facts_hash",
    "arbitration_result_is_exactly_bound_v2",
    "build_arbitration_chart_facts",
    "empty_arbitration_basis_v2",
    "normalize_arbitration_result_v2",
    "reserved_arbitration_basis_size_v2",
]
