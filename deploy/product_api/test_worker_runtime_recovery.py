"""Contracts for the shared production/rehearsal worker recovery helper."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "deploy/product_api/worker_runtime_recovery.py"
SPEC = importlib.util.spec_from_file_location("worker_runtime_recovery", MODULE)
assert SPEC and SPEC.loader
recovery = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = recovery
SPEC.loader.exec_module(recovery)


PRIOR_SHA = "1" * 40
CANDIDATE_SHA = "2" * 40
IMAGE_ID = f"sha256:{'a' * 64}"
PROJECT = "rehearsal_product"
REPORT_BEFORE = "b" * 64
NARRATIVE_BEFORE = "c" * 64
REPORT_AFTER = "d" * 64
NARRATIVE_AFTER = "e" * 64


def _inspection(
    container_id: str,
    *,
    service: str,
    running: bool,
    restart: str,
    config_image: str,
) -> str:
    return json.dumps([{
        "Id": container_id,
        "Image": IMAGE_ID,
        "State": {"Running": running},
        "Config": {
            "Image": config_image,
            "Env": [f"PRODUCT_RELEASE_COMMIT={PRIOR_SHA}"],
            "Labels": {
                "com.docker.compose.project": PROJECT,
                "com.docker.compose.service": service,
            },
        },
        "HostConfig": {"RestartPolicy": {"Name": restart}},
        "Mounts": [],
    }])


def test_recovery_recreates_both_exact_workers_with_release_bound_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compose = tmp_path / "docker-compose.product.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    environment_file = tmp_path / ".env.product"
    environment_file.write_text(
        "CLAIMS_UPLOAD_ROOT=/tmp/claims\nCLAIMS_UPLOAD_DIR=/data/claims_uploads\n",
        encoding="utf-8",
    )
    recreated = False
    calls: list[tuple[str, ...]] = []

    def run(arguments, *, environment=None, cwd=None, timeout=90):
        nonlocal recreated
        command = tuple(arguments)
        calls.append(command)
        if command[:2] == ("docker", "compose"):
            if "up" in command:
                recreated = True
                assert environment["PRODUCT_IMAGE_TAG"] == PRIOR_SHA
                assert environment["PRODUCT_RELEASE_COMMIT"] == PRIOR_SHA
                assert cwd == tmp_path
                return ""
            service = command[-1]
            if command[-4:-1] == ("ps", "--all", "--quiet"):
                return {
                    "company_report_worker": REPORT_BEFORE,
                    "company_card_narrative_worker": NARRATIVE_BEFORE,
                }[service]
            if command[-2] == "--quiet" and command[-3] == "ps":
                assert recreated
                return {
                    "company_report_worker": REPORT_AFTER,
                    "company_card_narrative_worker": NARRATIVE_AFTER,
                }[service]
        if command == ("docker", "inspect", REPORT_BEFORE):
            return _inspection(
                REPORT_BEFORE,
                service="company_report_worker",
                running=False,
                restart="no",
                config_image=f"b2b-product-api:{PRIOR_SHA}",
            )
        if command == ("docker", "inspect", NARRATIVE_BEFORE):
            return _inspection(
                NARRATIVE_BEFORE,
                service="company_card_narrative_worker",
                running=False,
                restart="no",
                config_image=f"b2b-product-api:{PRIOR_SHA}",
            )
        if command == ("docker", "inspect", REPORT_AFTER):
            return _inspection(
                REPORT_AFTER,
                service="company_report_worker",
                running=True,
                restart="unless-stopped",
                config_image=f"b2b-product-api:{PRIOR_SHA}",
            )
        if command == ("docker", "inspect", NARRATIVE_AFTER):
            return _inspection(
                NARRATIVE_AFTER,
                service="company_card_narrative_worker",
                running=True,
                restart="unless-stopped",
                config_image=f"b2b-product-api:{PRIOR_SHA}",
            )
        if command in {
            (
                "docker", "image", "inspect", "--format", "{{.Id}}",
                f"b2b-product-api:rollback-{CANDIDATE_SHA}",
            ),
            (
                "docker", "image", "inspect", "--format", "{{.Id}}",
                f"b2b-product-api:{PRIOR_SHA}",
            ),
        }:
            return IMAGE_ID
        if command == (
            "docker", "tag", f"b2b-product-api:rollback-{CANDIDATE_SHA}",
            f"b2b-product-api:{PRIOR_SHA}",
        ):
            return ""
        if command[:2] == ("docker", "exec"):
            assert command[2] in {REPORT_AFTER, NARRATIVE_AFTER}
            assert command[3:5] == ("python", "-c")
            assert "SELECT 1" in command[5]
            return ""
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(recovery, "_run", run)
    result = recovery.recover_workers(
        prior_release_sha=PRIOR_SHA,
        expected_image_id=IMAGE_ID,
        rollback_tag=f"b2b-product-api:rollback-{CANDIDATE_SHA}",
        compose_project=PROJECT,
        compose_file=compose,
        environment_file=environment_file,
    )

    assert result["outcome"] == "recovered"
    assert result["prior_report_worker_container"] == REPORT_BEFORE
    assert result["new_report_worker_container"] == REPORT_AFTER
    assert result["prior_narrative_worker_container"] == NARRATIVE_BEFORE
    assert result["new_narrative_worker_container"] == NARRATIVE_AFTER
    assert any("up" in command for command in calls)
    assert {
        command[2]
        for command in calls
        if command[:2] == ("docker", "exec")
    } == {REPORT_AFTER, NARRATIVE_AFTER}


def test_recovery_rejects_non_sha_bound_rollback_tag_before_docker_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compose = tmp_path / "docker-compose.product.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    environment_file = tmp_path / ".env.product"
    environment_file.write_text("synthetic=true\n", encoding="utf-8")
    monkeypatch.setattr(
        recovery,
        "_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("invalid rollback tag accessed Docker")
        ),
    )

    with pytest.raises(recovery.WorkerRecoveryError, match="identity is invalid"):
        recovery.recover_workers(
            prior_release_sha=PRIOR_SHA,
            expected_image_id=IMAGE_ID,
            rollback_tag="b2b-product-api:latest",
            compose_project=PROJECT,
            compose_file=compose,
            environment_file=environment_file,
        )


def test_compose_keeps_exact_override_order_for_disposable_rehearsal(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "docker-compose.product.yml"
    override = tmp_path / "docker-compose.product.rehearsal.yml"
    environment_file = tmp_path / ".env.product"

    command = recovery._compose(
        project=PROJECT,
        compose_file=canonical,
        compose_override_files=(override,),
        environment_file=environment_file,
        tail=("ps", "--all", "--quiet", "company_report_worker"),
    )

    assert command == (
        "docker", "compose", "-p", PROJECT,
        "--profile", "company-card-narrative",
        "-f", str(canonical),
        "-f", str(override),
        "--env-file", str(environment_file),
        "ps", "--all", "--quiet", "company_report_worker",
    )
