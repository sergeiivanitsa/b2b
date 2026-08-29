"""Adapter-only tests for the one-time revision-0015 worker drain."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "deploy/product_api/legacy_0015_worker_drain.py"
SPEC = importlib.util.spec_from_file_location("legacy_0015_worker_drain", MODULE)
assert SPEC and SPEC.loader
drain = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = drain
SPEC.loader.exec_module(drain)


class Clock:
    now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Container:
    def __init__(self, exited):
        self.identity = drain.ContainerIdentity("c" * 64, f"sha256:{'d' * 64}")
        self.exits = iter(exited)
        self.last = False
        self.events = []

    def capture(self):
        self.events.append("capture")
        return self.identity

    def disable_restart(self, identity):
        self.events.append(("restart-none", identity.container_id))

    def send_sigterm(self, identity):
        self.events.append(("SIGTERM", identity.container_id))

    def exited(self, identity):
        assert identity == self.identity
        try:
            self.last = next(self.exits)
        except StopIteration:
            pass
        return self.last


class Database:
    def __init__(self, snapshots):
        self.snapshots = iter(snapshots)
        self.last = None
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        try:
            self.last = next(self.snapshots)
        except StopIteration:
            pass
        assert self.last is not None
        return self.last


def snapshot(**changes):
    values = dict(
        db_clock="2026-08-29 00:00:00+00",
        queued=2,
        running=0,
        succeeded=15,
        failed=0,
    )
    values.update(changes)
    return drain.AggregateSnapshot(**values)


def policy(**changes):
    values = dict(
        deadline_seconds=10,
        shutdown_grace_seconds=3,
        provider_timeout_seconds=4,
        stable_interval_seconds=2,
        poll_interval_seconds=1,
    )
    values.update(changes)
    return drain.DrainPolicy(**values)


def execute(container, database, selected_policy=None):
    clock = Clock()
    return drain.drain_worker(
        container,
        database,
        selected_policy or policy(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


def test_one_worker_sigterm_then_two_stable_safe_legacy_snapshots() -> None:
    container = Container([False, True, True, True])
    database = Database([snapshot(), snapshot(), snapshot()])
    result = execute(container, database)
    assert result.poll_count == 4
    assert container.events == [
        "capture",
        ("restart-none", "c" * 64),
        ("SIGTERM", "c" * 64),
    ]
    encoded = result.privacy_safe_json("postgresql://user:secret@db/app")
    data = json.loads(encoded)
    assert data["aggregate"] == {"failed": 0, "queued": 2, "running": 0, "succeeded": 15}
    assert "secret" not in encoded and "report_id" not in encoded and "inn" not in encoded


def test_running_or_changing_snapshot_never_passes_and_never_force_kills() -> None:
    container = Container([True])
    database = Database(
        [snapshot(running=1), *(snapshot(queued=value) for value in range(20))]
    )
    with pytest.raises(drain.LegacyDrainError, match="deadline"):
        execute(container, database, policy(deadline_seconds=6))
    assert not any("KILL" in event[0] and event[0] != "SIGTERM" for event in container.events if isinstance(event, tuple))


def test_live_worker_deadline_does_not_query_database() -> None:
    container = Container([False])
    database = Database([])
    with pytest.raises(drain.LegacyDrainError, match="deadline"):
        execute(container, database, policy(deadline_seconds=6))
    assert database.calls == 0


def test_policy_covers_shutdown_and_provider_bounds() -> None:
    with pytest.raises(drain.LegacyDrainError, match="shorter"):
        policy(deadline_seconds=3, provider_timeout_seconds=4)
    with pytest.raises(drain.LegacyDrainError, match="fit"):
        policy(deadline_seconds=4, stable_interval_seconds=4)


def test_psql_secret_is_environment_only(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgresql://user:secret@db/app"

    def run(arguments, **kwargs):
        assert database_url not in arguments
        assert kwargs["env"]["PGDATABASE"] == database_url
        return SimpleNamespace(returncode=0, stdout=json.dumps(drain.asdict(snapshot())) + "\n")

    monkeypatch.setattr(drain.subprocess, "run", run)
    assert drain.PsqlAggregateAdapter(database_url).snapshot().running == 0


def test_source_has_only_old_schema_aggregate_and_no_force_path() -> None:
    source = MODULE.read_text(encoding="utf-8")
    assert "company_report_jobs" in source
    assert "company_card_narrative" not in source
    assert "--force" not in source and "SIGKILL" not in source and '"stop"' not in source
    assert '["kill", "--signal=TERM", identity.container_id]' in source
    assert "worker_token" not in source and "report_id" not in source
