from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceGate:
    name: str
    state: str
    reason: str


# Deliberately shipped closed. Tests may inject a synthetic verified registry;
# runtime code must not treat this registry as a reason to call a provider.
ARBITRATION_EVIDENCE_REGISTRY_V1: dict[str, EvidenceGate] = {
    "provider_envelope": EvidenceGate("provider_envelope", "gate_closed", "unverified_observed_shape"),
}


@dataclass(frozen=True)
class ArbitrationEvidenceBindingV2:
    registry_version: str
    contract_binding: str
    openapi_sha256: str
    runtime_dataset: str
    endpoint: str
    identity_policy: str
    target_policy: str
    collection_policy: str
    state: str


ARBITRATION_EVIDENCE_BINDING_V2 = ArbitrationEvidenceBindingV2(
    registry_version="datanewton_arbitration_registry_v2",
    contract_binding="datanewton_arbitration_openapi_v1_2026_08_26",
    openapi_sha256="2c3d34ab00a35e58e07f7c3dea32b605b9e61d112a92a1654fd54e415ef851d2",
    runtime_dataset="arbitration_cases",
    endpoint="GET /v1/arbitration-cases",
    identity_policy="arbitration_case_identity_case_id_only_v1",
    target_policy="arbitration_target_exact_inn_v1",
    collection_policy="datanewton_arbitration_single_page_1000_v1",
    state="verified",
)


def arbitration_provider_allowed(registry: dict[str, EvidenceGate] | None = None) -> bool:
    gate = (registry or ARBITRATION_EVIDENCE_REGISTRY_V1).get("provider_envelope")
    return gate is not None and gate.state == "verified"


def arbitration_v2_evidence_allowed(binding: object) -> bool:
    """Admit only the immutable, exact V2 evidence tuple.

    The legacy mutable V1 registry above intentionally retains its historical
    fixture semantics.  Runtime V3 generation cannot promote it or a partial
    look-alike to the approved contract.
    """
    return type(binding) is ArbitrationEvidenceBindingV2 and binding == ARBITRATION_EVIDENCE_BINDING_V2


__all__ = [
    "ARBITRATION_EVIDENCE_BINDING_V2",
    "ARBITRATION_EVIDENCE_REGISTRY_V1",
    "ArbitrationEvidenceBindingV2",
    "EvidenceGate",
    "arbitration_provider_allowed",
    "arbitration_v2_evidence_allowed",
]
