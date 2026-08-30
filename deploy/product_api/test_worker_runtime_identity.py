"""Contracts for the shared read-only Product worker runtime proof."""
from __future__ import annotations

from pathlib import Path

import pytest

from deploy.product_api import worker_runtime_identity as identity


RELEASE_SHA = "1" * 40
IMAGE_ID = f"sha256:{'a' * 64}"
PROJECT = "b2b"
REPORT = "b" * 64
NARRATIVE = "c" * 64


def test_identity_probes_and_reinspects_both_exact_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspections: list[tuple[str, str]] = []
    probes: list[str] = []

    def inspect(container_id: str, **kwargs) -> None:
        inspections.append((kwargs["service"], container_id))
        assert kwargs["project"] == PROJECT
        assert kwargs["release_sha"] == RELEASE_SHA
        assert kwargs["expected_image_id"] == IMAGE_ID
        assert kwargs["expected_config_image"] == f"b2b-product-api:{RELEASE_SHA}"
        assert kwargs["allowed_restart_policies"] == frozenset({"unless-stopped"})
        assert kwargs["require_running"] is True

    monkeypatch.setattr(identity, "_inspect_worker", inspect)
    monkeypatch.setattr(identity, "_probe_worker_database", probes.append)

    result = identity.verify_workers(
        release_sha=RELEASE_SHA,
        expected_image_id=IMAGE_ID,
        compose_project=PROJECT,
        report_container=REPORT,
        narrative_container=NARRATIVE,
    )

    assert inspections == [
        ("company_report_worker", REPORT),
        ("company_report_worker", REPORT),
        ("company_card_narrative_worker", NARRATIVE),
        ("company_card_narrative_worker", NARRATIVE),
    ]
    assert probes == [REPORT, NARRATIVE]
    assert result["outcome"] == "verified"


def test_identity_rejects_duplicate_workers_before_runtime_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        identity,
        "_inspect_worker",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("invalid identity accessed runtime")
        ),
    )

    with pytest.raises(identity.WorkerRecoveryError, match="identity is invalid"):
        identity.verify_workers(
            release_sha=RELEASE_SHA,
            expected_image_id=IMAGE_ID,
            compose_project=PROJECT,
            report_container=REPORT,
            narrative_container=REPORT,
        )


def test_production_workflow_stages_and_invokes_shared_worker_identity() -> None:
    workflow = (
        Path(__file__).resolve().parents[2] / ".github/workflows/deploy_prod.yml"
    ).read_text(encoding="utf-8")
    assert "deploy/product_api/worker_runtime_identity.py" in workflow
    assert workflow.count("worker_runtime_identity.py") >= 3
    assert "candidate-worker-runtime.json" in workflow
    assert "rollback-worker-runtime.json" in workflow
