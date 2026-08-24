from __future__ import annotations

import hmac
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import re
from typing import Any
from uuid import UUID

from .canonical_json import canonical_json_bytes
from .evidence import EvidenceGate, arbitration_provider_allowed
from .models import (
    ArbitrationBasisV1, ArbitrationCollectionCountersV1,
    ArbitrationPageManifestV1, InternalCaseIdentityV1, LimitationV1,
    PrivateArbitrationCaseV1, PrivateOpponentTokenV1,
)

MAX_ROWS = 1000
MAX_CASES = 1000
MAX_PAGES = 10
PAGE_SIZE = 100
MAX_CASE_BYTES = 256 * 1024
MAX_BASIS_BYTES = 8 * 1024 * 1024
_MASK_KEY_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_ROLE_COLLECTIONS = (
    "plaintiffs", "respondents", "applicants", "creditors",
    "creditors_current_payments", "debtors", "interested_persons",
    "third_parties", "others",
)
_COMPLETION_PRECEDENCE = (
    "privacy_key_unavailable", "envelope_gate_closed", "envelope_invalid",
    "provider_error", "total_drift", "offset_drift", "duplicate_conflict",
    "oversized_case", "storage_cap_exhausted", "case_cap_exhausted",
    "max_pages_exhausted", "non_progress", "complete",
)
_REQUIRED_ENVELOPE_GATES = (
    "arbitration_total_path", "arbitration_total_type", "total_scope",
    "data_path", "offset_path", "limit_path", "shape_version",
)


class ArbitrationGateClosedError(RuntimeError):
    code = "arbitration_provider_gate_closed"


@dataclass(frozen=True)
class FixtureArbitrationCollectionV1:
    """Pure sanitized fixture collection; it has no provider or DB dependency."""

    basis: ArbitrationBasisV1
    shape_version: str | None
    source_total: int | None
    page_manifest: tuple[ArbitrationPageManifestV1, ...]
    counters: ArbitrationCollectionCountersV1
    completion_reasons: tuple[str, ...]
    completion_reason: str
    collection_complete: bool
    calendar_complete: bool
    calendar_scope: str
    unknown_year_count: int
    zero_years_proven: bool
    limitations: tuple[LimitationV1, ...]


def require_arbitration_provider_gate(registry: object = None) -> None:
    if not arbitration_provider_allowed(registry if isinstance(registry, dict) else None):
        raise ArbitrationGateClosedError("arbitration provider envelope is not verified")


def private_opponent_token(
    *,
    secret: bytes,
    key_id: str,
    opponent_identifier: str | None = None,
    stable_identifier_kind: str | None = None,
    report_id: UUID | str | None = None,
    case_key: str | None = None,
    source_role_collection: str | None = None,
    zero_based_ordinal: int | None = None,
) -> PrivateOpponentTokenV1:
    """Create only a report-scoped full HMAC-SHA-256 opaque token.

    A stable opponent identifier needs its independently supplied verified
    kind; the parser must never derive that kind from its length.  Fixture
    collection otherwise uses the explicit
    report/case/role/ordinal identity, so neither a name nor provider arrival
    ordering becomes a public or cross-report token.
    """
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("masking secret must contain at least 32 bytes")
    if not _MASK_KEY_ID_RE.fullmatch(key_id):
        raise ValueError("masking key id is invalid")
    if opponent_identifier is not None:
        if (
            report_id is None
            or stable_identifier_kind not in {"inn", "ogrn"}
            or not isinstance(opponent_identifier, str)
            or not opponent_identifier.strip()
        ):
            raise ValueError("opponent identifier is invalid")
        identity: dict[str, object] = {
            "kind": stable_identifier_kind,
            "value": opponent_identifier.strip(),
        }
    else:
        if report_id is None or not isinstance(case_key, str) or not case_key.strip():
            raise ValueError("report-scoped opponent identity is required")
        if source_role_collection not in _ROLE_COLLECTIONS or not isinstance(zero_based_ordinal, int) or zero_based_ordinal < 0:
            raise ValueError("case-position opponent identity is invalid")
        identity = {
            "kind": "case_position",
            "case_key": case_key.strip(),
            "source_role_collection": source_role_collection,
            "zero_based_ordinal": zero_based_ordinal,
        }
    report_text = str(report_id).lower() if report_id is not None else "legacy"
    payload = {
        "identity_version": "OpponentHmacIdentityV1",
        "domain": "company-card-v2:opponent:v1",
        "report_id": report_text,
        "entity_class": "masked_unknown",
        "identifier": identity,
    }
    value = hmac.new(secret, canonical_json_bytes(payload), hashlib.sha256).hexdigest()
    return PrivateOpponentTokenV1(key_id=key_id, value=value)


