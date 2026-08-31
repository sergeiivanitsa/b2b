from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from product_api.company_reports.company_card_v2.models import CompanyCardV2SnapshotV2
from product_api.company_reports.company_card_v2.writer import (
    CompanyCardV2BuilderError,
    build_company_card_v2_snapshot_v2,
    build_company_card_v2_snapshot_v2_outcome,
    fetch_primary_activity,
)
from product_api.company_reports.company_card_v2 import writer as writer_module
from product_api.providers.datanewton import (
    COUNTERPARTY_ENDPOINT,
    FINANCE_ENDPOINT,
    DataNewtonResult,
    calculate_response_hash,
)


TARGET_INN = "7700000000"
REPORT_ID = UUID("00000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def _counterparty_payload(*, activity=True):
    payload = {
        "inn": TARGET_INN,
        "company": {
            "company_names": {"short_name": "Тест"},
        },
    }
    if activity:
        payload["company"]["okveds"] = [
            {
                "code": "62.01",
                "value": "Разработка программного обеспечения",
                "main": True,
                "mode": "new",
            },
        ]
    return payload


def _result(
    *,
    dataset="counterparty",
    endpoint=COUNTERPARTY_ENDPOINT,
    target=TARGET_INN,
    status=200,
    parameters=None,
    payload=None,
):
    if parameters is None:
        parameters = (
            {"inn": target, "filters": "OKVED_BLOCK"}
            if dataset == "counterparty"
            else {"inn": target}
        )
    raw_payload = payload if payload is not None else _counterparty_payload()
    return DataNewtonResult(
        dataset=dataset,
        endpoint=endpoint,
        requested_identifier=target,
        request_parameters=parameters,
        status_code=status,
        attempts=1,
        duration_ms=0,
        received_at=NOW,
        raw_payload=raw_payload,
        response_hash=calculate_response_hash(raw_payload),
    )


@pytest.mark.asyncio
async def test_disabled_writer_makes_zero_provider_calls():
    class Provider:
        async def fetch_counterparty(self, *_args, **_kwargs):
            raise AssertionError("disabled writer must not call provider")

    result = await fetch_primary_activity(
        enabled=False,
        provider=Provider(),
        inn=TARGET_INN,
    )
    assert result.activity is None
    assert result.limitation_code == "primary_activity_not_admitted"


@pytest.mark.asyncio
async def test_enabled_writer_requests_only_okved_block_and_stores_one_admitted_fact():
    calls = []

    class Provider:
        async def fetch_counterparty(self, identifier, *, filters, request_id=None):
            calls.append((identifier, filters, request_id))
            return _result()

    result = await fetch_primary_activity(
        enabled=True,
        provider=Provider(),
        inn=TARGET_INN,
        request_id="writer-test",
    )

    assert calls == [(TARGET_INN, ("OKVED_BLOCK",), "writer-test")]
    assert result.activity is not None
    assert (result.activity.code, result.activity.label) == (
        "62.01",
        "Разработка программного обеспечения",
    )
    evidence = result.narrative_evidence().model_dump(mode="json")
    assert evidence["primary_activity"] == {
        "code": "62.01",
        "label": "Разработка программного обеспечения",
        "is_primary": True,
    }
    assert "okveds" not in str(evidence)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        _result(target="7800000000"),
        _result(status=500),
        _result(parameters={"inn": TARGET_INN, "filters": "MANAGER_BLOCK"}),
        _result(endpoint=FINANCE_ENDPOINT),
        _result(dataset="finance", endpoint=FINANCE_ENDPOINT),
    ],
)
async def test_target_profile_dataset_or_endpoint_failure_is_safe_missing_activity(result):
    class Provider:
        async def fetch_counterparty(self, *_args, **_kwargs):
            return result

    outcome = await fetch_primary_activity(
        enabled=True,
        provider=Provider(),
        inn=TARGET_INN,
    )

    assert outcome.activity is None
    assert outcome.narrative_evidence().primary_activity is None
    assert outcome.narrative_evidence().limitation_code == "primary_activity_not_admitted"


