from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from product_api.company_reports.company_card_v2.evidence import ARBITRATION_EVIDENCE_BINDING_V2
from product_api.company_reports.company_card_v2.models import CompanyCardV2SnapshotV2, CompanyCardV2SnapshotV3
from product_api.company_reports.company_card_v2.writer import (
    CompanyCardV2BuilderError,
    build_company_card_v2_snapshot,
    build_company_card_v2_snapshot_outcome,
    build_company_card_v2_snapshot_v3_outcome,
)
from product_api.company_reports.persistence.errors import CompanyReportSnapshotError
from product_api.company_reports.persistence.v3 import (
    company_card_v2_to_snapshot,
    validate_company_card_v2_finalization,
)
from product_api.providers.datanewton import (
    COUNTERPARTY_ENDPOINT,
    FINANCE_ENDPOINT,
    DataNewtonResult,
    calculate_response_hash,
)


TARGET_INN = "7700000000"
REPORT_ID = UUID("00000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 8, 27, 1, 2, 3, tzinfo=timezone.utc)
SECRET = b"iteration-24-test-mask-secret-32b"


def _result(*, dataset: str, endpoint: str, payload: dict[str, object], parameters: dict[str, object], request_id: str) -> DataNewtonResult:
    return DataNewtonResult(
        dataset=dataset,
        endpoint=endpoint,
        requested_identifier=TARGET_INN,
        requested_identifiers=[],
        request_parameters=parameters,
        request_body=None,
        status_code=200,
        attempts=1,
        duration_ms=1,
        request_id=request_id,
        received_at=NOW,
        raw_payload=payload,
        lexical_transport_valid=True,
        lexical_number_lexemes={
            "/total_cases": "0",
            "/offset": "0",
            "/limit": "1000",
        },
        response_hash=calculate_response_hash(payload),
    )


def _counterparty_result(request_id: str) -> DataNewtonResult:
    payload = {
        "inn": TARGET_INN,
        "company": {
            "company_names": {"short_name": "Тест"},
            "okveds": [{"code": "62.01", "value": "Разработка ПО", "main": True, "mode": "new"}],
        },
    }
    return _result(
        dataset="counterparty",
        endpoint=COUNTERPARTY_ENDPOINT,
        payload=payload,
        parameters={"inn": TARGET_INN, "filters": "OKVED_BLOCK"},
        request_id=request_id,
    )


def _finance_result(request_id: str) -> DataNewtonResult:
    return _result(
        dataset="finance",
        endpoint=FINANCE_ENDPOINT,
        payload={},
        parameters={"inn": TARGET_INN},
        request_id=request_id,
    )


def _arbitration_result() -> DataNewtonResult:
    payload = {"total_cases": 0, "offset": 0, "limit": 1000}
    return _result(
        dataset="arbitration_cases",
        endpoint="/v1/arbitration-cases",
        payload=payload,
        parameters={"inn": TARGET_INN, "company_role": "ALL", "offset": 0, "limit": 1000},
        request_id=f"company-report:{REPORT_ID}",
    )


async def _base_provider_result(kind: str, request_id: str) -> DataNewtonResult:
    return _counterparty_result(request_id) if kind == "counterparty" else _finance_result(request_id)


def _builder_args(provider: object) -> dict[str, object]:
    return {
        "provider": provider,
        "report_id": REPORT_ID,
        "subject_inn": TARGET_INN,
        "target_inn": TARGET_INN,
        "writer_profile": "company_card_v2_writer_v3",
        "report_version": "3",
        "presentation_contract": "company_public_h2_v1",
        "rollout_config_generation": 7,
        "now": NOW,
    }


@pytest.mark.asyncio
async def test_generic_disabled_path_is_exact_v2_and_never_resolves_arbitration_method() -> None:
    calls: list[str] = []

    class Provider:
        async def fetch_counterparty(self, _identifier, *, filters, request_id=None):
            calls.append("counterparty")
            return await _base_provider_result("counterparty", request_id)

        async def fetch_finance(self, _identifier, *, request_id=None):
            calls.append("finance")
            return await _base_provider_result("finance", request_id)

        def __getattr__(self, name: str):
            if name == "fetch_arbitration_cases":
                raise AssertionError("disabled V2 dispatch touched arbitration callback")
            raise AttributeError(name)

    snapshot = await build_company_card_v2_snapshot(
        **_builder_args(Provider()),
        arbitration_enabled=False,
        arbitration_operation_enabled=True,
    )
    assert type(snapshot) is CompanyCardV2SnapshotV2
    assert snapshot.snapshot_schema_version == "company_card_v2_snapshot_v2"
    assert calls == ["counterparty", "finance"]


@pytest.mark.asyncio
async def test_generic_rejects_disabled_nonnull_key_tuple_before_provider_calls() -> None:
    class Provider:
        def __getattr__(self, name: str):
            raise AssertionError(f"invalid persisted tuple touched provider method {name}")

    with pytest.raises(CompanyCardV2BuilderError, match="null key tuple"):
        await build_company_card_v2_snapshot_outcome(
            **_builder_args(Provider()),
            arbitration_enabled=False,
            arbitration_key_id="active_2026",
            arbitration_key_secret=SECRET,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation_enabled", "evidence", "key_id", "secret", "reason", "state"),
    [
        (False, ARBITRATION_EVIDENCE_BINDING_V2, "active_2026", SECRET, "operation_gate_closed", "gate_closed"),
        (True, replace(ARBITRATION_EVIDENCE_BINDING_V2, openapi_sha256="0" * 64), "active_2026", SECRET, "evidence_gate_closed", "gate_closed"),
        (True, ARBITRATION_EVIDENCE_BINDING_V2, "missing", None, "privacy_key_unavailable", "failed"),
        (True, ARBITRATION_EVIDENCE_BINDING_V2, "active_2026", b"x" * 65, "privacy_key_unavailable", "failed"),
    ],
)
async def test_v3_preflight_is_ordered_and_makes_zero_arbitration_callbacks(
    operation_enabled, evidence, key_id, secret, reason, state
) -> None:
    class Provider:
        async def fetch_counterparty(self, _identifier, *, filters, request_id=None):
            return _counterparty_result(request_id)

        async def fetch_finance(self, _identifier, *, request_id=None):
            return _finance_result(request_id)

        async def fetch_arbitration_cases(self, *_args, **_kwargs):
            raise AssertionError("rejected preflight called arbitration provider")

    outcome = await build_company_card_v2_snapshot_v3_outcome(
        **_builder_args(Provider()),
        arbitration_operation_enabled=operation_enabled,
        arbitration_evidence=evidence,
        arbitration_key_id=key_id,
        arbitration_key_secret=secret,
    )
    assert type(outcome.snapshot) is CompanyCardV2SnapshotV3
    assert outcome.snapshot.snapshot_schema_version == "company_card_v2_snapshot_v3"
    assert outcome.snapshot.arbitration_basis.completion_reasons == (reason,)
    assert outcome.snapshot.arbitration_chart_facts.collection_state == state
    assert outcome.lifecycle_status == "partial"
    assert outcome.snapshot.arbitration_basis.mask_key_id is None


@pytest.mark.asyncio
async def test_v3_calls_exact_single_request_and_can_complete_exact_empty_population() -> None:
    arbitration_calls: list[tuple[object, ...]] = []

    class Provider:
        async def fetch_counterparty(self, _identifier, *, filters, request_id=None):
            return _counterparty_result(request_id)

        async def fetch_finance(self, _identifier, *, request_id=None):
            return _finance_result(request_id)

        async def fetch_arbitration_cases(self, identifier, *, company_role, offset, limit, request_id):
            arbitration_calls.append((identifier, company_role, offset, limit, request_id))
            return _arbitration_result()

    outcome = await build_company_card_v2_snapshot_outcome(
        **_builder_args(Provider()),
        arbitration_enabled=True,
        arbitration_operation_enabled=True,
        arbitration_key_id="active_2026",
        arbitration_key_secret=SECRET,
    )

    assert type(outcome.snapshot) is CompanyCardV2SnapshotV3
    assert outcome.lifecycle_status == "complete"
    assert outcome.snapshot.arbitration_basis.completion_reasons == ("complete",)
    assert outcome.snapshot.arbitration_basis.source_total == 0
    assert outcome.snapshot.arbitration_basis.mask_key_id == "active_2026"
    assert outcome.snapshot.arbitration_chart_facts.collection_state == "complete"
    assert arbitration_calls == [
        (TARGET_INN, "ALL", 0, 1000, f"company-report:{REPORT_ID}"),
    ]
    assert CompanyCardV2SnapshotV3.model_validate(outcome.snapshot.model_dump(mode="json")) == outcome.snapshot

    v3_with_v2_discriminator = outcome.snapshot.model_copy(
        update={"snapshot_schema_version": "company_card_v2_snapshot_v2"},
    )
    with pytest.raises(CompanyReportSnapshotError, match="snapshot"):
        company_card_v2_to_snapshot(v3_with_v2_discriminator)
    with pytest.raises(CompanyReportSnapshotError, match="snapshot"):
        validate_company_card_v2_finalization(
            v3_with_v2_discriminator,
            report_id=REPORT_ID,
            subject_inn=TARGET_INN,
            writer_profile="company_card_v2_writer_v3",
            report_version="3",
            presentation_contract="company_public_h2_v1",
            rollout_config_generation=7,
        )

    tampered = outcome.snapshot.model_dump(mode="json")
    tampered["arbitration_chart_facts_hash"] = "0" * 64
    with pytest.raises(ValidationError, match="arbitration facts hash"):
        CompanyCardV2SnapshotV3.model_validate(tampered)


@pytest.mark.asyncio
async def test_provider_failure_retains_resolved_key_but_no_raw_exception() -> None:
    marker = "RAW PROVIDER FAILURE MARKER"

    class Provider:
        async def fetch_counterparty(self, _identifier, *, filters, request_id=None):
            return _counterparty_result(request_id)

        async def fetch_finance(self, _identifier, *, request_id=None):
            return _finance_result(request_id)

        async def fetch_arbitration_cases(self, *_args, **_kwargs):
            raise RuntimeError(marker)

    outcome = await build_company_card_v2_snapshot_v3_outcome(
        **_builder_args(Provider()),
        arbitration_operation_enabled=True,
        arbitration_key_id="active_2026",
        arbitration_key_secret=SECRET,
    )
    assert outcome.snapshot.arbitration_basis.completion_reasons == ("provider_error",)
    assert outcome.snapshot.arbitration_basis.mask_key_id == "active_2026"
    assert marker not in str(outcome.snapshot.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_arbitration_cancellation_propagates() -> None:
    class Provider:
        async def fetch_counterparty(self, _identifier, *, filters, request_id=None):
            return _counterparty_result(request_id)

        async def fetch_finance(self, _identifier, *, request_id=None):
            return _finance_result(request_id)

        async def fetch_arbitration_cases(self, *_args, **_kwargs):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await build_company_card_v2_snapshot_v3_outcome(
            **_builder_args(Provider()),
            arbitration_operation_enabled=True,
            arbitration_key_id="active_2026",
            arbitration_key_secret=SECRET,
        )