def build_fixture_arbitration_basis(
    rows: Iterable[dict[str, Any]], *, secret: bytes, key_id: str, target_inn: str | None = None,
    report_id: UUID | str | None = None,
) -> ArbitrationBasisV1:
    """Bounded synthetic-page normalization; never makes a provider call."""
    dedup: dict[tuple[str, str], PrivateArbitrationCaseV1] = {}
    conflicted: set[tuple[str, str]] = set()
    total_bytes = 0
    for index, row in enumerate(rows):
        if index >= MAX_ROWS:
            break
        if not isinstance(row, dict):
            continue
        try:
            row_size = len(canonical_json_bytes(row))
        except ValueError:
            # A non-canonical fixture row is not an admissible private fact.
            continue
        if row_size > MAX_CASE_BYTES or total_bytes + row_size > MAX_BASIS_BYTES:
            break
        total_bytes += row_size
        identity = _identity(row)
        if identity is None:
            continue
        roles = _roles_for_target(row, target_inn)
        opponent = _opponent_token_from_row(
            row, secret=secret, key_id=key_id, report_id=report_id, case_key=identity.value,
        )
        candidate = PrivateArbitrationCaseV1(
            identity=identity, roles=roles,
            started_at=_as_date(row.get("started_at")), updated_at=_as_date(row.get("updated_at")),
            opponent=opponent,
            amount=_as_decimal(row.get("amount")),
        )
        key = (identity.source_kind, identity.value)
        if key in conflicted:
            continue
        existing = dedup.get(key)
        if existing is None:
            dedup[key] = candidate
        elif existing != candidate:
            # Conflicting duplicates are removed instead of selecting an arbitrary fact.
            dedup.pop(key, None)
            conflicted.add(key)
    cases = tuple(sorted(dedup.values(), key=lambda item: (item.identity.source_kind, item.identity.value)))[:MAX_CASES]
    return ArbitrationBasisV1(
        counters=ArbitrationCollectionCountersV1(
            rows_observed=len(cases), rows_shape_valid=len(cases), unique_case_count=len(cases),
        ),
        cases=cases,
        limitations=(LimitationV1(code="arbitration_public_gate_closed", field="arbitration"),),
    )


