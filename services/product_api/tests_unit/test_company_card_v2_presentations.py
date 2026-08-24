from uuid import uuid4

import pytest

from product_api.company_reports.company_card_v2.service import h2_cohort_selected
from types import SimpleNamespace

from product_api.company_reports.persistence.presentations import (
    PresentationAssignmentConflict,
    _has_exact_artifact_binding,
)


def test_h2_cohort_requires_server_side_enabled_valid_configuration() -> None:
    settings = type("Settings", (), {
        "company_card_v2_presentations_enabled": True,
        "company_card_v2_rollout_generation": 1,
        "company_card_v2_allowlist_inns": ["7701234567"],
        "company_card_v2_percentage_basis_points": 0,
    })()
    assert h2_cohort_selected(inn="7701234567", settings=settings)
    assert not h2_cohort_selected(inn="7701234568", settings=settings)


def test_h2_unresolved_assignment_conflict_has_no_public_activation_semantics() -> None:
    error = PresentationAssignmentConflict("unresolved H2 pin is not assignable")
    assert "unresolved" in str(error)
    assert uuid4() != uuid4()


def test_h2_artifact_binding_requires_exact_kind_key_and_exclusive_identity() -> None:
    artifact = SimpleNamespace(
        binding_kind="artifact",
        binding_key="a" * 64,
        artifact_identity="a" * 64,
        fallback_identity=None,
    )
    assert _has_exact_artifact_binding(artifact)

    artifact.binding_key = "b" * 64
    assert not _has_exact_artifact_binding(artifact)
    artifact.binding_key = "a" * 64
    artifact.fallback_identity = "c" * 64
    assert not _has_exact_artifact_binding(artifact)


def test_h2_fallback_binding_requires_exact_lowercase_digest_and_no_artifact_identity() -> None:
    artifact = SimpleNamespace(
        binding_kind="fallback",
        binding_key="b" * 64,
        artifact_identity=None,
        fallback_identity="b" * 64,
    )
    assert _has_exact_artifact_binding(artifact)

    artifact.fallback_identity = "B" * 64
    assert not _has_exact_artifact_binding(artifact)
    artifact.fallback_identity = "b" * 64
    artifact.artifact_identity = "a" * 64
    assert not _has_exact_artifact_binding(artifact)
