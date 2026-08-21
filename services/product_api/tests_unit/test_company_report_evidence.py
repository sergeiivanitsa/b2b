import os
from pathlib import Path

import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from product_api.company_reports.orchestrator import build_company_report
from product_api.company_reports.evidence import EVIDENCE_BY_ID, EVIDENCE_REGISTRY, validate_evidence_registry


def test_evidence_registry_is_unique_and_optional_gates_fail_closed():
    assert len(EVIDENCE_BY_ID) == len(EVIDENCE_REGISTRY)
    for gate_id in ("finance_unit", "tax", "bankruptcy", "management_privacy", "owners", "contacts", "fssp"):
        assert EVIDENCE_BY_ID[gate_id].operational_state == "disabled"


def test_enabled_evidence_paths_are_real_tracked_files_and_env_cannot_activate(monkeypatch):
    root = Path(__file__).parents[3]
    validate_evidence_registry(root)
    for gate in EVIDENCE_REGISTRY:
        for relative in gate.evidence_paths:
            assert (root / relative).is_file()
    before = tuple(EVIDENCE_REGISTRY)
    monkeypatch.setenv("COMPANY_REPORT_ENABLE_TAX", "1")
    monkeypatch.setenv("COMPANY_REPORT_ENABLE_FINANCE_UNIT", "1")
    assert tuple(EVIDENCE_REGISTRY) == before
    assert EVIDENCE_BY_ID["tax"].operational_state == "disabled"


@pytest.mark.asyncio
async def test_optional_provider_methods_are_never_called():
    provider = successful_fake_provider()

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("optional provider method must not be called")

    provider.fetch_tax_info = forbidden
    provider.fetch_bankruptcy = forbidden
    provider.fetch_fssp = forbidden
    provider.fetch_batch_cards = forbidden
    report = await build_company_report("0000000000", provider=provider)
    assert report.optional_datasets == {}
    assert report.tax_info is None and report.bankruptcy is None