def collect_fixture_arbitration_pages(
    pages: Iterable[object], *, registry: dict[str, object], secret: bytes | None,
    key_id: str | None, target_inn: str, report_id: UUID | str,
    visible_case_number_gate: bool = False,
) -> FixtureArbitrationCollectionV1:
    """Collect already-supplied fixture pages under the section-31 bounds.

    This is deliberately a pure test seam: it accepts page *values*, never a
    provider callback, URL, client or credentials.  The shipped registry stays
    closed; a caller must supply a complete synthetic verified registry.
    """
    if not _fixture_registry_verified(registry):
        return _empty_collection("envelope_gate_closed")
    if not isinstance(secret, bytes) or len(secret) < 32 or not isinstance(key_id, str) or not _MASK_KEY_ID_RE.fullmatch(key_id):
        return _empty_collection("privacy_key_unavailable")

    counters = {field: 0 for field in ArbitrationCollectionCountersV1.model_fields}
    manifest: list[ArbitrationPageManifestV1] = []
    limitations: list[LimitationV1] = [LimitationV1(code="arbitration_public_gate_closed", field="arbitration")]
    reasons: set[str] = set()
    admitted: dict[tuple[str, str], tuple[PrivateArbitrationCaseV1, bytes]] = {}
    conflicted: set[tuple[str, str]] = set()
    seen_hashes: set[str] = set()
    seen_row_hashes: set[str] = set()
    source_total: int | None = None
    expected_offset = 0
    unknown_year_count = 0
    stopped = False
    admitted_case_bytes = 0

    for page_index, page in enumerate(pages):
        if page_index >= MAX_PAGES:
            reasons.add("max_pages_exhausted")
            break
        counters["pages_requested"] += 1
        if not isinstance(page, dict):
            reasons.add("envelope_invalid")
            break
        if page.get("provider_error") is not None:
            reasons.add("provider_error")
            break
        rows = page.get("data")
        total = page.get("total_cases")
        offset = page.get("offset")
        limit = page.get("limit")
        if not isinstance(rows, list) or not isinstance(total, int) or isinstance(total, bool) or total < 0 or not isinstance(offset, int) or isinstance(offset, bool) or offset < 0 or limit != PAGE_SIZE:
            reasons.add("envelope_invalid")
            break
        if len(rows) > PAGE_SIZE:
            reasons.add("envelope_invalid")
            break
        if source_total is None:
            source_total = total
        elif total != source_total:
            reasons.add("total_drift")
            break
        if offset != expected_offset:
            reasons.add("offset_drift")
            break
        page_hash = hashlib.sha256(canonical_json_bytes(page)).hexdigest()
        row_hash = hashlib.sha256(canonical_json_bytes(rows)).hexdigest()
        if (page_hash in seen_hashes or row_hash in seen_row_hashes) and rows:
            reasons.add("non_progress")
            break
        seen_hashes.add(page_hash)
        seen_row_hashes.add(row_hash)
        if not rows and expected_offset < total:
            reasons.add("non_progress")
            break

        accepted_before = len(admitted)
        counters["pages_accepted"] += 1
        for row in rows:
            if counters["rows_observed"] >= MAX_ROWS:
                reasons.add("case_cap_exhausted")
                stopped = True
                break
            counters["rows_observed"] += 1
            candidate = _sanitize_fixture_case(
                row, secret=secret, key_id=key_id, target_inn=target_inn, report_id=report_id,
            )
            if candidate is None:
                counters["malformed_count"] += 1
                continue
            case, case_limitations, year_unknown, masked_unknown = candidate
            counters["rows_shape_valid"] += 1
            unknown_year_count += year_unknown
            counters["masked_unknown_count"] += masked_unknown
            limitations.extend(case_limitations)
            case_bytes = canonical_json_bytes(case.model_dump(mode="json"))
            if len(case_bytes) > MAX_CASE_BYTES:
                counters["oversized_case_count"] += 1
                reasons.add("oversized_case")
                stopped = True
                break
            key = (case.identity.source_kind, case.identity.value)
            if key in conflicted:
                counters["duplicate_conflict_row_count"] += 1
                continue
            existing = admitted.get(key)
            if existing is not None:
                if existing[1] == case_bytes:
                    counters["duplicate_identical_count"] += 1
                else:
                    admitted_case_bytes -= len(existing[1]) + 1
                    admitted.pop(key)
                    conflicted.add(key)
                    counters["duplicate_conflict_row_count"] += 1
                    counters["duplicate_conflict_key_count"] += 1
                    reasons.add("duplicate_conflict")
                continue
            proposed = dict(admitted)
            proposed[key] = (case, case_bytes)
            # Most rows are far below the 8 MiB threshold.  Avoid repeatedly
            # serializing every prior case; only a threshold candidate pays the
            # exact whole-basis CJSON cost.
            projected_case_bytes = admitted_case_bytes + len(case_bytes) + 1
            if projected_case_bytes > MAX_BASIS_BYTES or (
                projected_case_bytes > MAX_BASIS_BYTES - 65536
                and len(canonical_json_bytes(_basis_cap_payload(proposed, source_total, manifest))) > MAX_BASIS_BYTES
            ):
                reasons.add("storage_cap_exhausted")
                stopped = True
                break
            admitted[key] = (case, case_bytes)
            admitted_case_bytes = projected_case_bytes
        manifest.append(ArbitrationPageManifestV1(
            offset=offset, limit=limit, returned_count=len(rows),
            accepted_count=max(0, len(admitted) - accepted_before), page_hash=page_hash,
        ))
        expected_offset += len(rows)
        if stopped:
            break
        if len(rows) < PAGE_SIZE and expected_offset < total:
            reasons.add("non_progress")
            break
        if expected_offset >= total:
            break

    counters["unique_case_count"] = len(admitted)
    ordered_cases = tuple(case for _, (case, _) in sorted(admitted.items(), key=lambda item: item[1][1]))
    if not reasons and source_total is not None and expected_offset >= source_total:
        reasons.add("complete")
    elif not reasons and counters["pages_requested"] >= MAX_PAGES and source_total is not None and expected_offset < source_total:
        reasons.add("max_pages_exhausted")
    elif not reasons:
        reasons.add("non_progress")
    ordered_reasons = tuple(reason for reason in _COMPLETION_PRECEDENCE if reason in reasons)
    counter_model = ArbitrationCollectionCountersV1(**counters)
    basis = ArbitrationBasisV1(
        shape_version=_fixture_shape_version(registry), source_total=source_total,
        page_manifest=tuple(manifest), counters=counter_model,
        completion_reasons=ordered_reasons, collection_complete=ordered_reasons == ("complete",),
        calendar_complete=False, calendar_scope="unverified", unknown_year_count=unknown_year_count,
        zero_years_proven=False, mask_algorithm_version="opponent_hmac_sha256_v1", mask_key_id=key_id,
        cases=ordered_cases, limitations=tuple(_unique_limitations(limitations)),
    )
    return FixtureArbitrationCollectionV1(
        basis=basis, shape_version=basis.shape_version, source_total=basis.source_total,
        page_manifest=basis.page_manifest, counters=basis.counters,
        completion_reasons=basis.completion_reasons, completion_reason=ordered_reasons[0],
        collection_complete=basis.collection_complete, calendar_complete=basis.calendar_complete,
        calendar_scope=basis.calendar_scope, unknown_year_count=basis.unknown_year_count,
        zero_years_proven=basis.zero_years_proven, limitations=basis.limitations,
    )


