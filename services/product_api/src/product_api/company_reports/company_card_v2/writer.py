"""Default-off write-side builder for Company Card v2 snapshots.

This module is deliberately a narrow provider boundary. It is never imported
by public read code: the CompanyReport worker explicitly decides whether the
feature is enabled, opens the injected provider client, and atomically
finalizes the result afterwards.
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID

from product_api.company_reports.normalizers.finance import normalize_finance
from product_api.providers.datanewton import COUNTERPARTY_ENDPOINT, FINANCE_ENDPOINT

from .counterparty import CounterpartyShapeError, parse_observed_counterparty
from .decimal_transport import json_pointer_escape
from .finance import APPROVED_CODES, build_chart_facts, classify_finance_cell, finance_limitations
from .models import (
    ArbitrationBasisV1,
    CompanyCardV2SnapshotV2,
    FinanceBasisV1,
    FinanceCellV1,
    NarrativeEvidenceV1,
    PrimaryActivitySnapshotV1,
)
from .primary_activity import SOURCE_PROFILE_VERSION, PrimaryActivityV1, parse_primary_activity


H2_WRITER_PROFILE = "company_card_v2_writer_v3"
H2_PRESENTATION_CONTRACT = "company_public_h2_v1"
V2_SNAPSHOT_SCHEMA_VERSION = "company_card_v2_snapshot_v2"
_REPORT_VERSION = "3"
_INN_LENGTHS = frozenset({10, 12})
_MISSING = object()


class CompanyCardV2BuilderError(ValueError):
    """A fail-closed error before a V2 immutable snapshot can be produced."""


class CounterpartyProvider(Protocol):
    async def fetch_counterparty(
        self,
        identifier: str,
        *,
        filters: tuple[str, ...],
        request_id: str | None = None,
    ) -> object: ...


class CompanyCardV2WriterProvider(CounterpartyProvider, Protocol):
    async def fetch_finance(
        self,
        identifier: str,
        *,
        request_id: str | None = None,
    ) -> object: ...


@dataclass(frozen=True)
class PrimaryActivityWriterResult:
    activity: PrimaryActivityV1 | None
    source_profile_version: str = SOURCE_PROFILE_VERSION
    limitation_code: str | None = None

    def narrative_evidence(self) -> NarrativeEvidenceV1:
        """Convert only the admitted fact to the frozen V2 snapshot leaf."""
        if self.activity is None:
            return NarrativeEvidenceV1(limitation_code="primary_activity_not_admitted")
        return NarrativeEvidenceV1(
            primary_activity=PrimaryActivitySnapshotV1(
                code=self.activity.code,
                label=self.activity.label,
            )
        )


@dataclass(frozen=True)
class CompanyCardV2BuildOutcome:
    """The immutable artifact plus its explicit write-side lifecycle result.

    A snapshot can be finalized only after a valid counterparty dataset binds
    it to the target. A finance failure keeps that admitted data as a partial
    V2 result; it never manufactures financial values or requests arbitration.
    """

    snapshot: CompanyCardV2SnapshotV2
    lifecycle_status: Literal["complete", "partial"]


async def fetch_primary_activity(
    *,
    enabled: bool,
    provider: CounterpartyProvider,
    inn: str,
    request_id: str | None = None,
) -> PrimaryActivityWriterResult:
    """Fetch and admit the one approved activity fact, or return a safe null.

    This compatibility seam remains useful to callers that need only the
    activity evidence. The full V2 builder below additionally validates the
    writer tuple, counterparty core, finance basis, clock, and immutable
    snapshot shape.
    """
    if not enabled:
        return PrimaryActivityWriterResult(
            activity=None,
            limitation_code="primary_activity_not_admitted",
        )
    try:
        result = await provider.fetch_counterparty(
            inn,
            filters=("OKVED_BLOCK",),
            request_id=request_id,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        return PrimaryActivityWriterResult(
            activity=None,
            limitation_code="primary_activity_not_admitted",
        )
    activity = _admitted_primary_activity(result, target_inn=inn)
    return PrimaryActivityWriterResult(
        activity=activity,
        limitation_code=None if activity is not None else "primary_activity_not_admitted",
    )


async def build_company_card_v2_snapshot_v2(
    *,
    provider: CompanyCardV2WriterProvider,
    report_id: UUID,
    subject_inn: str,
    target_inn: str,
    writer_profile: str,
    report_version: str,
    presentation_contract: str,
    rollout_config_generation: int,
    now: datetime,
    request_id: str | None = None,
) -> CompanyCardV2SnapshotV2:
    """Build only the approved immutable V3/V2 snapshot shape.

    The function performs no hidden time, database, or network construction.
    The provider and timestamp are required injections from the worker. Its
    result intentionally contains no provider payload, headers, or errors.
    """
    return (
        await build_company_card_v2_snapshot_v2_outcome(
            provider=provider,
            report_id=report_id,
            subject_inn=subject_inn,
            target_inn=target_inn,
            writer_profile=writer_profile,
            report_version=report_version,
            presentation_contract=presentation_contract,
            rollout_config_generation=rollout_config_generation,
            now=now,
            request_id=request_id,
        )
    ).snapshot


async def build_company_card_v2_snapshot_v2_outcome(
    *,
    provider: CompanyCardV2WriterProvider,
    report_id: UUID,
    subject_inn: str,
    target_inn: str,
    writer_profile: str,
    report_version: str,
    presentation_contract: str,
    rollout_config_generation: int,
    now: datetime,
    request_id: str | None = None,
) -> CompanyCardV2BuildOutcome:
    """Build a V2 snapshot and expose only its complete/partial lifecycle."""
    _validate_builder_input(
        report_id=report_id,
        subject_inn=subject_inn,
        target_inn=target_inn,
        writer_profile=writer_profile,
        report_version=report_version,
        presentation_contract=presentation_contract,
        rollout_config_generation=rollout_config_generation,
        now=now,
    )
    base_request_id = request_id or f"company-report:{report_id}"

    try:
        counterparty_result = await provider.fetch_counterparty(
            target_inn,
            filters=("OKVED_BLOCK",),
            request_id=f"{base_request_id}:counterparty",
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise CompanyCardV2BuilderError("counterparty dataset is unavailable") from exc

    if not _counterparty_result_is_bound(counterparty_result, target_inn=target_inn):
        raise CompanyCardV2BuilderError("counterparty result is not bound to the V2 request")
    try:
        counterparty, counterparty_limitations = parse_observed_counterparty(
            _result_payload(counterparty_result)
        )
    except (CounterpartyShapeError, TypeError, ValueError) as exc:
        raise CompanyCardV2BuilderError("counterparty dataset cannot form a V2 snapshot") from exc
    if counterparty.inn != target_inn:
        raise CompanyCardV2BuilderError("counterparty core is not bound to the target")

    activity = _admitted_primary_activity(counterparty_result, target_inn=target_inn)
    narrative_evidence = PrimaryActivityWriterResult(
        activity=activity,
        limitation_code=None if activity is not None else "primary_activity_not_admitted",
    ).narrative_evidence()

    finance_basis = FinanceBasisV1()
    finance_available = False
    try:
        finance_result = await provider.fetch_finance(
            target_inn,
            request_id=f"{base_request_id}:finance",
        )
        if _finance_result_is_bound(finance_result, target_inn=target_inn):
            finance_basis = _finance_basis_from_result(finance_result)
            finance_available = True
    except asyncio.CancelledError:
        raise
    except Exception:
        # Per-dataset failure is deliberately contained: the admitted
        # counterparty snapshot remains a safe partial result. No raw error
        # escapes into an immutable artifact.
        finance_available = False

    limitations = tuple(
        [
            *counterparty_limitations,
            *finance_limitations(finance_basis),
        ]
    )
    snapshot = CompanyCardV2SnapshotV2(
        report_version=_REPORT_VERSION,
        writer_profile=H2_WRITER_PROFILE,
        presentation_contract=H2_PRESENTATION_CONTRACT,
        rollout_config_generation=rollout_config_generation,
        report_id=str(report_id),
        subject_inn=subject_inn,
        target_inn=target_inn,
        generated_at=now,
        counterparty=counterparty,
        finance_basis=finance_basis,
        arbitration_basis=ArbitrationBasisV1(),
        chart_facts=build_chart_facts(finance_basis),
        # V1 fixtures retain their frozen legacy literal. New V2 snapshots
        # bind the generation identity to the approved registry version.
        evidence_version="evidence_registry_v1",
        privacy_version="privacy_v1",
        limitations=limitations,
        snapshot_schema_version=V2_SNAPSHOT_SCHEMA_VERSION,
        narrative_evidence=narrative_evidence,
    )
    return CompanyCardV2BuildOutcome(
        snapshot=snapshot,
        lifecycle_status="complete" if finance_available else "partial",
    )


def _validate_builder_input(
    *,
    report_id: UUID,
    subject_inn: str,
    target_inn: str,
    writer_profile: str,
    report_version: str,
    presentation_contract: str,
    rollout_config_generation: int,
    now: datetime,
) -> None:
    if not isinstance(report_id, UUID):
        raise CompanyCardV2BuilderError("report_id must be a UUID")
    if not _valid_inn(subject_inn) or subject_inn != target_inn:
        raise CompanyCardV2BuilderError("subject and target must be the same exact INN")
    if (
        writer_profile,
        report_version,
        presentation_contract,
    ) != (H2_WRITER_PROFILE, _REPORT_VERSION, H2_PRESENTATION_CONTRACT):
        raise CompanyCardV2BuilderError("stored writer tuple is not eligible for the V2 builder")
    if isinstance(rollout_config_generation, bool) or not isinstance(rollout_config_generation, int) or rollout_config_generation <= 0:
        raise CompanyCardV2BuilderError("rollout configuration generation must be positive")
    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() != timedelta(0)
    ):
        raise CompanyCardV2BuilderError("explicit V2 builder clock must be UTC")


def _valid_inn(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.isascii()
        and value.isdecimal()
        and len(value) in _INN_LENGTHS
    )


def _admitted_primary_activity(result: object, *, target_inn: str) -> PrimaryActivityV1 | None:
    if not _counterparty_result_is_bound(result, target_inn=target_inn):
        return None
    return parse_primary_activity(
        _result_payload(result),
        expected_inn=target_inn,
        target_inn=_result_requested_identifier(result),
        requested_okved_block=True,
        dataset_success=True,
    )


def _counterparty_result_is_bound(result: object, *, target_inn: str) -> bool:
    if not _result_matches_dataset(
        result,
        dataset="counterparty",
        endpoint=COUNTERPARTY_ENDPOINT,
        target_inn=target_inn,
    ):
        return False
    parameters = _result_request_parameters(result)
    return (
        parameters is not None
        and set(parameters) == {"inn", "filters"}
        and parameters.get("inn") == target_inn
        and _is_exact_okved_filter(parameters.get("filters"))
    )


def _finance_result_is_bound(result: object, *, target_inn: str) -> bool:
    if not _result_matches_dataset(
        result,
        dataset="finance",
        endpoint=FINANCE_ENDPOINT,
        target_inn=target_inn,
    ):
        return False
    parameters = _result_request_parameters(result)
    return parameters is not None and parameters == {"inn": target_inn}


def _result_matches_dataset(
    result: object,
    *,
    dataset: str,
    endpoint: str,
    target_inn: str,
) -> bool:
    status_code = getattr(result, "status_code", None)
    return (
        getattr(result, "provider", None) == "datanewton"
        and getattr(result, "dataset", None) == dataset
        and getattr(result, "endpoint", None) == endpoint
        and _result_requested_identifier(result) == target_inn
        and isinstance(status_code, int)
        and not isinstance(status_code, bool)
        and 200 <= status_code < 300
        and isinstance(_result_payload(result), dict)
    )


def _result_requested_identifier(result: object) -> str | None:
    value = getattr(result, "requested_identifier", None)
    return value if isinstance(value, str) else None


def _result_payload(result: object) -> object:
    return getattr(result, "raw_payload", None)


def _result_request_parameters(result: object) -> Mapping[str, object] | None:
    value = getattr(result, "request_parameters", None)
    return value if isinstance(value, Mapping) else None


def _is_exact_okved_filter(value: object) -> bool:
    if value == "OKVED_BLOCK":
        return True
    if isinstance(value, (list, tuple)):
        return tuple(value) == ("OKVED_BLOCK",)
    return False


def _finance_basis_from_result(result: object) -> FinanceBasisV1:
    """Use the existing finance normalizer plus its ephemeral lexical gate.

    ``normalize_finance`` remains the authority for form/code/year discovery.
    The V2 bridge then reads a candidate only through the exact source path and
    the response-byte numeric manifest. Failed lexical transport yields the
    existing non-numeric state rather than a float-derived value.
    """
    facts = normalize_finance(result)  # type: ignore[arg-type]
    payload = _result_payload(result)
    if not isinstance(payload, dict):
        raise CompanyCardV2BuilderError("finance payload is invalid")
    manifest = getattr(result, "lexical_number_lexemes", {})
    if not isinstance(manifest, Mapping):
        manifest = {}
    transport_valid = getattr(result, "lexical_transport_valid", False) is True

    candidates: dict[tuple[str, str, int], list[_FinanceLexemeCandidate]] = {}
    for series in facts.indicators:
        form = getattr(series.form, "value", series.form)
        if not isinstance(form, str) or series.code not in APPROVED_CODES:
            continue
        for year in series.values_by_year:
            if isinstance(year, bool) or not isinstance(year, int):
                continue
            key = (form, series.code, year)
            entries = candidates.setdefault(key, [])
            for source_path in series.source_paths:
                entries.append(
                    _finance_lexeme_candidate(
                        payload=payload,
                        source_path=source_path,
                        year=year,
                        manifest=manifest,
                    )
                )

    cells: list[FinanceCellV1] = []
    for (form, code, year), entries in sorted(candidates.items()):
        cells.append(
            _classify_finance_candidates(
                form=form,
                code=code,
                year=year,
                candidates=entries,
                transport_valid=transport_valid,
            )
        )
    return FinanceBasisV1(cells=tuple(cells))


@dataclass(frozen=True)
class _FinanceLexemeCandidate:
    lexeme: str | None
    observed: bool
    invalid: bool = False
    unbound_number: bool = False


def _finance_lexeme_candidate(
    *,
    payload: dict[str, object],
    source_path: object,
    year: int,
    manifest: Mapping[str, object],
) -> _FinanceLexemeCandidate:
    pointer = _source_path_to_sum_pointer(source_path, year=year)
    if pointer is None:
        return _FinanceLexemeCandidate(None, observed=False, invalid=True)
    raw_value = _lookup_pointer(payload, pointer)
    if raw_value is _MISSING:
        return _FinanceLexemeCandidate(None, observed=False, invalid=True)
    if raw_value is None:
        return _FinanceLexemeCandidate(None, observed=False)
    if isinstance(raw_value, bool):
        return _FinanceLexemeCandidate(None, observed=True, invalid=True)
    if isinstance(raw_value, str):
        return _FinanceLexemeCandidate(raw_value, observed=True)
    manifest_value = manifest.get(pointer)
    if isinstance(manifest_value, str):
        return _FinanceLexemeCandidate(manifest_value, observed=True)
    return _FinanceLexemeCandidate(None, observed=True, unbound_number=True)


def _classify_finance_candidates(
    *,
    form: str,
    code: str,
    year: int,
    candidates: list[_FinanceLexemeCandidate],
    transport_valid: bool,
) -> FinanceCellV1:
    if any(candidate.invalid for candidate in candidates):
        return FinanceCellV1(form=form, code=code, year=year, state="invalid")
    if any(candidate.unbound_number for candidate in candidates):
        return FinanceCellV1(
            form=form,
            code=code,
            year=year,
            state="decimal_transport_lossy" if not transport_valid else "invalid",
        )
    lexemes = tuple(
        candidate.lexeme
        for candidate in candidates
        if candidate.lexeme is not None
    )
    if lexemes:
        return classify_finance_cell(
            form=form,
            code=code,
            year=year,
            lexemes=lexemes,
            transport_valid=transport_valid,
        )
    return FinanceCellV1(form=form, code=code, year=year, state="missing")


def _source_path_to_sum_pointer(source_path: object, *, year: int) -> str | None:
    if not isinstance(source_path, str) or not source_path.startswith("$"):
        return None
    tokens: list[str] = []
    cursor = 1
    while cursor < len(source_path):
        marker = source_path[cursor]
        if marker == ".":
            cursor += 1
            next_marker = cursor
            while next_marker < len(source_path) and source_path[next_marker] not in ".[":
                next_marker += 1
            token = source_path[cursor:next_marker]
            if not token:
                return None
            tokens.append(token)
            cursor = next_marker
            continue
        if marker == "[":
            end = source_path.find("]", cursor + 1)
            if end < 0 or not source_path[cursor + 1:end].isdigit():
                return None
            tokens.append(source_path[cursor + 1:end])
            cursor = end + 1
            continue
        return None
    return "/" + "/".join(
        json_pointer_escape(token)
        for token in (*tokens, "sum", str(year))
    )


def _lookup_pointer(payload: object, pointer: str) -> object:
    value = payload
    for raw_token in pointer.lstrip("/").split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            if token not in value:
                return _MISSING
            value = value[token]
        elif isinstance(value, list) and token.isdigit():
            index = int(token)
            if index >= len(value):
                return _MISSING
            value = value[index]
        else:
            return _MISSING
    return value


__all__ = [
    "CompanyCardV2BuildOutcome",
    "CompanyCardV2BuilderError",
    "CompanyCardV2WriterProvider",
    "CounterpartyProvider",
    "H2_PRESENTATION_CONTRACT",
    "H2_WRITER_PROFILE",
    "PrimaryActivityWriterResult",
    "V2_SNAPSHOT_SCHEMA_VERSION",
    "build_company_card_v2_snapshot_v2",
    "build_company_card_v2_snapshot_v2_outcome",
    "fetch_primary_activity",
]