@pytest.mark.asyncio
async def test_v2_builder_validates_stored_tuple_before_any_provider_call():
    class Provider:
        async def fetch_counterparty(self, *_args, **_kwargs):
            raise AssertionError("invalid stored tuple must not call provider")

        async def fetch_finance(self, *_args, **_kwargs):
            raise AssertionError("invalid stored tuple must not call provider")

    with pytest.raises(CompanyCardV2BuilderError, match="stored writer tuple"):
        await build_company_card_v2_snapshot_v2(
            provider=Provider(),
            report_id=REPORT_ID,
            subject_inn=TARGET_INN,
            target_inn=TARGET_INN,
            writer_profile="h1_legacy_writer_v2",
            report_version="3",
            presentation_contract="company_public_h2_v1",
            rollout_config_generation=1,
            now=NOW,
        )


@pytest.mark.asyncio
async def test_v2_builder_writes_only_v2_and_calls_exact_allowed_provider_tuple():
    calls = []

    class Provider:
        async def fetch_counterparty(self, identifier, *, filters, request_id=None):
            calls.append(("counterparty", identifier, filters, request_id))
            return _result()

        async def fetch_finance(self, identifier, *, request_id=None):
            calls.append(("finance", identifier, request_id))
            return _result(dataset="finance", endpoint=FINANCE_ENDPOINT, payload={})

        def __getattr__(self, name):
            raise AssertionError(f"forbidden provider method requested: {name}")

    snapshot = await build_company_card_v2_snapshot_v2(
        provider=Provider(),
        report_id=REPORT_ID,
        subject_inn=TARGET_INN,
        target_inn=TARGET_INN,
        writer_profile="company_card_v2_writer_v3",
        report_version="3",
        presentation_contract="company_public_h2_v1",
        rollout_config_generation=7,
        now=NOW,
        request_id="company-report:fixed",
    )

    assert isinstance(snapshot, CompanyCardV2SnapshotV2)
    assert snapshot.snapshot_schema_version == "company_card_v2_snapshot_v2"
    assert snapshot.evidence_version == "evidence_registry_v1"
    assert snapshot.generated_at == NOW
    assert snapshot.narrative_evidence.primary_activity is not None
    assert snapshot.narrative_evidence.primary_activity.label == "Разработка программного обеспечения"
    assert snapshot.arbitration_basis.completion_reasons == ("envelope_gate_closed",)
    assert calls == [
        ("counterparty", TARGET_INN, ("OKVED_BLOCK",), "company-report:fixed:counterparty"),
        ("finance", TARGET_INN, "company-report:fixed:finance"),
    ]
    dumped = snapshot.model_dump(mode="json")
    assert "okveds" not in str(dumped)
    assert "raw_payload" not in str(dumped)
    with pytest.raises(ValidationError):
        snapshot.writer_profile = "h1_legacy_writer_v2"


@pytest.mark.asyncio
async def test_v2_builder_keeps_admitted_counterparty_as_partial_when_finance_fails():
    class Provider:
        async def fetch_counterparty(self, *_args, **_kwargs):
            return _result()

        async def fetch_finance(self, *_args, **_kwargs):
            raise RuntimeError("safe test-only finance failure")

    outcome = await build_company_card_v2_snapshot_v2_outcome(
        provider=Provider(),
        report_id=REPORT_ID,
        subject_inn=TARGET_INN,
        target_inn=TARGET_INN,
        writer_profile="company_card_v2_writer_v3",
        report_version="3",
        presentation_contract="company_public_h2_v1",
        rollout_config_generation=1,
        now=NOW,
    )

    assert outcome.lifecycle_status == "partial"
    assert outcome.snapshot.finance_basis.cells == ()
    assert outcome.snapshot.narrative_evidence.primary_activity is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("opf", "short_name", "expected"),
    [
        (
            "Общества с ограниченной ответственностью",
            'ООО "Тестовый контрагент"',
            "/company/ooo-testovyj-kontragent-7700000000",
        ),
        ("ООО", "ПАО Ромашка", "/company/7700000000-company"),
        ("Неподтверждённая форма", "Тест", "/company/7700000000-company"),
        (None, "Тест", "/company/7700000000-company"),
    ],
)
async def test_writer_binds_url_before_legal_form_is_excluded_from_snapshot(opf, short_name, expected):
    payload = _counterparty_payload()
    payload["company"]["company_names"]["short_name"] = short_name
    if opf is not None:
        payload["company"]["opf"] = opf

    class Provider:
        async def fetch_counterparty(self, *_args, **_kwargs):
            return _result(payload=payload)

        async def fetch_finance(self, *_args, **_kwargs):
            raise RuntimeError("safe test-only finance failure")

    outcome = await build_company_card_v2_snapshot_v2_outcome(
        provider=Provider(),
        report_id=REPORT_ID,
        subject_inn=TARGET_INN,
        target_inn=TARGET_INN,
        writer_profile="company_card_v2_writer_v3",
        report_version="3",
        presentation_contract="company_public_h2_v1",
        rollout_config_generation=1,
        now=NOW,
    )
    assert outcome.canonical_url_binding.canonical_path == expected
    assert "opf" not in outcome.snapshot.model_dump(mode="json")