def _fixture_registry_verified(registry: dict[str, object]) -> bool:
    if not isinstance(registry, dict):
        return False
    for name in _REQUIRED_ENVELOPE_GATES:
        gate = registry.get(name)
        if isinstance(gate, EvidenceGate):
            if gate.state != "verified":
                return False
        elif gate != "verified":
            return False
    return True


def _fixture_shape_version(registry: dict[str, object]) -> str | None:
    value = registry.get("shape_version")
    if isinstance(value, str) and value != "verified":
        return value
    return "fixture_verified_v1"


def _empty_collection(reason: str) -> FixtureArbitrationCollectionV1:
    limitation = LimitationV1(code=f"arbitration_{reason}", field="arbitration")
    return FixtureArbitrationCollectionV1(
        basis=ArbitrationBasisV1(cases=(), limitations=(limitation,)), shape_version=None,
        source_total=None, page_manifest=(), counters=ArbitrationCollectionCountersV1(),
        completion_reasons=(reason,), completion_reason=reason, collection_complete=False,
        calendar_complete=False, calendar_scope="unverified", unknown_year_count=0,
        zero_years_proven=False, limitations=(limitation,),
    )


def _sanitize_fixture_case(
    row: object, *, secret: bytes, key_id: str, target_inn: str, report_id: UUID | str,
) -> tuple[PrivateArbitrationCaseV1, tuple[LimitationV1, ...], int, int] | None:
    if not isinstance(row, dict):
        return None
    identity = _identity(row)
    if identity is None:
        return None
    started_at = _as_date(row.get("date_start"))
    updated_at = _as_date(row.get("date_update"))
    limitations: list[LimitationV1] = []
    if row.get("date_start") is not None and started_at is None:
        limitations.append(LimitationV1(code="arbitration_date_invalid", field="date_start"))
    if row.get("date_update") is not None and updated_at is None:
        limitations.append(LimitationV1(code="arbitration_date_invalid", field="date_update"))
    if started_at is not None and updated_at is not None and updated_at < started_at:
        limitations.append(LimitationV1(code="arbitration_date_inversion", field="date_update"))
    roles = _roles_for_target(row, target_inn)
    opponent = _opponent_token_from_row(row, secret=secret, key_id=key_id, report_id=report_id, case_key=identity.value)
    amount = _as_decimal(row.get("sum"))
    if amount is None:
        amount = _as_decimal(row.get("amount"))
    year = row.get("year")
    unknown_year = int(not isinstance(year, int) or isinstance(year, bool))
    return (
        PrivateArbitrationCaseV1(identity=identity, roles=roles, started_at=started_at,
            updated_at=updated_at, opponent=opponent, amount=amount),
        tuple(limitations), unknown_year, int(opponent is not None),
    )


def _basis_cap_payload(
    candidates: dict[tuple[str, str], tuple[PrivateArbitrationCaseV1, bytes]],
    source_total: int | None, manifest: list[ArbitrationPageProvenanceV1],
) -> dict[str, object]:
    return {
        "shape_version": "fixture_verified_v1", "source_total": source_total,
        "page_manifest": [item.model_dump(mode="json") for item in manifest],
        "sanitized_cases": [case.model_dump(mode="json") for _, (case, _) in sorted(candidates.items(), key=lambda item: item[1][1])],
        "mask_algorithm_version": "opponent_hmac_sha256_v1",
    }


def _unique_limitations(values: list[LimitationV1]) -> list[LimitationV1]:
    unique: dict[tuple[str, str], LimitationV1] = {}
    for value in values:
        unique.setdefault((value.code, value.field), value)
    return [unique[key] for key in sorted(unique)]


