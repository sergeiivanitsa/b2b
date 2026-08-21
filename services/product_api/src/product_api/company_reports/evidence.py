"""Immutable, reviewable evidence gates for the public H1 projection."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


EvidenceState = Literal["enabled", "read_existing_only", "enabled_without_unit", "disabled"]


@dataclass(frozen=True)
class EvidenceGate:
    gate_id: str
    registry_version: Literal["evidence_registry_v1"]
    schema_state: str
    operational_state: EvidenceState
    evidence_paths: tuple[str, ...]
    public_behavior: str


EVIDENCE_REGISTRY: tuple[EvidenceGate, ...] = (
    EvidenceGate("counterparty_core", "evidence_registry_v1", "verified", "enabled", ("services/product_api/src/product_api/company_reports/normalizers/counterparty.py", "services/product_api/tests_unit/fixtures/datanewton/counterparty_success.json"), "normalized_core_only"),
    EvidenceGate("counterparty_address", "evidence_registry_v1", "verified", "read_existing_only", ("services/product_api/src/product_api/company_reports/normalizers/counterparty.py", "services/product_api/tests_unit/fixtures/datanewton/counterparty_success.json"), "stored_available_only"),
    EvidenceGate("finance_series", "evidence_registry_v1", "verified", "enabled_without_unit", ("services/product_api/src/product_api/company_reports/normalizers/finance.py", "services/product_api/tests_unit/fixtures/datanewton/finance_success.json"), "yoy_only"),
    EvidenceGate("finance_unit", "evidence_registry_v1", "unverified", "disabled", (), "money_null"),
    EvidenceGate("arbitration_parties", "evidence_registry_v1", "verified", "enabled", ("services/product_api/src/product_api/company_reports/normalizers/arbitration.py", "services/product_api/tests_unit/fixtures/datanewton/arbitration_success.json"), "typed_identity_only"),
    EvidenceGate("tax", "evidence_registry_v1", "unverified", "disabled", (), "not_requested"),
    EvidenceGate("bankruptcy", "evidence_registry_v1", "unverified", "disabled", (), "not_requested"),
    EvidenceGate("management_privacy", "evidence_registry_v1", "unverified", "disabled", (), "hidden"),
    EvidenceGate("owners", "evidence_registry_v1", "unverified", "disabled", (), "hidden"),
    EvidenceGate("contacts", "evidence_registry_v1", "prohibited", "disabled", (), "hidden"),
    EvidenceGate("fssp", "evidence_registry_v1", "unverified", "disabled", (), "hidden"),
)

EVIDENCE_BY_ID = {gate.gate_id: gate for gate in EVIDENCE_REGISTRY}


def validate_evidence_registry(repository_root: Path) -> None:
    """Validate only tracked local evidence; environment cannot activate gates."""
    for gate in EVIDENCE_REGISTRY:
        if gate.operational_state != "disabled" and not gate.evidence_paths:
            raise ValueError(f"enabled evidence gate has no artifacts: {gate.gate_id}")
        for relative in gate.evidence_paths:
            path = repository_root / relative
            if not path.is_file():
                raise ValueError(f"evidence artifact does not exist: {relative}")
