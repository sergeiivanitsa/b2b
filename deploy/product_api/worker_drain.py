"""Strict, adapter-driven report/narrative worker drain gate.

The tool sends SIGTERM only, waits for the exact old containers to exit, then
requires two stable privacy-safe aggregate database snapshots.  It deliberately
has no force/kill/migration/recreate capability.
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
_RELEASE_SHA = re.compile(r"^[0-9a-f]{40}$")


class DrainError(RuntimeError):
    """Closed failure that must stop deployment before Alembic."""


@dataclass(frozen=True)
class ContainerIdentity:
    name: str
    container_id: str
    image_id: str

    def __post_init__(self) -> None:
        if (
            not self.name
            or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for character in self.name)
            or _CONTAINER_ID.fullmatch(self.container_id) is None
            or _IMAGE_ID.fullmatch(self.image_id) is None
        ):
            raise DrainError("worker container identity is invalid")


@dataclass(frozen=True)
class AggregateSnapshot:
    db_clock: str
    report_queued: int
    report_succeeded: int
    report_failed: int
    report_running: int
    outbox_pending: int
    outbox_processed: int
    outbox_terminal: int
    outbox_leased: int
    narrative_ready: int
    narrative_pre_dispatch_failed: int
    narrative_finalized: int
    narrative_fallback_finalized: int
    narrative_ambiguous_timeout: int
    narrative_invalid_output: int
    narrative_active: int
    runtime_leased: int
    reservation_released: int
    reservation_consumed: int
    reservation_reserved: int
    unsafe_dispatch: int

    def __post_init__(self) -> None:
        if not isinstance(self.db_clock, str) or not self.db_clock:
            raise DrainError("database clock is missing")
        for field in fields(self):
            if field.name == "db_clock":
                continue
            value = getattr(self, field.name)
            if type(value) is not int or value < 0:
                raise DrainError("worker aggregate snapshot is invalid")

    @property
    def safe(self) -> bool:
        return all(
            value == 0
            for value in (
                self.report_running,
                self.outbox_leased,
                self.narrative_active,
                self.runtime_leased,
                self.reservation_reserved,
                self.unsafe_dispatch,
            )
        )

    def stable_key(self) -> tuple[int, ...]:
        return tuple(
            getattr(self, field.name)
            for field in fields(self)
            if field.name != "db_clock"
        )


@dataclass(frozen=True)
class DrainPolicy:
    deadline_seconds: float
    shutdown_grace_seconds: float
    provider_timeout_seconds: float
    gateway_timeout_seconds: float
    stable_interval_seconds: float
    poll_interval_seconds: float = 1.0

    def __post_init__(self) -> None:
        positive_values = (
            self.deadline_seconds,
            self.provider_timeout_seconds,
            self.gateway_timeout_seconds,
            self.stable_interval_seconds,
            self.poll_interval_seconds,
        )
        if any(
            type(value) not in {int, float} or not math.isfinite(value) or value <= 0
            for value in positive_values
        ) or (
            type(self.shutdown_grace_seconds) not in {int, float}
            or not math.isfinite(self.shutdown_grace_seconds)
            or self.shutdown_grace_seconds < 0
        ):
            raise DrainError("worker drain timing values are outside allowed bounds")
        required = max(
            self.shutdown_grace_seconds,
            self.provider_timeout_seconds,
            self.gateway_timeout_seconds,
        )
        if self.deadline_seconds < required:
            raise DrainError("worker drain deadline is shorter than configured operation bounds")
        if self.stable_interval_seconds >= self.deadline_seconds:
            raise DrainError("worker drain stable interval must fit inside the deadline")


@dataclass(frozen=True)
class DrainResult:
    outcome: str
    poll_count: int
    snapshot: AggregateSnapshot
    report_worker_container: str
    narrative_worker_container: str
    report_worker_image: str
    narrative_worker_image: str

    def privacy_safe_json(self) -> str:
        data = {
            "outcome": self.outcome,
            "poll_count": self.poll_count,
            "db_clock": self.snapshot.db_clock,
            "aggregate": {
                key: value
                for key, value in asdict(self.snapshot).items()
                if key != "db_clock"
            },
            "report_worker_container": self.report_worker_container,
            "narrative_worker_container": self.narrative_worker_container,
            "report_worker_image": self.report_worker_image,
            "narrative_worker_image": self.narrative_worker_image,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"))


def deployment_result_json(result: DrainResult, database_url: str) -> str:
    """Bind the safe drain evidence to its DB target without exposing credentials."""
    if not database_url or any(character in database_url for character in "\r\n\x00"):
        raise DrainError("database URL is missing or invalid")
    data = json.loads(result.privacy_safe_json())
    data["database_target_sha256"] = sha256(database_url.encode("utf-8")).hexdigest()
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def preflight_result_json(
    snapshot: AggregateSnapshot,
    identities: tuple[ContainerIdentity, ContainerIdentity],
    database_url: str,
    release_sha: str,
) -> str:
    """Bind a read-only, privacy-safe preflight to its release and DB target."""
    if (
        _RELEASE_SHA.fullmatch(release_sha) is None
        or not database_url
        or any(character in database_url for character in "\r\n\x00")
        or len(identities) != 2
        or identities[0].container_id == identities[1].container_id
    ):
        raise DrainError("worker drain preflight identity is invalid")
    data = {
        "outcome": "validated",
        "release_sha": release_sha,
        "database_target_sha256": sha256(database_url.encode("utf-8")).hexdigest(),
        "db_clock": snapshot.db_clock,
        "aggregate": {
            key: value
            for key, value in asdict(snapshot).items()
            if key != "db_clock"
        },
        "report_worker_container": identities[0].container_id,
        "narrative_worker_container": identities[1].container_id,
        "report_worker_image": identities[0].image_id,
        "narrative_worker_image": identities[1].image_id,
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


class ContainerAdapter(Protocol):
    def capture(self) -> tuple[ContainerIdentity, ContainerIdentity]: ...
    def disable_restart(self, identity: ContainerIdentity) -> None: ...
    def send_sigterm(self, identity: ContainerIdentity) -> None: ...
    def all_exited(self, identities: tuple[ContainerIdentity, ContainerIdentity]) -> bool: ...


class DatabaseAdapter(Protocol):
    def snapshot(self) -> AggregateSnapshot: ...


def drain_workers(
    containers: ContainerAdapter,
    database: DatabaseAdapter,
    policy: DrainPolicy,
    *,
    identities: tuple[ContainerIdentity, ContainerIdentity] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> DrainResult:
    """Drain exact workers and return only after two equal safe snapshots."""
    started = monotonic()
    identities = containers.capture() if identities is None else identities
    if len(identities) != 2 or identities[0].container_id == identities[1].container_id:
        raise DrainError("exact report and narrative worker identities are required")
    for identity in identities:
        containers.disable_restart(identity)
    for identity in identities:
        containers.send_sigterm(identity)

    prior_key: tuple[int, ...] | None = None
    prior_at: float | None = None
    polls = 0
    while True:
        now = monotonic()
        if now - started >= policy.deadline_seconds:
            raise DrainError("worker drain deadline expired")
        polls += 1
        if not containers.all_exited(identities):
            prior_key = None
            prior_at = None
            sleep(policy.poll_interval_seconds)
            continue
        snapshot = database.snapshot()
        key = snapshot.stable_key()
        if not snapshot.safe:
            prior_key = None
            prior_at = None
        elif prior_key == key and prior_at is not None and now - prior_at >= policy.stable_interval_seconds:
            return DrainResult(
                outcome="drained",
                poll_count=polls,
                snapshot=snapshot,
                report_worker_container=identities[0].container_id,
                narrative_worker_container=identities[1].container_id,
                report_worker_image=identities[0].image_id,
                narrative_worker_image=identities[1].image_id,
            )
        elif prior_key != key or prior_at is None:
            prior_key = key
            prior_at = now
        sleep(policy.poll_interval_seconds)


class DockerCliAdapter:
    def __init__(self, names: Sequence[str]) -> None:
        if len(names) != 2 or len(set(names)) != 2:
            raise DrainError("exactly two distinct worker containers are required")
        self._names = tuple(names)

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
            raise DrainError("docker worker operation failed")
        return completed.stdout.strip()

    def capture(self) -> tuple[ContainerIdentity, ContainerIdentity]:
        captured: list[ContainerIdentity] = []
        for name in self._names:
            raw = self._run(["inspect", "--format", "{{json .}}", name])
            try:
                data = json.loads(raw)
                container_id = data["Id"]
                image_id = data["Image"]
                running = data["State"]["Running"]
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise DrainError("docker worker identity response is invalid") from exc
            if running is not True:
                raise DrainError("worker is not running at drain start")
            captured.append(ContainerIdentity(name, container_id, image_id))
        return captured[0], captured[1]

    def environment(self, container_id: str, names: frozenset[str]) -> dict[str, str]:
        if _CONTAINER_ID.fullmatch(container_id) is None:
            raise DrainError("worker settings container identity is invalid")
        raw = self._run(["inspect", "--format", "{{json .Config.Env}}", container_id])
        return _parse_container_environment(raw, names)

    def disable_restart(self, identity: ContainerIdentity) -> None:
        self._run(["update", "--restart=no", identity.container_id])

    def send_sigterm(self, identity: ContainerIdentity) -> None:
        self._run(["kill", "--signal=TERM", identity.container_id])

    def all_exited(self, identities: tuple[ContainerIdentity, ContainerIdentity]) -> bool:
        states = [
            self._run(["inspect", "--format", "{{.State.Running}}", identity.container_id])
            for identity in identities
        ]
        if any(state not in {"true", "false"} for state in states):
            raise DrainError("docker worker state response is invalid")
        return states == ["false", "false"]


_AGGREGATE_SQL = r"""
WITH report AS (
  SELECT
    count(*) FILTER (WHERE state = 'queued') AS queued,
    count(*) FILTER (WHERE state = 'succeeded') AS succeeded,
    count(*) FILTER (WHERE state = 'failed') AS failed,
    count(*) FILTER (WHERE state = 'running') AS running
  FROM company_report_jobs
), outbox AS (
  SELECT
    count(*) FILTER (WHERE state = 'pending') AS pending,
    count(*) FILTER (WHERE state = 'processed') AS processed,
    count(*) FILTER (WHERE state = 'terminal') AS terminal,
    count(*) FILTER (WHERE state = 'leased') AS leased
  FROM company_card_narrative_outbox
), narrative AS (
  SELECT
    count(*) FILTER (WHERE state = 'ready') AS ready,
    count(*) FILTER (WHERE state = 'pre_dispatch_failed') AS pre_dispatch_failed,
    count(*) FILTER (WHERE state = 'finalized') AS finalized,
    count(*) FILTER (WHERE state = 'fallback_finalized') AS fallback_finalized,
    count(*) FILTER (WHERE state = 'ambiguous_timeout') AS ambiguous_timeout,
    count(*) FILTER (WHERE state = 'invalid_output') AS invalid_output,
    count(*) FILTER (WHERE state IN ('leased','dispatching','dispatched','validating','rendered')) AS active,
    count(*) FILTER (
      WHERE gateway_dispatch_id IS NOT NULL AND NOT (
        state IN ('ambiguous_timeout','fallback_finalized','invalid_output','finalized')
        AND lease_token IS NULL AND lease_expires_at IS NULL
        AND EXISTS (
          SELECT 1 FROM company_card_narrative_budget_reservations r
          WHERE r.generation_key = company_card_narrative_jobs.generation_key
            AND r.state = 'consumed'
        )
        AND (
          (state = 'finalized' AND EXISTS (
            SELECT 1 FROM company_card_narrative_artifacts a
            WHERE a.id = company_card_narrative_jobs.artifact_id
              AND a.generation_key = company_card_narrative_jobs.generation_key
              AND a.binding_kind = 'artifact'
          ))
          OR (state IN ('fallback_finalized','ambiguous_timeout','invalid_output') AND (
            artifact_id IS NULL OR EXISTS (
              SELECT 1 FROM company_card_narrative_artifacts a
              WHERE a.id = company_card_narrative_jobs.artifact_id
                AND a.generation_key = company_card_narrative_jobs.generation_key
                AND a.binding_kind = 'fallback'
            )
          ))
        )
      )
    ) AS unsafe_dispatch
  FROM company_card_narrative_jobs
), runtime AS (
  SELECT coalesce(sum(leased_count), 0) AS leased
  FROM company_card_narrative_runtime_control
), reservation AS (
  SELECT
    count(*) FILTER (WHERE state = 'released') AS released,
    count(*) FILTER (WHERE state = 'consumed') AS consumed,
    count(*) FILTER (WHERE state = 'reserved') AS reserved
  FROM company_card_narrative_budget_reservations
)
SELECT json_build_object(
  'db_clock', clock_timestamp()::text,
  'report_queued', report.queued,
  'report_succeeded', report.succeeded,
  'report_failed', report.failed,
  'report_running', report.running,
  'outbox_pending', outbox.pending,
  'outbox_processed', outbox.processed,
  'outbox_terminal', outbox.terminal,
  'outbox_leased', outbox.leased,
  'narrative_ready', narrative.ready,
  'narrative_pre_dispatch_failed', narrative.pre_dispatch_failed,
  'narrative_finalized', narrative.finalized,
  'narrative_fallback_finalized', narrative.fallback_finalized,
  'narrative_ambiguous_timeout', narrative.ambiguous_timeout,
  'narrative_invalid_output', narrative.invalid_output,
  'narrative_active', narrative.active,
  'runtime_leased', runtime.leased,
  'reservation_released', reservation.released,
  'reservation_consumed', reservation.consumed,
  'reservation_reserved', reservation.reserved,
  'unsafe_dispatch', narrative.unsafe_dispatch
)::text
FROM report, outbox, narrative, runtime, reservation;
"""


class PsqlAggregateAdapter:
    def __init__(self, database_url: str) -> None:
        if not database_url or any(character in database_url for character in "\r\n\x00"):
            raise DrainError("database URL is missing or invalid")
        self._database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    def snapshot(self) -> AggregateSnapshot:
        environment = os.environ.copy()
        environment["PGCONNECT_TIMEOUT"] = "5"
        environment["PGDATABASE"] = self._database_url
        completed = subprocess.run(
            ["psql", "--no-psqlrc", "--tuples-only", "--no-align", "--set", "ON_ERROR_STOP=1", "--command", _AGGREGATE_SQL],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            env=environment,
        )
        if completed.returncode != 0:
            raise DrainError("worker aggregate database query failed")
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if len(lines) != 1:
            raise DrainError("worker aggregate database response is invalid")
        try:
            data = json.loads(lines[0])
            if not isinstance(data, dict) or set(data) != {field.name for field in fields(AggregateSnapshot)}:
                raise DrainError("worker aggregate database response is invalid")
            return AggregateSnapshot(**data)
        except (TypeError, json.JSONDecodeError) as exc:
            raise DrainError("worker aggregate database response is invalid") from exc


_REQUIRED_SETTINGS = frozenset({
    "DATABASE_URL",
    "COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS",
    "DATANEWTON_TIMEOUT_SECONDS",
    "COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS",
})


def _parse_container_environment(raw: str, names: frozenset[str]) -> dict[str, str]:
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DrainError("worker settings environment response is invalid") from exc
    if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
        raise DrainError("worker settings environment response is invalid")
    result: dict[str, str] = {}
    for row in rows:
        name, separator, value = row.partition("=")
        if not separator or name not in names:
            continue
        if name in result or not value or any(character in value for character in "\r\n\x00"):
            raise DrainError("worker settings environment response is invalid")
        result[name] = value
    if set(result) != names:
        raise DrainError("worker settings environment is incomplete")
    return result


def _numeric_setting(settings: dict[str, str], name: str, *, allow_zero: bool = False) -> float:
    try:
        value = float(settings[name])
    except (KeyError, ValueError) as exc:
        raise DrainError("worker timing setting is invalid") from exc
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise DrainError("worker timing setting is invalid")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed Product worker drain")
    parser.add_argument("--container", action="append", required=True)
    parser.add_argument("--settings-container", required=True)
    parser.add_argument("--deadline-seconds", type=float, required=True)
    parser.add_argument("--stable-interval-seconds", type=float, required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--release-sha")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        containers = DockerCliAdapter(args.container)
        if args.settings_container not in args.container:
            raise DrainError("settings container must be one of the exact workers")
        identities = containers.capture()
        settings = containers.environment(args.settings_container, _REQUIRED_SETTINGS)
        for container_id in args.container:
            if containers.environment(container_id, _REQUIRED_SETTINGS) != settings:
                raise DrainError("exact workers do not share the same drain settings")
        policy = DrainPolicy(
            deadline_seconds=args.deadline_seconds,
            shutdown_grace_seconds=_numeric_setting(
                settings, "COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS", allow_zero=True
            ),
            provider_timeout_seconds=_numeric_setting(settings, "DATANEWTON_TIMEOUT_SECONDS"),
            gateway_timeout_seconds=_numeric_setting(
                settings, "COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS"
            ),
            stable_interval_seconds=args.stable_interval_seconds,
        )
        database = PsqlAggregateAdapter(settings["DATABASE_URL"])
        preflight_snapshot = database.snapshot()
        if args.validate_only:
            if _RELEASE_SHA.fullmatch(args.release_sha or "") is None:
                raise DrainError("exact release SHA is required for worker drain preflight")
            if not preflight_snapshot.safe:
                raise DrainError("worker aggregate snapshot is unsafe for deployment preflight")
            print(
                preflight_result_json(
                    preflight_snapshot,
                    identities,
                    settings["DATABASE_URL"],
                    args.release_sha,
                )
            )
            return 0
        result = drain_workers(
            containers,
            database,
            policy,
            identities=identities,
        )
    except (DrainError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(deployment_result_json(result, settings["DATABASE_URL"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
