#!/usr/bin/env python3
"""Read-only closed identity proof for the sole deployed Gateway runtime.

The same program is used by disposable deploy rehearsal and production
preflight.  It never starts, stops, tags, removes, or recreates a container.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence
from urllib.request import ProxyHandler, Request, build_opener


_SHA = re.compile(r"^[0-9a-f]{40}$")
_IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTAINER = re.compile(r"^[0-9a-f]{64}$")
_PROJECT = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class GatewayIdentityError(RuntimeError):
    pass


def _run(arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        list(arguments),
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if completed.returncode != 0:
        raise GatewayIdentityError("Docker identity command failed; STOP")
    return completed.stdout.strip()


def _absolute_existing_directory(value: str, *, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise GatewayIdentityError(f"{label} is not an exact directory; STOP")
    try:
        if path.resolve(strict=True) != path:
            raise GatewayIdentityError(f"{label} is not canonical; STOP")
    except OSError as exc:
        raise GatewayIdentityError(f"{label} cannot be resolved; STOP") from exc
    return path


def _absolute_existing_file(value: str, *, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise GatewayIdentityError(f"{label} is not an exact file; STOP")
    try:
        if path.resolve(strict=True) != path:
            raise GatewayIdentityError(f"{label} is not canonical; STOP")
    except OSError as exc:
        raise GatewayIdentityError(f"{label} cannot be resolved; STOP") from exc
    return path


def _one_release(environment: object) -> str:
    if not isinstance(environment, list) or any(not isinstance(row, str) for row in environment):
        raise GatewayIdentityError("Gateway environment is invalid; STOP")
    releases = [row.removeprefix("GATEWAY_RELEASE_COMMIT=") for row in environment if row.startswith("GATEWAY_RELEASE_COMMIT=")]
    if len(releases) != 1 or _SHA.fullmatch(releases[0]) is None:
        raise GatewayIdentityError("Gateway release identity cardinality is invalid; STOP")
    return releases[0]


def _health(url: str) -> None:
    if not re.fullmatch(r"http://127\.0\.0\.1:[1-9][0-9]{0,4}/health", url):
        raise GatewayIdentityError("Gateway health URL is not exact loopback HTTP; STOP")
    try:
        response = build_opener(ProxyHandler({})).open(
            Request(url, method="GET"),
            timeout=10,
        )
        try:
            if response.status != 200:
                raise GatewayIdentityError("Gateway health response is not 200; STOP")
        finally:
            response.close()
    except GatewayIdentityError:
        raise
    except Exception as exc:
        raise GatewayIdentityError("Gateway health check failed; STOP") from exc


def inspect_gateway(
    *,
    release_root: Path,
    candidate_release_sha: str | None,
    expected_release_sha: str | None,
    environment_file: Path,
    expected_loopback: str,
    health_url: str,
) -> dict[str, object]:
    requested = candidate_release_sha or expected_release_sha or ""
    if (
        (candidate_release_sha is None) == (expected_release_sha is None)
        or _SHA.fullmatch(requested) is None
    ):
        raise GatewayIdentityError("Exactly one requested release SHA is required; STOP")
    if not re.fullmatch(r"127\.0\.0\.1:[1-9][0-9]{0,4}", expected_loopback):
        raise GatewayIdentityError("Expected Gateway loopback is invalid; STOP")
    if health_url != f"http://{expected_loopback}/health":
        raise GatewayIdentityError("Gateway health URL is not bound to the expected loopback; STOP")
    candidate_stage = release_root / requested
    if candidate_release_sha is not None and (
        candidate_stage.exists() or candidate_stage.is_symlink()
    ):
        raise GatewayIdentityError("Candidate Gateway stage already exists; STOP")

    rows = [
        row
        for row in _run(
            (
                "docker",
                "ps",
                "-aq",
                "--no-trunc",
                "--filter",
                "label=com.docker.compose.service=gateway_api",
            )
        ).splitlines()
        if row
    ]
    if len(rows) != 1 or _CONTAINER.fullmatch(rows[0]) is None:
        raise GatewayIdentityError("Gateway service cardinality is not exactly one; STOP")
    container_id = rows[0]
    try:
        inspected = json.loads(_run(("docker", "inspect", container_id)))
        if not isinstance(inspected, list) or len(inspected) != 1 or not isinstance(inspected[0], dict):
            raise GatewayIdentityError("Gateway inspect response is invalid; STOP")
        data: dict[str, Any] = inspected[0]
        state = data["State"]
        config = data["Config"]
        host_config = data["HostConfig"]
        network = data["NetworkSettings"]
        labels = config["Labels"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise GatewayIdentityError("Gateway inspect response is invalid; STOP") from exc

    if data.get("Id") != container_id or state.get("Running") is not True:
        raise GatewayIdentityError("Gateway is not the exact running container; STOP")
    release_sha = _one_release(config.get("Env"))
    if candidate_release_sha is not None and release_sha == candidate_release_sha:
        raise GatewayIdentityError("Gateway already runs the candidate release; STOP")
    if expected_release_sha is not None and release_sha != expected_release_sha:
        raise GatewayIdentityError("Gateway does not run the expected release; STOP")

    image_id = data.get("Image")
    config_image = config.get("Image")
    if not isinstance(image_id, str) or _IMAGE.fullmatch(image_id) is None:
        raise GatewayIdentityError("Gateway image identity is invalid; STOP")
    if config_image != f"b2b-gateway-api:{release_sha}":
        raise GatewayIdentityError("Gateway config image is not release-bound; STOP")
    if _run(("docker", "image", "inspect", "--format", "{{.Id}}", config_image)) != image_id:
        raise GatewayIdentityError("Gateway tag/image identity mismatch; STOP")

    if not isinstance(labels, dict) or labels.get("com.docker.compose.service") != "gateway_api":
        raise GatewayIdentityError("Gateway service label mismatch; STOP")
    project = labels.get("com.docker.compose.project")
    if not isinstance(project, str) or _PROJECT.fullmatch(project) is None:
        raise GatewayIdentityError("Gateway Compose project identity is invalid; STOP")
    config_files = labels.get("com.docker.compose.project.config_files")
    working_dir = labels.get("com.docker.compose.project.working_dir")
    labelled_environment_file = labels.get("com.docker.compose.project.environment_file")
    if not all(isinstance(value, str) for value in (config_files, working_dir, labelled_environment_file)):
        raise GatewayIdentityError("Gateway Compose labels are incomplete; STOP")

    fresh_stage = release_root / f"{release_sha}-fresh-install"
    normal_stage = release_root / release_sha
    config_path = _absolute_existing_file(str(config_files), label="Gateway Compose config")
    working_path = _absolute_existing_directory(str(working_dir), label="Gateway Compose working directory")
    if config_path == fresh_stage / "docker-compose.gateway.yml" and working_path == fresh_stage:
        topology = "fresh-install"
    elif config_path == normal_stage / "docker-compose.gateway.yml" and working_path == normal_stage:
        topology = "normal"
    else:
        raise GatewayIdentityError("Gateway Compose graph is outside an approved release stage; STOP")
    if expected_release_sha is not None and topology != "normal":
        raise GatewayIdentityError("Deployed Gateway is not on the normal release topology; STOP")
    if Path(str(labelled_environment_file)) != environment_file:
        raise GatewayIdentityError("Gateway environment-file label mismatch; STOP")

    restart_policy = host_config.get("RestartPolicy", {}).get("Name")
    if restart_policy != "unless-stopped":
        raise GatewayIdentityError("Gateway restart policy mismatch; STOP")
    bindings = network.get("Ports", {}).get("8001/tcp")
    expected_ip, expected_port = expected_loopback.rsplit(":", 1)
    if bindings != [{"HostIp": expected_ip, "HostPort": expected_port}]:
        raise GatewayIdentityError("Gateway loopback binding mismatch; STOP")
    _health(health_url)

    return {
        "identity_mode": "prior" if candidate_release_sha is not None else "deployed",
        "requested_release_sha": requested,
        "container_id": container_id,
        "current_image_id": image_id,
        "current_release_sha": release_sha,
        "environment_file": str(environment_file),
        "project": project,
        "schema_version": "gateway_runtime_identity_v1",
        "topology": topology,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only exact Gateway identity proof")
    parser.add_argument("--release-root", required=True)
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--candidate-release-sha")
    identity.add_argument("--expected-release-sha")
    parser.add_argument("--environment-file", required=True)
    parser.add_argument("--expected-loopback", required=True)
    parser.add_argument("--health-url", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = inspect_gateway(
            release_root=_absolute_existing_directory(args.release_root, label="Gateway release root"),
            candidate_release_sha=args.candidate_release_sha,
            expected_release_sha=args.expected_release_sha,
            environment_file=_absolute_existing_file(args.environment_file, label="Gateway environment file"),
            expected_loopback=args.expected_loopback,
            health_url=args.health_url,
        )
    except (GatewayIdentityError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
