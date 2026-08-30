"""Executable contracts for the shared read-only Gateway identity proof."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "deploy/us/gateway_runtime_identity.py"
SPEC = importlib.util.spec_from_file_location("gateway_runtime_identity", MODULE)
assert SPEC and SPEC.loader
identity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = identity
SPEC.loader.exec_module(identity)


OLD_SHA = "1" * 40
CANDIDATE_SHA = "2" * 40
CONTAINER_ID = "a" * 64
IMAGE_ID = f"sha256:{'b' * 64}"


def _runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    release_sha: str,
    topology: str,
) -> tuple[Path, Path]:
    release_root = tmp_path / "releases"
    release_root.mkdir()
    stage_name = (
        f"{release_sha}-fresh-install" if topology == "fresh-install" else release_sha
    )
    stage = release_root / stage_name
    stage.mkdir()
    compose = stage / "docker-compose.gateway.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    environment_file = tmp_path / ".env.gateway"
    environment_file.write_text("GATEWAY_SHARED_SECRET=synthetic\n", encoding="utf-8")
    inspected = [{
        "Id": CONTAINER_ID,
        "Image": IMAGE_ID,
        "State": {"Running": True},
        "Config": {
            "Image": f"b2b-gateway-api:{release_sha}",
            "Env": [f"GATEWAY_RELEASE_COMMIT={release_sha}"],
            "Labels": {
                "com.docker.compose.service": "gateway_api",
                "com.docker.compose.project": "rehearsal_gateway",
                "com.docker.compose.project.config_files": str(compose),
                "com.docker.compose.project.working_dir": str(stage),
                "com.docker.compose.project.environment_file": str(environment_file),
            },
        },
        "HostConfig": {"RestartPolicy": {"Name": "unless-stopped"}},
        "NetworkSettings": {
            "Ports": {"8001/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8001"}]}
        },
    }]

    def run(arguments):
        command = tuple(arguments)
        if command[:4] == ("docker", "ps", "-aq", "--no-trunc"):
            return CONTAINER_ID
        if command == ("docker", "inspect", CONTAINER_ID):
            return json.dumps(inspected)
        if command == (
            "docker", "image", "inspect", "--format", "{{.Id}}",
            f"b2b-gateway-api:{release_sha}",
        ):
            return IMAGE_ID
        raise AssertionError(f"unexpected Docker command: {command!r}")

    monkeypatch.setattr(identity, "_run", run)
    monkeypatch.setattr(identity, "_health", lambda url: None)
    return release_root, environment_file


@pytest.mark.parametrize("topology", ["fresh-install", "normal"])
def test_prior_identity_accepts_only_approved_old_topologies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: str,
) -> None:
    release_root, environment_file = _runtime(
        tmp_path, monkeypatch, release_sha=OLD_SHA, topology=topology
    )

    result = identity.inspect_gateway(
        release_root=release_root,
        candidate_release_sha=CANDIDATE_SHA,
        expected_release_sha=None,
        environment_file=environment_file,
        expected_loopback="127.0.0.1:8001",
        health_url="http://127.0.0.1:8001/health",
    )

    assert result == {
        "identity_mode": "prior",
        "requested_release_sha": CANDIDATE_SHA,
        "container_id": CONTAINER_ID,
        "current_image_id": IMAGE_ID,
        "current_release_sha": OLD_SHA,
        "environment_file": str(environment_file),
        "project": "rehearsal_gateway",
        "schema_version": "gateway_runtime_identity_v1",
        "topology": topology,
    }


def test_deployed_identity_requires_expected_normal_topology(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root, environment_file = _runtime(
        tmp_path, monkeypatch, release_sha=CANDIDATE_SHA, topology="normal"
    )

    result = identity.inspect_gateway(
        release_root=release_root,
        candidate_release_sha=None,
        expected_release_sha=CANDIDATE_SHA,
        environment_file=environment_file,
        expected_loopback="127.0.0.1:8001",
        health_url="http://127.0.0.1:8001/health",
    )

    assert result["identity_mode"] == "deployed"
    assert result["current_release_sha"] == CANDIDATE_SHA
    assert result["topology"] == "normal"


def test_deployed_identity_rejects_expected_release_on_fresh_install_topology(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root, environment_file = _runtime(
        tmp_path, monkeypatch, release_sha=CANDIDATE_SHA, topology="fresh-install"
    )

    with pytest.raises(identity.GatewayIdentityError, match="normal release topology"):
        identity.inspect_gateway(
            release_root=release_root,
            candidate_release_sha=None,
            expected_release_sha=CANDIDATE_SHA,
            environment_file=environment_file,
            expected_loopback="127.0.0.1:8001",
            health_url="http://127.0.0.1:8001/health",
        )


def test_prior_identity_rejects_existing_candidate_stage_before_docker_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root, environment_file = _runtime(
        tmp_path, monkeypatch, release_sha=OLD_SHA, topology="normal"
    )
    (release_root / CANDIDATE_SHA).mkdir()
    monkeypatch.setattr(
        identity,
        "_run",
        lambda arguments: (_ for _ in ()).throw(
            AssertionError("candidate-stage rejection accessed Docker")
        ),
    )

    with pytest.raises(identity.GatewayIdentityError, match="already exists"):
        identity.inspect_gateway(
            release_root=release_root,
            candidate_release_sha=CANDIDATE_SHA,
            expected_release_sha=None,
            environment_file=environment_file,
            expected_loopback="127.0.0.1:8001",
            health_url="http://127.0.0.1:8001/health",
        )


def test_identity_rejects_health_url_for_another_loopback_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root, environment_file = _runtime(
        tmp_path, monkeypatch, release_sha=OLD_SHA, topology="normal"
    )

    with pytest.raises(identity.GatewayIdentityError, match="not bound"):
        identity.inspect_gateway(
            release_root=release_root,
            candidate_release_sha=CANDIDATE_SHA,
            expected_release_sha=None,
            environment_file=environment_file,
            expected_loopback="127.0.0.1:8001",
            health_url="http://127.0.0.1:8999/health",
        )