def visible_case_number(row: object, *, gate_verified: bool) -> str | None:
    """Return only the separately-gated observed visible-number field.

    The internal dedup key is deliberately never a display fallback.
    """
    if not gate_verified or not isinstance(row, dict):
        return None
    value = row.get("first_number")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def select_verified_alias(candidates: Iterable[dict[str, object]]) -> str | None:
    """Choose a legal/state alias only under explicit verified identity facts."""
    prepared: list[tuple[date | None, date | None, str, str]] = []
    expected_inn: str | None = None
    for candidate in candidates:
        if candidate.get("entity_class") not in {"legal", "state"} or candidate.get("identifier_verified") is not True:
            continue
        inn = candidate.get("inn")
        name = candidate.get("safe_name")
        case_key = candidate.get("case_key")
        if not isinstance(inn, str) or not re.fullmatch(r"(?:[0-9]{10}|[0-9]{12})", inn):
            continue
        if expected_inn is None:
            expected_inn = inn
        elif inn != expected_inn:
            return None
        if not isinstance(name, str) or not (normalized := name.strip()):
            continue
        if not isinstance(case_key, str) or not case_key.strip():
            continue
        prepared.append((_as_date(candidate.get("date_update")), _as_date(candidate.get("date_start")), normalized, case_key.strip()))
    if not prepared:
        return None
    # Greatest update, then greatest start; ties use scalar lexicographic name
    # and then the private case key only as deterministic selection evidence.
    best_date = max(item[0] or date.min for item in prepared)
    prepared = [item for item in prepared if (item[0] or date.min) == best_date]
    best_start = max(item[1] or date.min for item in prepared)
    prepared = [item for item in prepared if (item[1] or date.min) == best_start]
    return min(prepared, key=lambda item: (item[2], item[3]))[2]


def public_arbitration_nulls() -> dict[str, None]:
    return {f"A{number}": None for number in range(1, 6)}


def _identity(row: dict[str, Any]) -> InternalCaseIdentityV1 | None:
    for key in ("case_id", "id"):
        value = row.get(key)
        if isinstance(value, (str, int)) and str(value):
            return InternalCaseIdentityV1(source_kind=key, value=str(value))
    return None


def _roles_for_target(row: dict[str, Any], target_inn: str | None) -> tuple[str, ...]:
    """Attribute a case only on an exact target INN in source collections."""
    if not isinstance(target_inn, str) or not re.fullmatch(r"(?:[0-9]{10}|[0-9]{12})", target_inn):
        return ("other",)
    matched: list[str] = []
    for collection in _ROLE_COLLECTIONS:
        parties = row.get(collection)
        if not isinstance(parties, list):
            continue
        for party in parties:
            if isinstance(party, dict) and party.get("inn") == target_inn:
                matched.append(collection)
                break
    if len(matched) != 1 or matched[0] == "others":
        return ("other",)
    return (matched[0],)


def _opponent_token_from_row(
    row: dict[str, Any], *, secret: bytes, key_id: str, report_id: UUID | str | None, case_key: str,
) -> PrivateOpponentTokenV1 | None:
    """Mask only a fixture-provided private identifier; never inspect names."""
    identifier = row.get("opponent_identifier")
    identifier_kind = row.get("opponent_identifier_kind")
    if isinstance(identifier, str) and identifier.strip() and isinstance(identifier_kind, str) and report_id is not None:
        return private_opponent_token(
            secret=secret, key_id=key_id, report_id=report_id,
            opponent_identifier=identifier, stable_identifier_kind=identifier_kind,
        )
    if report_id is None:
        return None
    for collection in _ROLE_COLLECTIONS:
        parties = row.get(collection)
        if isinstance(parties, list) and parties:
            return private_opponent_token(
                secret=secret, key_id=key_id, report_id=report_id, case_key=case_key,
                source_role_collection=collection, zero_based_ordinal=0,
            )
    return None


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _as_decimal(value: object) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        try:
            return Decimal(value)
        except Exception:
            return None
    return None


__all__ = [
    "ArbitrationCollectionCountersV1", "ArbitrationGateClosedError",
    "ArbitrationPageManifestV1", "FixtureArbitrationCollectionV1",
    "MAX_BASIS_BYTES", "MAX_CASE_BYTES", "MAX_CASES",
    "MAX_PAGES", "MAX_ROWS", "PAGE_SIZE", "build_fixture_arbitration_basis",
    "collect_fixture_arbitration_pages", "private_opponent_token",
    "public_arbitration_nulls", "require_arbitration_provider_gate",
    "select_verified_alias", "visible_case_number",
]