@pytest.mark.asyncio
async def test_v2_builder_does_not_store_a_finance_normalization_error(monkeypatch):
    raw_marker = "PRIVATE-FINANCE-NORMALIZATION-MARKER"

    class Provider:
        async def fetch_counterparty(self, *_args, **_kwargs):
            return _result()

        async def fetch_finance(self, *_args, **_kwargs):
            return _result(dataset="finance", endpoint=FINANCE_ENDPOINT, payload={})

    def fail_normalization(_result):
        raise RuntimeError(raw_marker)

    monkeypatch.setattr(writer_module, "normalize_finance", fail_normalization)
    outcome = await build_company_card_v2_snapshot_v2_outcome(
        provider=Provider(),
        report_id=REPORT_ID,
        subject_inn=TARGET_INN,
        target_inn=TARGET_INN,
        writer_profile="company_card_v2_writer_v3",
        report_version="3",
        presentation_contract="company_public_h2_v1",
        rollout_config_generation=1,
        now=NOW,
    )

    assert outcome.lifecycle_status == "partial"
    assert raw_marker not in repr(outcome.snapshot)
    assert raw_marker not in str(outcome.snapshot.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_v2_builder_rejects_unbound_counterparty_without_finance_call():
    finance_called = False

    class Provider:
        async def fetch_counterparty(self, *_args, **_kwargs):
            return _result(parameters={"inn": TARGET_INN, "filters": "CONTACT_BLOCK"})

        async def fetch_finance(self, *_args, **_kwargs):
            nonlocal finance_called
            finance_called = True
            raise AssertionError("unbound counterparty must stop before finance")

    with pytest.raises(CompanyCardV2BuilderError, match="counterparty result"):
        await build_company_card_v2_snapshot_v2(
            provider=Provider(),
            report_id=REPORT_ID,
            subject_inn=TARGET_INN,
            target_inn=TARGET_INN,
            writer_profile="company_card_v2_writer_v3",
            report_version="3",
            presentation_contract="company_public_h2_v1",
            rollout_config_generation=1,
            now=NOW,
        )
    assert finance_called is False


@pytest.mark.asyncio
async def test_v2_builder_uses_explicit_utc_clock_only():
    class Provider:
        async def fetch_counterparty(self, *_args, **_kwargs):
            raise AssertionError("invalid clock must reject before provider")

        async def fetch_finance(self, *_args, **_kwargs):
            raise AssertionError("invalid clock must reject before provider")

    with pytest.raises(CompanyCardV2BuilderError, match="clock must be UTC"):
        await build_company_card_v2_snapshot_v2(
            provider=Provider(),
            report_id=REPORT_ID,
            subject_inn=TARGET_INN,
            target_inn=TARGET_INN,
            writer_profile="company_card_v2_writer_v3",
            report_version="3",
            presentation_contract="company_public_h2_v1",
            rollout_config_generation=1,
            now=datetime(2026, 8, 25, 12, 0),
        )
