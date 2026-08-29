"""Fail-closed drain for the single CompanyReport worker on schema revision 0015.

This one-time bootstrap helper deliberately knows only the pre-narrative job
table.  It disables restart for one exact running container, sends SIGTERM,
and waits for two equal aggregate snapshots with no running job.  It has no
force, migration, row-output, or container-recreate capability.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from typing import Callable, Protocol, Sequence

_CONTAINER_ID = re.compile(r"^[0-9a-f]{12,64}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


class LegacyDrainError(RuntimeError):
    """Closed failure that must stop the bootstrap before Alembic."""


@dataclass(frozen=True)
class ContainerIdentity:
    container_id: str
    image_id: str

    def __post_init__(self) -> None:
        if (
            _CONTAINER_ID.fullmatch(self.container_id) is None
            or _IMAGE_ID.fullmatch(self.image_id) is None
        ):
            raise LegacyDrainError("legacy worker container identity is invalid")


@dataclass(frozen=True)
class AggregateSnapshot:
    db_clock: str
    queued: int
    running: int
    succeeded: int
    failed: int

    def __post_init__(self) -> None:
        if not isinstance(self.db_clock, str) or not self.db_clock:
            raise LegacyDrainError("legacy database clock is missing")
        for field in fields(self):
            if field.name == "db_clock":
                continue
            value = getattr(self, field.name)
            if type(value) is not int or value < 0:
                raise LegacyDrainError("legacy aggregate snapshot is invalid")

    def stable_key(self) -> tuple[int, int, int, int]:
        return self.queued, self.running, self.succeeded, self.failed


@dataclass(frozen=True)
class DrainPolicy:
    deadline_seconds: float
    shutdown_grace_seconds: float
    provider_timeout_seconds: float
    stable_interval_seconds: float
    poll_interval_seconds: float = 1.0

    def __post_init__(self) -> None:
        values = (
            self.deadline_seconds,
            self.provider_timeout_seconds,
            self.stable_interval_seconds,
            self.poll_interval_seconds,
        )
        if any(
            type(value) not in {int, float}
            or not math.isfinite(value)
            or value <= 0
            for value in values
        ) or (
            type(self.shutdown_grace_seconds) not in {int, float}
            or not math.isfinite(self.shutdown_grace_seconds)
            or self.shutdown_grace_seconds < 0
        ):
            raise LegacyDrainError("legacy drain timing values are outside allowed bounds")
        if self.deadline_seconds < max(
            self.shutdown_grace_seconds, self.provider_timeout_seconds
        ):
            raise LegacyDrainError("legacy drain deadline is shorter than operation bounds")
        if self.stable_interval_seconds >= self.deadline_seconds:
            raise LegacyDrainError("legacy stable interval must fit inside the deadline")


@dataclass(frozen=True)
class DrainResult:
    poll_count: int
    snapshot: AggregateSnapshot
    worker_container: str
    worker_image: str

    def privacy_safe_json(self, database_url: str) -> str:
        if not database_url or any(character in database_url for character in "\r\n\x00"):
            raise LegacyDrainError("database URL is missing or invalid")
        return json.dumps(
            {
                "aggregate": {
                    key: value
                    for key, value in asdict(self.snapshot).items()
                    if key != "db_clock"
                },
                "database_target_sha256": sha256(
                    database_url.encode("utf-8")
                ).hexdigest(),
                "db_clock": self.snapshot.db_clock,
                "outcome": "drained",
                "poll_count": self.poll_count,
                "worker_container": self.worker_container,
                "worker_image": self.worker_image,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


class ContainerAdapter(Protocol):
    def capture(self) -> ContainerIdentity: ...
    def disable_restart(self, identity: ContainerIdentity) -> None: ...
    def send_sigterm(self, identity: ContainerIdentity) -> None: ...
    def exited(self, identity: ContainerIdentity) -> bool: ...


class DatabaseAdapter(Protocol):
    def snapshot(self) -> AggregateSnapshot: ...


def drain_worker(
    container: ContainerAdapter,
    database: DatabaseAdapter,
    policy: DrainPolicy,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> DrainResult:
    started = monotonic()
    identity = container.capture()
    container.disable_restart(identity)
    container.send_sigterm(identity)
    prior_key: tuple[int, int, int, int] | None = None
    prior_at: float | None = None
    polls = 0
    while True:
        now = monotonic()
        if now - started >= policy.deadline_seconds:
            raise LegacyDrainError("legacy worker drain deadline expired")
        polls += 1
        if not container.exited(identity):
            prior_key = None
            prior_at = None
            sleep(policy.poll_interval_seconds)
            continue
        snapshot = database.snapshot()
        key = snapshot.stable_key()
        if snapshot.running != 0:
            prior_key = None
            prior_at = None
        elif prior_key == key and prior_at is not None and (
            now - prior_at >= policy.stable_interval_seconds
        ):
            return DrainResult(polls, snapshot, identity.container_id, identity.image_id)
        elif prior_key != key or prior_at is None:
            prior_key = key
            prior_at = now
        sleep(policy.poll_interval_seconds)


class DockerCliAdapter:
    def __init__(self, container_id: str) -> None:
        if _CONTAINER_ID.fullmatch(container_id) is None:
            raise LegacyDrainError("exactly one legacy worker container is required")
        self._container_id = container_id

    @staticmethod
    def _run(arguments: list[str]) -> str:
        completed = subprocess.run(
            ["docker", *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if completed.returncode != 0:
            raise LegacyDrainError("legacy Docker worker operation failed")
        return completed.stdout.strip()

    def capture(self) -> ContainerIdentity:
        raw = self._run(["inspect", "--format", "{{json .}}", self._container_id])
        try:
            data = json.loads(raw)
            identity = ContainerIdentity(data["Id"], data["Image"])
            running = data["State"]["Running"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise LegacyDrainError("legacy Docker identity response is invalid") from exc
        if running is not True or identity.container_id != self._container_id:
            raise LegacyDrainError("legacy worker is not the exact running container")
        return identity

    def environment(self, names: frozenset[str]) -> dict[str, str]:
        raw = self._run(
            ["inspect", "--format", "{{json .Config.Env}}", self._container_id]
        )
        return _parse_container_environment(raw, names)

    def disable_restart(self, identity: ContainerIdentity) -> None:
        self._run(["update", "--restart=no", identity.container_id])

    def send_sigterm(self, identity: ContainerIdentity) -> None:
        self._run(["kill", "--signal=TERM", identity.container_id])

    def exited(self, identity: ContainerIdentity) -> bool:
        value = self._run(
            ["inspect", "--format", "{{.State.Running}}", identity.container_id]
        )
        if value not in {"true", "false"}:
            raise LegacyDrainError("legacy Docker state response is invalid")
        return value == "false"


_AGGREGATE_SQL = r"""
SELECT json_build_object(
  'db_clock', clock_timestamp()::text,
  'queued', count(*) FILTER (WHERE state = 'queued'),
  'running', count(*) FILTER (WHERE state = 'running'),
  'succeeded', count(*) FILTER (WHERE state = 'succeeded'),
  'failed', count(*) FILTER (WHERE state = 'failed')
)::text
FROM company_report_jobs;
"""


class PsqlAggregateAdapter:
    def __init__(self, database_url: str) -> None:
        if not database_url or any(character in database_url for character in "\r\n\x00"):
            raise LegacyDrainError("database URL is missing or invalid")
        self._database_url = database_url.replace(
            "postgresql+asyncpg://", "postgresql://", 1
        )

    def snapshot(self) -> AggregateSnapshot:
        environment = os.environ.copy()
        environment["PGCONNECT_TIMEOUT"] = "5"
        environment["PGDATABASE"] = self._database_url
        completed = subprocess.run(
            [
                "psql",
                "--no-psqlrc",
                "--tuples-only",
                "--no-align",
                "--set",
                "ON_ERROR_STOP=1",
                "--command",
                _AGGREGATE_SQL,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            env=environment,
        )
        if completed.returncode != 0:
            raise LegacyDrainError("legacy aggregate database query failed")
        rows = [line for line in completed.stdout.splitlines() if line.strip()]
        try:
            data = json.loads(rows[0]) if len(rows) == 1 else None
            if not isinstance(data, dict) or set(data) != {
                field.name for field in fields(AggregateSnapshot)
            }:
                raise LegacyDrainError("legacy aggregate database response is invalid")
            return AggregateSnapshot(**data)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LegacyDrainError("legacy aggregate database response is invalid") from exc


_REQUIRED_SETTINGS = frozenset(
    {
        "DATABASE_URL",
        "COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS",
        "DATANEWTON_TIMEOUT_SECONDS",
    }
)


def _parse_container_environment(raw: str, names: frozenset[str]) -> dict[str, str]:
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LegacyDrainError("legacy worker environment response is invalid") from exc
    if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
        raise LegacyDrainError("legacy worker environment response is invalid")
    result: dict[str, str] = {}
    for row in rows:
        name, separator, value = row.partition("=")
        if not separator or name not in names:
            continue
        if name in result or not value or any(character in value for character in "\r\n\x00"):
            raise LegacyDrainError("legacy worker environment response is invalid")
        result[name] = value
    if set(result) != names:
        raise LegacyDrainError("legacy worker environment is incomplete")
    return result


def _numeric(settings: dict[str, str], name: str, *, allow_zero: bool = False) -> float:
    try:
        value = float(settings[name])
    except (KeyError, ValueError) as exc:
        raise LegacyDrainError("legacy worker timing setting is invalid") from exc
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise LegacyDrainError("legacy worker timing setting is invalid")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Drain one exact revision-0015 report worker")
    parser.add_argument("--container", required=True)
    parser.add_argument("--deadline-seconds", type=float, required=True)
    parser.add_argument("--stable-interval-seconds", type=float, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        container = DockerCliAdapter(args.container)
        settings = container.environment(_REQUIRED_SETTINGS)
        result = drain_worker(
            container,
            PsqlAggregateAdapter(settings["DATABASE_URL"]),
            DrainPolicy(
                deadline_seconds=args.deadline_seconds,
                shutdown_grace_seconds=_numeric(
                    settings,
                    "COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS",
                    allow_zero=True,
                ),
                provider_timeout_seconds=_numeric(
                    settings, "DATANEWTON_TIMEOUT_SECONDS"
                ),
                stable_interval_seconds=args.stable_interval_seconds,
            ),
        )
        print(result.privacy_safe_json(settings["DATABASE_URL"]))
    except (LegacyDrainError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
