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


def arbitration_provider_allowed(registry: dict[str, EvidenceGate] | None = None) -> bool:
    gate = (registry or ARBITRATION_EVIDENCE_REGISTRY_V1).get("provider_envelope")
    return gate is not None and gate.state == "verified"


__all__ = ["ARBITRATION_EVIDENCE_REGISTRY_V1", "EvidenceGate", "arbitration_provider_allowed"]
