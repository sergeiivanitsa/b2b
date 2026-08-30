#!/usr/bin/env python3
"""Read-only exact identity and PostgreSQL proof for both Product workers."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Sequence

try:
    from worker_runtime_recovery import (
        WorkerRecoveryError,
        _IMAGE,
        _PROJECT,
        _SHA,
        _inspect_worker,
        _probe_worker_database,
    )
except ModuleNotFoundError:  # Repository import used by unit tests.
    from deploy.product_api.worker_runtime_recovery import (
        WorkerRecoveryError,
        _IMAGE,
        _PROJECT,
        _SHA,
        _inspect_worker,
        _probe_worker_database,
    )


def verify_workers(
    *,
    release_sha: str,
    expected_image_id: str,
    compose_project: str,
    report_container: str,
    narrative_container: str,
) -> dict[str, object]:
    if (
        _SHA.fullmatch(release_sha) is None
        or _IMAGE.fullmatch(expected_image_id) is None
        or _PROJECT.fullmatch(compose_project) is None
        or report_container == narrative_container
    ):
        raise WorkerRecoveryError("worker runtime identity is invalid; STOP")

    expected_config_image = f"b2b-product-api:{release_sha}"
    pairs = (
        ("company_report_worker", report_container),
        ("company_card_narrative_worker", narrative_container),
    )
    for service, container_id in pairs:
        _inspect_worker(
            container_id,
            service=service,
            project=compose_project,
            release_sha=release_sha,
            expected_image_id=expected_image_id,
            expected_config_image=expected_config_image,
            allowed_restart_policies=frozenset({"unless-stopped"}),
            require_running=True,
        )
        _probe_worker_database(container_id)
        _inspect_worker(
            container_id,
            service=service,
            project=compose_project,
            release_sha=release_sha,
            expected_image_id=expected_image_id,
            expected_config_image=expected_config_image,
            allowed_restart_policies=frozenset({"unless-stopped"}),
            require_running=True,
        )

    return {
        "compose_project": compose_project,
        "expected_image_id": expected_image_id,
        "narrative_worker_container": narrative_container,
        "outcome": "verified",
        "release_sha": release_sha,
        "report_worker_container": report_container,
        "schema_version": "worker_runtime_identity_v1",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify exact Product worker runtime")
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--expected-image-id", required=True)
    parser.add_argument("--compose-project", required=True)
    parser.add_argument("--report-container", required=True)
    parser.add_argument("--narrative-container", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = verify_workers(
            release_sha=args.release_sha,
            expected_image_id=args.expected_image_id,
            compose_project=args.compose_project,
            report_container=args.report_container,
            narrative_container=args.narrative_container,
        )
    except (WorkerRecoveryError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
