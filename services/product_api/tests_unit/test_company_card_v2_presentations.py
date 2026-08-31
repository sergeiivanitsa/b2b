from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from product_api.company_reports.company_card_v2.service import h2_cohort_selected
from product_api.company_reports.company_card_v2.models import (
    CompanyCardV2SnapshotV1,
    CompanyCardV2SnapshotV2,
    CompanyCardV2SnapshotV3,
)
from product_api.company_reports.persistence.presentations import (
    H2_PRESENTATION_CONTRACT,
    H2_PUBLICATION_POLICY_V1,
    H2_PUBLICATION_POLICY_V2,
    H2_PUBLICATION_POLICY_V3,
    PresentationAssignmentConflict,
    _has_exact_artifact_binding,
    _validate_h2_snapshot_policy,
    append_presentation_pin,
)
from product_api.company_reports.persistence.errors import CompanyReportSnapshotError
from product_api.company_reports.persistence.v3 import company_card_v2_from_snapshot


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


def _unresolved_h2_pin_case():
    subject_id = uuid4()
    report = SimpleNamespace(
        id=uuid4(),
        subject_id=subject_id,
        snapshot_hash="a" * 64,
    )
    pin = SimpleNamespace(
        subject_id=subject_id,
        report_id=report.id,
        snapshot_hash=report.snapshot_hash,
        presentation_contract=H2_PRESENTATION_CONTRACT,
        generation=1,
        publication_policy_version=H2_PUBLICATION_POLICY_V3,
        projection_scope="staged_publication",
        canonical_path="/company/ooo-test-7700000000",
        published_lastmod=None,
        indexable=False,
        chart_facts_version="company_card_v2_chart_facts_v1",
        chart_facts_hash="b" * 64,
        evidence_registry_version="company_card_v2_evidence_v2",
        projection_digest=None,
        narrative_binding_status="unresolved",
        narrative_binding_kind=None,
        narrative_binding_key=None,
    )
    kwargs = {
        "subject_id": subject_id,
        "report": report,
        "contract": H2_PRESENTATION_CONTRACT,
        "generation": 1,
        "publication_policy_version": H2_PUBLICATION_POLICY_V3,
        "chart_facts_version": pin.chart_facts_version,
        "chart_facts_hash": pin.chart_facts_hash,
        "evidence_registry_version": pin.evidence_registry_version,
        "canonical_path": pin.canonical_path,
    }
    return pin, kwargs


@pytest.mark.asyncio
async def test_append_h2_unresolved_pin_exact_replay_is_read_only() -> None:
    pin, kwargs = _unresolved_h2_pin_case()
    session = SimpleNamespace(scalar=AsyncMock(return_value=pin))

    result = await append_presentation_pin(session, **kwargs)

    assert result is pin
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "mutated_value"),
    (
        ("projection_digest", "c" * 64),
        ("narrative_binding_status", "resolved"),
        ("narrative_binding_kind", "artifact"),
        ("narrative_binding_key", "d" * 64),
        ("canonical_path", "/company/ao-other-7700000000"),
    ),
)
async def test_append_h2_unresolved_pin_rejects_mutated_binding_shape(
    field: str,
    mutated_value: str,
) -> None:
    pin, kwargs = _unresolved_h2_pin_case()
    setattr(pin, field, mutated_value)
    session = SimpleNamespace(scalar=AsyncMock(return_value=pin))

    with pytest.raises(
        PresentationAssignmentConflict,
        match="presentation pin generation conflicts",
    ):
        await append_presentation_pin(session, **kwargs)


def _policy_matrix_report(*, arbitration_enabled: bool):
    return SimpleNamespace(
        writer_profile="company_card_v2_writer_v3",
        report_version="3",
        presentation_contract=H2_PRESENTATION_CONTRACT,
        rollout_generation=24,
        arbitration_collection_enabled=arbitration_enabled,
        arbitration_mask_key_id=("mask_2026_08" if arbitration_enabled else None),
    )


def _policy_matrix_snapshot(snapshot_type):
    if snapshot_type is CompanyCardV2SnapshotV3:
        return snapshot_type.model_construct(
            arbitration_basis=SimpleNamespace(mask_key_id="mask_2026_08")
        )
    return snapshot_type.model_construct()


