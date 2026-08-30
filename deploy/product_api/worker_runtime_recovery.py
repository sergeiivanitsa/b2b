#!/usr/bin/env python3
"""Restore the two exact Product workers after an armed drain fails.

This helper is intentionally narrower than full Product rollback: it is valid
only before the Product/Alembic phase starts.  Production and the disposable
deploy rehearsal call the same executable path.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


_SHA = re.compile(r"^[0-9a-f]{40}$")
_IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTAINER = re.compile(r"^[0-9a-f]{64}$")
_PROJECT = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_ROLLBACK_TAG = re.compile(r"^b2b-product-api:rollback-[0-9a-f]{40}$")
_SERVICES = ("company_report_worker", "company_card_narrative_worker")
_DATABASE_PROBE = (
    "import asyncio,os,asyncpg\n"
    "async def main():\n"
    " dsn=os.environ['DATABASE_URL'].replace('postgresql+asyncpg://','postgresql://',1)\n"
    " connection=await asyncpg.connect(dsn=dsn,timeout=5)\n"
    " try:\n"
    "  assert await connection.fetchval('SELECT 1') == 1\n"
    " finally:\n"
    "  await connection.close()\n"
    "asyncio.run(main())\n"
)


class WorkerRecoveryError(RuntimeError):
    pass


def _run(
    arguments: Sequence[str],
    *,
    environment: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: int = 90,
) -> str:
    completed = subprocess.run(
        list(arguments),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
        cwd=cwd,
    )
    if completed.returncode != 0:
        raise WorkerRecoveryError("worker recovery command failed; STOP")
    return completed.stdout.strip()


def _exact_file(value: str, *, label: str) -> Path:
    path = Path(value)
    try:
        if (
            not path.is_absolute()
            or path.is_symlink()
            or not path.is_file()
            or path.resolve(strict=True) != path
        ):
            raise WorkerRecoveryError(f"{label} is not an exact canonical file; STOP")
    except OSError as exc:
        raise WorkerRecoveryError(f"{label} cannot be resolved; STOP") from exc
    return path


def _release_rows(environment: object) -> list[str]:
    if not isinstance(environment, list) or any(
        not isinstance(row, str) for row in environment
    ):
        raise WorkerRecoveryError("worker environment response is invalid; STOP")
    return [
        row.removeprefix("PRODUCT_RELEASE_COMMIT=")
        for row in environment
        if row.startswith("PRODUCT_RELEASE_COMMIT=")
    ]


def _inspect_worker(
    container_id: str,
    *,
    service: str,
    project: str,
    release_sha: str,
    expected_image_id: str,
    expected_config_image: str | None,
    allowed_restart_policies: frozenset[str],
    require_running: bool,
) -> dict[str, Any]:
    if _CONTAINER.fullmatch(container_id) is None:
        raise WorkerRecoveryError("worker container identity is invalid; STOP")
    try:
        response = json.loads(_run(("docker", "inspect", container_id)))
        if (
            not isinstance(response, list)
            or len(response) != 1
            or not isinstance(response[0], dict)
        ):
            raise WorkerRecoveryError("worker inspect response is invalid; STOP")
        data: dict[str, Any] = response[0]
        config = data["Config"]
        labels = config["Labels"]
        state = data["State"]
        restart = data["HostConfig"]["RestartPolicy"]["Name"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise WorkerRecoveryError("worker inspect response is invalid; STOP") from exc
    if data.get("Id") != container_id or data.get("Image") != expected_image_id:
        raise WorkerRecoveryError("worker image/container identity mismatch; STOP")
    if expected_config_image is not None and config.get("Image") != expected_config_image:
        raise WorkerRecoveryError("worker config image identity mismatch; STOP")
    releases = _release_rows(config.get("Env"))
    if releases != [release_sha]:
        raise WorkerRecoveryError("worker release identity mismatch; STOP")
    if (
        not isinstance(labels, dict)
        or labels.get("com.docker.compose.service") != service
        or labels.get("com.docker.compose.project") != project
    ):
        raise WorkerRecoveryError("worker Compose identity mismatch; STOP")
    if restart not in allowed_restart_policies:
        raise WorkerRecoveryError("worker restart policy is outside recovery state; STOP")
    if require_running and state.get("Running") is not True:
        raise WorkerRecoveryError("recovered worker is not running; STOP")
    mounts = data.get("Mounts")
    if not isinstance(mounts, list) or any(
        isinstance(mount, dict) and mount.get("Destination") == "/data/claims_uploads"
        for mount in mounts
    ):
        raise WorkerRecoveryError("worker unexpectedly mounts Claims storage; STOP")
    return data


def _probe_worker_database(container_id: str) -> None:
    if _CONTAINER.fullmatch(container_id) is None:
        raise WorkerRecoveryError("worker database probe identity is invalid; STOP")
    _run(("docker", "exec", container_id, "python", "-c", _DATABASE_PROBE), timeout=20)


def _compose(
    *,
    project: str,
    compose_file: Path,
    compose_override_files: Sequence[Path],
    environment_file: Path,
    tail: Sequence[str],
) -> tuple[str, ...]:
    compose_arguments = tuple(
        argument
        for path in (compose_file, *compose_override_files)
        for argument in ("-f", str(path))
    )
    return (
        "docker",
        "compose",
        "-p",
        project,
        "--profile",
        "company-card-narrative",
        *compose_arguments,
        "--env-file",
        str(environment_file),
        *tail,
    )


def recover_workers(
    *,
    prior_release_sha: str,
    expected_image_id: str,
    rollback_tag: str,
    compose_project: str,
    compose_file: Path,
    environment_file: Path,
    compose_override_files: Sequence[Path] = (),
) -> dict[str, object]:
    if (
        _SHA.fullmatch(prior_release_sha) is None
        or _IMAGE.fullmatch(expected_image_id) is None
        or _ROLLBACK_TAG.fullmatch(rollback_tag) is None
        or _PROJECT.fullmatch(compose_project) is None
    ):
        raise WorkerRecoveryError("worker recovery identity is invalid; STOP")

    environment = os.environ.copy()
    environment.update(
        {
            "PRODUCT_ENV_FILE": str(environment_file),
            "PRODUCT_IMAGE_TAG": prior_release_sha,
            "PRODUCT_RELEASE_COMMIT": prior_release_sha,
        }
    )
    before: dict[str, str] = {}
    for service in _SERVICES:
        rows = [
            row
            for row in _run(
                _compose(
                    project=compose_project,
                    compose_file=compose_file,
                    compose_override_files=compose_override_files,
                    environment_file=environment_file,
                    tail=("ps", "--all", "--quiet", service),
                ),
                environment=environment,
                cwd=compose_file.parent,
            ).splitlines()
            if row
        ]
        if len(rows) != 1:
            raise WorkerRecoveryError("exact prior worker cardinality is required; STOP")
        before[service] = rows[0]
        _inspect_worker(
            rows[0],
            service=service,
            project=compose_project,
            release_sha=prior_release_sha,
            expected_image_id=expected_image_id,
            expected_config_image=None,
            allowed_restart_policies=frozenset({"no", "unless-stopped"}),
            require_running=False,
        )

    if _run(("docker", "image", "inspect", "--format", "{{.Id}}", rollback_tag)) != expected_image_id:
        raise WorkerRecoveryError("rollback tag/image identity mismatch; STOP")
    release_tag = f"b2b-product-api:{prior_release_sha}"
    _run(("docker", "tag", rollback_tag, release_tag))
    if _run(("docker", "image", "inspect", "--format", "{{.Id}}", release_tag)) != expected_image_id:
        raise WorkerRecoveryError("release tag/image identity mismatch; STOP")

    _run(
        _compose(
            project=compose_project,
            compose_file=compose_file,
            compose_override_files=compose_override_files,
            environment_file=environment_file,
            tail=(
                "up",
                "-d",
                "--no-build",
                "--force-recreate",
                *_SERVICES,
            ),
        ),
        environment=environment,
        cwd=compose_file.parent,
    )

    after: dict[str, str] = {}
    for service in _SERVICES:
        rows = [
            row
            for row in _run(
                _compose(
                    project=compose_project,
                    compose_file=compose_file,
                    compose_override_files=compose_override_files,
                    environment_file=environment_file,
                    tail=("ps", "--quiet", service),
                ),
                environment=environment,
                cwd=compose_file.parent,
            ).splitlines()
            if row
        ]
        if len(rows) != 1 or rows[0] == before[service]:
            raise WorkerRecoveryError("worker was not exactly recreated; STOP")
        after[service] = rows[0]
        _inspect_worker(
            rows[0],
            service=service,
            project=compose_project,
            release_sha=prior_release_sha,
            expected_image_id=expected_image_id,
            expected_config_image=release_tag,
            allowed_restart_policies=frozenset({"unless-stopped"}),
            require_running=True,
        )
        _probe_worker_database(rows[0])
        _inspect_worker(
            rows[0],
            service=service,
            project=compose_project,
            release_sha=prior_release_sha,
            expected_image_id=expected_image_id,
            expected_config_image=release_tag,
            allowed_restart_policies=frozenset({"unless-stopped"}),
            require_running=True,
        )

    return {
        "compose_project": compose_project,
        "expected_image_id": expected_image_id,
        "new_narrative_worker_container": after["company_card_narrative_worker"],
        "new_report_worker_container": after["company_report_worker"],
        "outcome": "recovered",
        "prior_narrative_worker_container": before["company_card_narrative_worker"],
        "prior_release_sha": prior_release_sha,
        "prior_report_worker_container": before["company_report_worker"],
        "schema_version": "worker_runtime_recovery_v1",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore exact workers after failed drain")
    parser.add_argument("--prior-release-sha", required=True)
    parser.add_argument("--expected-image-id", required=True)
    parser.add_argument("--rollback-tag", required=True)
    parser.add_argument("--compose-project", required=True)
    parser.add_argument("--compose-file", required=True)
    parser.add_argument("--compose-override-file", action="append", default=[])
    parser.add_argument("--environment-file", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = recover_workers(
            prior_release_sha=args.prior_release_sha,
            expected_image_id=args.expected_image_id,
            rollback_tag=args.rollback_tag,
            compose_project=args.compose_project,
            compose_file=_exact_file(args.compose_file, label="Product Compose file"),
            compose_override_files=tuple(
                _exact_file(path, label="Product Compose override file")
                for path in args.compose_override_file
            ),
            environment_file=_exact_file(args.environment_file, label="Product environment file"),
        )
    except (WorkerRecoveryError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
