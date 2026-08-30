#!/usr/bin/env python3
"""Disposable fresh-install-to-normal-deploy control-plane rehearsal.

The rehearsal consumes the exact build-once Product/Gateway images.  It uses a
real migrated PostgreSQL database, injects a deterministic failure after worker
mutation, invokes the same worker recovery helper as production, and moves a
Gateway from a fresh-install Compose stage to a normal release stage.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Sequence
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_DRAIN = REPO_ROOT / "deploy/product_api/worker_drain.py"
WORKER_RECOVERY = REPO_ROOT / "deploy/product_api/worker_runtime_recovery.py"
WORKER_IDENTITY = REPO_ROOT / "deploy/product_api/worker_runtime_identity.py"
GATEWAY_IDENTITY = REPO_ROOT / "deploy/us/gateway_runtime_identity.py"
PRODUCT_COMPOSE = REPO_ROOT / "docker-compose.product.yml"
GATEWAY_COMPOSE = REPO_ROOT / "deploy/us/compose/docker-compose.gateway.yml"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTAINER = re.compile(r"^[0-9a-f]{64}$")


class RehearsalError(RuntimeError):
    pass


def _run(
    arguments: Sequence[str],
    *,
    environment: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: int = 120,
    label: str,
) -> str:
    completed = subprocess.run(
        list(arguments),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        cwd=cwd,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RehearsalError(
            f"{label} failed with exit code {completed.returncode}; STOP"
        )
    return completed.stdout.strip()


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_http(port: int) -> None:
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            response = opener.open(
                Request(f"http://127.0.0.1:{port}/health", method="GET"),
                timeout=2,
            )
            try:
                if response.status == 200:
                    return
            finally:
                response.close()
        except Exception:
            time.sleep(0.5)
    raise RehearsalError("disposable Gateway did not become healthy; STOP")


def _compose(
    *,
    project: str,
    compose_files: Sequence[Path],
    environment_file: Path,
    tail: Sequence[str],
) -> tuple[str, ...]:
    compose_arguments = tuple(
        argument
        for path in compose_files
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


def _gateway_compose(
    *,
    project: str,
    compose_file: Path,
    environment_file: Path,
    tail: Sequence[str],
) -> tuple[str, ...]:
    return (
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(compose_file),
        "--env-file",
        str(environment_file),
        *tail,
    )


def _exact_service_ids(
    *,
    project: str,
    compose_files: Sequence[Path],
    environment_file: Path,
    environment: dict[str, str],
    running: bool,
) -> tuple[str, str]:
    result: list[str] = []
    for service in ("company_report_worker", "company_card_narrative_worker"):
        flags = ("--quiet",) if running else ("--all", "--quiet")
        rows = [
            row
            for row in _run(
                _compose(
                    project=project,
                    compose_files=compose_files,
                    environment_file=environment_file,
                    tail=("ps", *flags, service),
                ),
                environment=environment,
                cwd=compose_files[0].parent,
                label="worker identity discovery",
            ).splitlines()
            if row
        ]
        if len(rows) != 1 or _CONTAINER.fullmatch(rows[0]) is None:
            raise RehearsalError("disposable worker cardinality is not exactly one; STOP")
        result.append(rows[0])
    return result[0], result[1]


def _inspect_recovered_workers(
    identities: tuple[str, str],
    *,
    release_sha: str,
    image_id: str,
) -> None:
    for container_id in identities:
        raw = _run(
            ("docker", "inspect", container_id),
            label="worker post-transition inspection",
        )
        try:
            data = json.loads(raw)[0]
            releases = [
                row.removeprefix("PRODUCT_RELEASE_COMMIT=")
                for row in data["Config"]["Env"]
                if row.startswith("PRODUCT_RELEASE_COMMIT=")
            ]
        except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise RehearsalError("worker post-transition response is invalid; STOP") from exc
        if (
            data.get("Id") != container_id
            or data.get("Image") != image_id
            or data.get("State", {}).get("Running") is not True
            or data.get("HostConfig", {}).get("RestartPolicy", {}).get("Name")
            != "unless-stopped"
            or data.get("HostConfig", {}).get("NetworkMode") != "host"
            or releases != [release_sha]
        ):
            raise RehearsalError("worker post-transition identity mismatch; STOP")


def _copy_gateway_compose_for_port(source: Path, target: Path, port: int) -> None:
    if port < 1 or port > 65535:
        raise RehearsalError("disposable Gateway port is invalid; STOP")
    text = source.read_text(encoding="utf-8")
    binding = '127.0.0.1:8001:8001'
    if text.count(binding) != 1:
        raise RehearsalError("canonical Gateway loopback binding is missing; STOP")
    target.write_text(
        text.replace(binding, f"127.0.0.1:{port}:8001"),
        encoding="utf-8",
        newline="\n",
    )


def _canonical_cli(arguments: Sequence[str], *, environment: dict[str, str] | None = None, label: str) -> dict[str, object]:
    raw = _run(arguments, environment=environment, label=label)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RehearsalError(f"{label} did not emit JSON; STOP") from exc
    if not isinstance(value, dict) or raw != json.dumps(value, separators=(",", ":"), sort_keys=True):
        raise RehearsalError(f"{label} receipt is not canonical; STOP")
    return value


def _shared_worker_identity(
    identities: tuple[str, str],
    *,
    release_sha: str,
    image_id: str,
    compose_project: str,
    label: str,
) -> dict[str, object]:
    receipt = _canonical_cli(
        (
            sys.executable,
            str(WORKER_IDENTITY),
            "--release-sha",
            release_sha,
            "--expected-image-id",
            image_id,
            "--compose-project",
            compose_project,
            "--report-container",
            identities[0],
            "--narrative-container",
            identities[1],
        ),
        label=label,
    )
    if (
        receipt.get("schema_version") != "worker_runtime_identity_v1"
        or receipt.get("outcome") != "verified"
        or receipt.get("release_sha") != release_sha
        or receipt.get("expected_image_id") != image_id
        or receipt.get("compose_project") != compose_project
        or receipt.get("report_worker_container") != identities[0]
        or receipt.get("narrative_worker_container") != identities[1]
    ):
        raise RehearsalError(f"{label} receipt is invalid; STOP")
    return receipt


def _create_prior_image(*, candidate: str, prior: str, seed_name: str) -> str:
    _run(("docker", "create", "--name", seed_name, candidate), label="prior image seed create")
    try:
        _run(
            (
                "docker",
                "commit",
                "--change",
                "LABEL com.b2b.deploy-rehearsal.prior=true",
                seed_name,
                prior,
            ),
            label="prior image materialization",
        )
    finally:
        _run(("docker", "rm", seed_name), label="prior image seed cleanup")
    image_id = _run(
        ("docker", "image", "inspect", "--format", "{{.Id}}", prior),
        label="prior image inspection",
    )
    if _IMAGE.fullmatch(image_id) is None:
        raise RehearsalError("prior image identity is invalid; STOP")
    return image_id


def _verify_release_images(
    release_root: Path,
    release_sha: str,
    postgres_image: str,
) -> tuple[str, str]:
    manifest_path = release_root / f"release-manifest-{release_sha}.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RehearsalError("release manifest cannot be read; STOP") from exc
    if manifest.get("release_sha") != release_sha:
        raise RehearsalError("release manifest SHA mismatch; STOP")
    if manifest.get("pins", {}).get("postgres_image") != postgres_image:
        raise RehearsalError("PostgreSQL image is not release-manifest pinned; STOP")
    result: list[str] = []
    for service in ("product", "gateway"):
        archive = f"{service}-api-{release_sha}.oci.tar"
        digest = manifest.get("images", {}).get(archive, {}).get("config_digest")
        actual = _run(
            (
                "docker",
                "image",
                "inspect",
                "--format",
                "{{.Id}}",
                f"b2b-{service}-api:{release_sha}",
            ),
            label="candidate image inspection",
        )
        if not isinstance(digest, str) or _IMAGE.fullmatch(digest) is None or actual != digest:
            raise RehearsalError("candidate image/manifest identity mismatch; STOP")
        result.append(actual)
    return result[0], result[1]


def run_rehearsal(
    *,
    release_sha: str,
    release_root: Path,
    postgres_image: str,
) -> dict[str, object]:
    if _SHA.fullmatch(release_sha) is None:
        raise RehearsalError("release SHA is invalid; STOP")
    if not release_root.is_absolute() or release_root.is_symlink() or not release_root.is_dir():
        raise RehearsalError("release artifact root is not exact; STOP")
    for command in ("docker", "psql"):
        if shutil.which(command) is None:
            raise RehearsalError(f"required rehearsal command is unavailable: {command}; STOP")
    candidate_product_image, candidate_gateway_image = _verify_release_images(
        release_root, release_sha, postgres_image
    )
    postgres_image_id = _run(
        ("docker", "image", "inspect", "--format", "{{.Id}}", postgres_image),
        label="pinned PostgreSQL image inspection",
    )
    if _IMAGE.fullmatch(postgres_image_id) is None:
        raise RehearsalError("pinned PostgreSQL image identity is invalid; STOP")

    run_id = uuid4().hex
    short = run_id[:12]
    postgres_port = _free_loopback_port()
    gateway_port = _free_loopback_port()
    while gateway_port == postgres_port:
        gateway_port = _free_loopback_port()
    prior_sha = sha256(f"prior:{release_sha}".encode("ascii")).hexdigest()[:40]
    if prior_sha == release_sha:
        raise RehearsalError("prior/candidate release identity collision; STOP")
    temporary = Path(tempfile.mkdtemp(prefix=f"deploy-rehearsal-{short}-"))
    product_root = temporary / "product-releases"
    gateway_root = temporary / "gateway-releases"
    product_prior_stage = product_root / f"{prior_sha}-fresh-install"
    product_candidate_stage = product_root / release_sha
    gateway_prior_stage = gateway_root / f"{prior_sha}-fresh-install"
    gateway_candidate_stage = gateway_root / release_sha
    for path in (product_prior_stage, product_candidate_stage, gateway_prior_stage):
        path.mkdir(parents=True)
    shutil.copy2(PRODUCT_COMPOSE, product_prior_stage / PRODUCT_COMPOSE.name)
    shutil.copy2(PRODUCT_COMPOSE, product_candidate_stage / PRODUCT_COMPOSE.name)
    _copy_gateway_compose_for_port(
        GATEWAY_COMPOSE,
        gateway_prior_stage / GATEWAY_COMPOSE.name,
        gateway_port,
    )
    product_network_override = temporary / "docker-compose.product.rehearsal.yml"
    product_network_override.write_text(
        "services:\n"
        "  company_report_worker:\n"
        "    network_mode: host\n"
        "  company_card_narrative_worker:\n"
        "    network_mode: host\n",
        encoding="utf-8",
        newline="\n",
    )
    prior_product_files = (
        product_prior_stage / PRODUCT_COMPOSE.name,
        product_network_override,
    )
    candidate_product_files = (
        product_candidate_stage / PRODUCT_COMPOSE.name,
        product_network_override,
    )

    postgres_name = f"deploy-rehearsal-pg-{short}"
    product_project = f"rehearsal_product_{short}"
    gateway_project = f"rehearsal_gateway_{short}"
    product_seed = f"deploy-rehearsal-product-seed-{short}"
    gateway_seed = f"deploy-rehearsal-gateway-seed-{short}"
    password = f"rehearsal{run_id}"
    async_database_url = (
        f"postgresql+asyncpg://rehearsal:{password}@127.0.0.1:{postgres_port}/rehearsal"
    )
    claims_root = temporary / "claims"
    claims_root.mkdir()
    product_environment_file = temporary / ".env.product"
    product_environment_file.write_text(
        "\n".join(
            (
                "APP_ENV=test",
                "LOG_LEVEL=INFO",
                f"DATABASE_URL={async_database_url}",
                f"GATEWAY_URL=http://127.0.0.1:{gateway_port}",
                "GATEWAY_SHARED_SECRET=rehearsal-shared-secret",
                "AUTH_TOKEN_SECRET=rehearsal-auth-secret",
                "CLAIM_EDIT_TOKEN_SECRET=rehearsal-claim-secret",
                f"CLAIMS_UPLOAD_ROOT={claims_root}",
                "CLAIMS_UPLOAD_DIR=/data/claims_uploads",
                "INVITE_TOKEN_SECRET=rehearsal-invite-secret",
                "SESSION_SECRET=rehearsal-session-secret",
                "EMAIL_FROM=rehearsal@example.invalid",
                "DATANEWTON_ENABLED=false",
                "DATANEWTON_TIMEOUT_SECONDS=1",
                "COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS=0",
                "COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS=1",
                "COMPANY_CARD_AI_NARRATIVE_ENABLED=false",
                "COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH=true",
                "COMPANY_CARD_AI_NARRATIVE_DAILY_DISPATCH_CREDITS=0",
                "COMPANY_CARD_AI_NARRATIVE_MONTHLY_DISPATCH_CREDITS=0",
                "COMPANY_CARD_AI_NARRATIVE_WORKER_CONCURRENCY=0",
            )
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    gateway_environment_file = temporary / ".env.gateway"
    gateway_environment_file.write_text(
        "\n".join(
            (
                "APP_ENV=test",
                "LOG_LEVEL=INFO",
                "GATEWAY_SHARED_SECRET=rehearsal-shared-secret",
                "COMPANY_CARD_NARRATIVE_GATEWAY_ENABLED=false",
            )
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    product_environment = os.environ.copy()
    product_environment.update(
        {
            "PRODUCT_ENV_FILE": str(product_environment_file),
            "PRODUCT_IMAGE_TAG": prior_sha,
            "PRODUCT_RELEASE_COMMIT": prior_sha,
        }
    )
    gateway_environment = os.environ.copy()
    gateway_environment.update(
        {
            "GATEWAY_ENV_FILE": str(gateway_environment_file),
            "GATEWAY_IMAGE_TAG": prior_sha,
            "GATEWAY_RELEASE_COMMIT": prior_sha,
        }
    )
    cleanup_errors: list[str] = []
    prior_product_image = ""
    prior_gateway_image = ""
    primary_error: BaseException | None = None
    try:
        _run(
            (
                "docker",
                "run",
                "--detach",
                "--name",
                postgres_name,
                "--label",
                f"com.b2b.deploy-rehearsal.run-id={run_id}",
                "--env",
                "POSTGRES_USER=rehearsal",
                "--env",
                f"POSTGRES_PASSWORD={password}",
                "--env",
                "POSTGRES_DB=rehearsal",
                "--network",
                "host",
                postgres_image,
                "-c",
                f"port={postgres_port}",
            ),
            label="disposable PostgreSQL start",
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            completed = subprocess.run(
                (
                    "docker", "exec", postgres_name, "pg_isready", "-U", "rehearsal",
                    "-p", str(postgres_port),
                ),
                check=False,
                capture_output=True,
                timeout=5,
            )
            if completed.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RehearsalError("disposable PostgreSQL did not become ready; STOP")

        _run(
            (
                "docker",
                "run",
                "--rm",
                "--network",
                "host",
                "--env-file",
                str(product_environment_file),
                "--entrypoint",
                "python",
                f"b2b-product-api:{release_sha}",
                "-m",
                "alembic",
                "-c",
                "/app/alembic.ini",
                "upgrade",
                "head",
            ),
            timeout=180,
            label="candidate-image PostgreSQL migration",
        )

        prior_product_image = _create_prior_image(
            candidate=f"b2b-product-api:{release_sha}",
            prior=f"b2b-product-api:{prior_sha}",
            seed_name=product_seed,
        )
        prior_gateway_image = _create_prior_image(
            candidate=f"b2b-gateway-api:{release_sha}",
            prior=f"b2b-gateway-api:{prior_sha}",
            seed_name=gateway_seed,
        )
        if prior_product_image == candidate_product_image or prior_gateway_image == candidate_gateway_image:
            raise RehearsalError("synthetic prior image is not distinct from candidate; STOP")

        _run(
            _compose(
                project=product_project,
                compose_files=prior_product_files,
                environment_file=product_environment_file,
                tail=(
                    "up",
                    "-d",
                    "--no-build",
                    "--force-recreate",
                    "company_report_worker",
                    "company_card_narrative_worker",
                ),
            ),
            environment=product_environment,
            cwd=product_prior_stage,
            label="prior workers start",
        )
        worker_ids = _exact_service_ids(
            project=product_project,
            compose_files=prior_product_files,
            environment_file=product_environment_file,
            environment=product_environment,
            running=True,
        )
        _inspect_recovered_workers(
            worker_ids, release_sha=prior_sha, image_id=prior_product_image
        )
        _shared_worker_identity(
            worker_ids,
            release_sha=prior_sha,
            image_id=prior_product_image,
            compose_project=product_project,
            label="prior shared worker identity",
        )
        _canonical_cli(
            (
                sys.executable,
                str(WORKER_DRAIN),
                "--container",
                worker_ids[0],
                "--container",
                worker_ids[1],
                "--settings-container",
                worker_ids[0],
                "--deadline-seconds",
                "30",
                "--stable-interval-seconds",
                "1",
                "--validate-only",
                "--release-sha",
                release_sha,
            ),
            label="exact worker SQL preflight",
        )

        rollback_tag = f"b2b-product-api:rollback-{release_sha}"
        _run(("docker", "tag", f"b2b-product-api:{prior_sha}", rollback_tag), label="worker rollback arm")
        wrapper_root = temporary / "psql-wrapper"
        wrapper_root.mkdir()
        counter = wrapper_root / "counter"
        real_psql = Path(shutil.which("psql") or "")
        wrapper = wrapper_root / "psql"
        wrapper.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "count=0\n"
            "if test -f \"$REHEARSAL_PSQL_COUNTER\"; then read -r count < \"$REHEARSAL_PSQL_COUNTER\"; fi\n"
            "count=$((count + 1))\n"
            "printf '%s\\n' \"$count\" > \"$REHEARSAL_PSQL_COUNTER\"\n"
            "if test \"$count\" -eq 2; then exit 70; fi\n"
            "exec \"$REHEARSAL_REAL_PSQL\" \"$@\"\n",
            encoding="utf-8",
            newline="\n",
        )
        wrapper.chmod(0o750)
        injected_environment = os.environ.copy()
        injected_environment.update(
            {
                "PATH": f"{wrapper_root}{os.pathsep}{os.environ.get('PATH', '')}",
                "REHEARSAL_PSQL_COUNTER": str(counter),
                "REHEARSAL_REAL_PSQL": str(real_psql),
            }
        )
        injected = subprocess.run(
            (
                sys.executable,
                str(WORKER_DRAIN),
                "--container",
                worker_ids[0],
                "--container",
                worker_ids[1],
                "--settings-container",
                worker_ids[0],
                "--deadline-seconds",
                "30",
                "--stable-interval-seconds",
                "1",
            ),
            check=False,
            capture_output=True,
            text=True,
            env=injected_environment,
            timeout=60,
        )
        if injected.returncode != 2 or "aggregate database query failed" not in injected.stderr:
            raise RehearsalError("post-mutation worker failure injection did not trip; STOP")
        for container_id in worker_ids:
            state = _run(
                (
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Running}}|{{.HostConfig.RestartPolicy.Name}}",
                    container_id,
                ),
                label="failed-drain worker state inspection",
            )
            if state != "false|no":
                raise RehearsalError("failure injection did not reach the mutation boundary; STOP")

        recovery_receipt = _canonical_cli(
            (
                sys.executable,
                str(WORKER_RECOVERY),
                "--prior-release-sha",
                prior_sha,
                "--expected-image-id",
                prior_product_image,
                "--rollback-tag",
                rollback_tag,
                "--compose-project",
                product_project,
                "--compose-file",
                str(product_prior_stage / PRODUCT_COMPOSE.name),
                "--compose-override-file",
                str(product_network_override),
                "--environment-file",
                str(product_environment_file),
            ),
            label="shared worker recovery",
        )
        if recovery_receipt.get("outcome") != "recovered":
            raise RehearsalError("shared worker recovery receipt is invalid; STOP")

        recovered_ids = _exact_service_ids(
            project=product_project,
            compose_files=prior_product_files,
            environment_file=product_environment_file,
            environment=product_environment,
            running=True,
        )
        _inspect_recovered_workers(
            recovered_ids, release_sha=prior_sha, image_id=prior_product_image
        )
        _shared_worker_identity(
            recovered_ids,
            release_sha=prior_sha,
            image_id=prior_product_image,
            compose_project=product_project,
            label="recovered shared worker identity",
        )
        drain_receipt = _canonical_cli(
            (
                sys.executable,
                str(WORKER_DRAIN),
                "--container",
                recovered_ids[0],
                "--container",
                recovered_ids[1],
                "--settings-container",
                recovered_ids[0],
                "--deadline-seconds",
                "30",
                "--stable-interval-seconds",
                "1",
            ),
            label="successful worker drain",
        )
        if drain_receipt.get("outcome") != "drained":
            raise RehearsalError("successful worker drain receipt is invalid; STOP")

        product_environment.update(
            {"PRODUCT_IMAGE_TAG": release_sha, "PRODUCT_RELEASE_COMMIT": release_sha}
        )
        _run(
            _compose(
                project=product_project,
                compose_files=candidate_product_files,
                environment_file=product_environment_file,
                tail=(
                    "up",
                    "-d",
                    "--no-build",
                    "--force-recreate",
                    "company_report_worker",
                    "company_card_narrative_worker",
                ),
            ),
            environment=product_environment,
            cwd=product_candidate_stage,
            label="candidate workers transition",
        )
        candidate_worker_ids = _exact_service_ids(
            project=product_project,
            compose_files=candidate_product_files,
            environment_file=product_environment_file,
            environment=product_environment,
            running=True,
        )
        _inspect_recovered_workers(
            candidate_worker_ids,
            release_sha=release_sha,
            image_id=candidate_product_image,
        )
        _shared_worker_identity(
            candidate_worker_ids,
            release_sha=release_sha,
            image_id=candidate_product_image,
            compose_project=product_project,
            label="candidate shared worker identity",
        )

        _run(
            _gateway_compose(
                project=gateway_project,
                compose_file=gateway_prior_stage / GATEWAY_COMPOSE.name,
                environment_file=gateway_environment_file,
                tail=("up", "-d", "--no-build", "--force-recreate", "gateway_api"),
            ),
            environment=gateway_environment,
            cwd=gateway_prior_stage,
            label="fresh-install topology Gateway start",
        )
        _wait_http(gateway_port)
        prior_gateway_receipt = _canonical_cli(
            (
                sys.executable,
                str(GATEWAY_IDENTITY),
                "--release-root",
                str(gateway_root),
                "--candidate-release-sha",
                release_sha,
                "--environment-file",
                str(gateway_environment_file),
                "--expected-loopback",
                f"127.0.0.1:{gateway_port}",
                "--health-url",
                f"http://127.0.0.1:{gateway_port}/health",
            ),
            label="fresh-install Gateway identity",
        )
        if (
            prior_gateway_receipt.get("topology") != "fresh-install"
            or prior_gateway_receipt.get("current_release_sha") != prior_sha
            or prior_gateway_receipt.get("current_image_id") != prior_gateway_image
        ):
            raise RehearsalError("fresh-install Gateway receipt is invalid; STOP")

        gateway_candidate_stage.mkdir()
        _copy_gateway_compose_for_port(
            GATEWAY_COMPOSE,
            gateway_candidate_stage / GATEWAY_COMPOSE.name,
            gateway_port,
        )
        gateway_environment.update(
            {"GATEWAY_IMAGE_TAG": release_sha, "GATEWAY_RELEASE_COMMIT": release_sha}
        )
        _run(
            _gateway_compose(
                project=gateway_project,
                compose_file=gateway_candidate_stage / GATEWAY_COMPOSE.name,
                environment_file=gateway_environment_file,
                tail=("up", "-d", "--no-build", "--force-recreate", "gateway_api"),
            ),
            environment=gateway_environment,
            cwd=gateway_candidate_stage,
            label="normal topology Gateway transition",
        )
        _wait_http(gateway_port)
        deployed_gateway_receipt = _canonical_cli(
            (
                sys.executable,
                str(GATEWAY_IDENTITY),
                "--release-root",
                str(gateway_root),
                "--expected-release-sha",
                release_sha,
                "--environment-file",
                str(gateway_environment_file),
                "--expected-loopback",
                f"127.0.0.1:{gateway_port}",
                "--health-url",
                f"http://127.0.0.1:{gateway_port}/health",
            ),
            label="normal Gateway identity",
        )
        if (
            deployed_gateway_receipt.get("topology") != "normal"
            or deployed_gateway_receipt.get("current_image_id")
            != candidate_gateway_image
        ):
            raise RehearsalError("normal Gateway receipt is invalid; STOP")

        return {
            "candidate_gateway_image_id": candidate_gateway_image,
            "candidate_product_image_id": candidate_product_image,
            "failure_injection": "recovered",
            "gateway_transition": "fresh-install-to-normal",
            "postgresql_acceptance": "migrated-head-and-exact-drain-sql",
            "release_sha": release_sha,
            "schema_version": "normal_deploy_rehearsal_v1",
            "worker_transition": "prior-recovered-drained-candidate",
        }
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        cleanup_environment = os.environ.copy()
        for command, environment, cwd, label in (
            (
                _compose(
                    project=product_project,
                    compose_files=candidate_product_files,
                    environment_file=product_environment_file,
                    tail=("down", "--remove-orphans"),
                ),
                product_environment,
                product_candidate_stage,
                "Product rehearsal cleanup",
            ),
            (
                _gateway_compose(
                    project=gateway_project,
                    compose_file=(
                        gateway_candidate_stage / GATEWAY_COMPOSE.name
                        if gateway_candidate_stage.is_dir()
                        else gateway_prior_stage / GATEWAY_COMPOSE.name
                    ),
                    environment_file=gateway_environment_file,
                    tail=("down", "--remove-orphans"),
                ),
                gateway_environment,
                gateway_candidate_stage if gateway_candidate_stage.is_dir() else gateway_prior_stage,
                "Gateway rehearsal cleanup",
            ),
            (("docker", "rm", "-f", postgres_name), cleanup_environment, None, "PostgreSQL rehearsal cleanup"),
        ):
            try:
                _run(command, environment=environment, cwd=cwd, label=label)
            except Exception as exc:
                cleanup_errors.append(str(exc))
        for tag in (
            f"b2b-product-api:{prior_sha}",
            f"b2b-product-api:rollback-{release_sha}",
            f"b2b-gateway-api:{prior_sha}",
        ):
            try:
                _run(("docker", "image", "rm", tag), label="prior image cleanup")
            except Exception as exc:
                cleanup_errors.append(str(exc))
        try:
            shutil.rmtree(temporary, ignore_errors=False)
        except Exception as exc:
            cleanup_errors.append(f"temporary rehearsal cleanup failed: {exc}")
        if primary_error is None and cleanup_errors:
            raise RehearsalError("; ".join(cleanup_errors))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run disposable normal deploy rehearsal")
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--release-root", required=True)
    parser.add_argument("--postgres-image", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_rehearsal(
            release_sha=args.release_sha,
            release_root=Path(args.release_root).resolve(strict=True),
            postgres_image=args.postgres_image,
        )
    except (RehearsalError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