@pytest.mark.parametrize(
    ("snapshot_type", "policy"),
    (
        (CompanyCardV2SnapshotV1, H2_PUBLICATION_POLICY_V2),
        (CompanyCardV2SnapshotV1, H2_PUBLICATION_POLICY_V3),
        (CompanyCardV2SnapshotV2, H2_PUBLICATION_POLICY_V3),
        (CompanyCardV2SnapshotV3, H2_PUBLICATION_POLICY_V1),
        (CompanyCardV2SnapshotV3, H2_PUBLICATION_POLICY_V2),
    ),
)
def test_h2_snapshot_policy_cross_pairs_fail_closed(snapshot_type, policy) -> None:
    snapshot = _policy_matrix_snapshot(snapshot_type)
    report = _policy_matrix_report(
        arbitration_enabled=snapshot_type is CompanyCardV2SnapshotV3
    )

    with pytest.raises(
        PresentationAssignmentConflict,
        match="H2 snapshot/policy decision is invalid",
    ):
        _validate_h2_snapshot_policy(report, snapshot, policy)


@pytest.mark.parametrize(
    ("snapshot_type", "policy", "arbitration_enabled"),
    (
        (CompanyCardV2SnapshotV1, H2_PUBLICATION_POLICY_V1, False),
        (CompanyCardV2SnapshotV2, H2_PUBLICATION_POLICY_V1, False),
        (CompanyCardV2SnapshotV2, H2_PUBLICATION_POLICY_V2, False),
        (CompanyCardV2SnapshotV3, H2_PUBLICATION_POLICY_V3, True),
    ),
)
def test_h2_snapshot_policy_accepts_only_the_four_historical_pairs(
    snapshot_type,
    policy,
    arbitration_enabled,
) -> None:
    _validate_h2_snapshot_policy(
        _policy_matrix_report(arbitration_enabled=arbitration_enabled),
        _policy_matrix_snapshot(snapshot_type),
        policy,
    )


def test_h2_v3_policy_rejects_effective_key_mismatch() -> None:
    snapshot = CompanyCardV2SnapshotV3.model_construct(
        arbitration_basis=SimpleNamespace(mask_key_id="mask_2027_01")
    )

    with pytest.raises(
        PresentationAssignmentConflict,
        match="H2 snapshot/policy decision is invalid",
    ):
        _validate_h2_snapshot_policy(
            _policy_matrix_report(arbitration_enabled=True),
            snapshot,
            H2_PUBLICATION_POLICY_V3,
        )


def _iteration24_snapshot_wire() -> dict[str, object]:
    path = (
        Path(__file__).parent
        / "fixtures"
        / "company_card_v2"
        / "snapshot_v3_arbitration_v3.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("role", ("other", "unattributed"))
@pytest.mark.parametrize("invalid_fact", ("outcome", "opponent"))
def test_v3_snapshot_wire_rejects_nonparty_role_derived_facts(
    role: str,
    invalid_fact: str,
) -> None:
    snapshot = _iteration24_snapshot_wire()
    case = snapshot["arbitration_basis"]["sanitized_cases"][0]
    case["role"] = role
    if invalid_fact == "outcome":
        case["outcome"] = "won"
        case["opponent_tokens"] = []
    else:
        case["outcome"] = "unknown"

    with pytest.raises(
        CompanyReportSnapshotError,
        match="company card v2 snapshot is invalid",
    ) as error:
        company_card_v2_from_snapshot(snapshot)
    assert "non-party arbitration role" in str(error.value.__cause__)


@pytest.mark.asyncio
async def test_h2_pin_rejects_serialized_nonparty_role_derived_facts() -> None:
    snapshot = _iteration24_snapshot_wire()
    case = snapshot["arbitration_basis"]["sanitized_cases"][0]
    case["role"] = "other"
    case["outcome"] = "won"
    case["opponent_tokens"] = []
    subject_id = uuid4()
    report = SimpleNamespace(
        id=UUID(snapshot["report_id"]),
        subject_id=subject_id,
        snapshot_hash="a" * 64,
        writer_profile="company_card_v2_writer_v3",
        report_version="3",
        presentation_contract=H2_PRESENTATION_CONTRACT,
        rollout_generation=snapshot["rollout_config_generation"],
        arbitration_collection_enabled=True,
        arbitration_mask_key_id="active_2026",
        normalized_snapshot=deepcopy(snapshot),
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=None))

    with pytest.raises(
        PresentationAssignmentConflict,
        match="H2 pin snapshot is invalid",
    ):
        await append_presentation_pin(
            session,
            subject_id=subject_id,
            report=report,
            contract=H2_PRESENTATION_CONTRACT,
            generation=1,
            publication_policy_version=H2_PUBLICATION_POLICY_V3,
            chart_facts_version=snapshot["chart_facts"]["version"],
            chart_facts_hash=snapshot["chart_facts"]["hash"],
            evidence_registry_version=snapshot["evidence_version"],
        )
