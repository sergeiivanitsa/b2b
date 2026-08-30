"""Adapter-only worker drain contract tests; no Docker or database is touched."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "deploy/product_api/worker_drain.py"
SPEC = importlib.util.spec_from_file_location("worker_drain", MODULE)
assert SPEC and SPEC.loader
drain = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = drain
SPEC.loader.exec_module(drain)


def _identity(name: str, marker: str):
    container_marker = "c" if marker == "a" else "d"
    return drain.ContainerIdentity(name, container_marker * 64, f"sha256:{marker * 64}")


def _snapshot(**changes):
    values = {
        "db_clock": "2026-08-28 00:00:00+00",
        "report_queued": 2,
        "report_succeeded": 3,
        "report_failed": 1,
        "report_running": 0,
        "outbox_pending": 2,
        "outbox_processed": 3,
        "outbox_terminal": 1,
        "outbox_leased": 0,
        "narrative_ready": 2,
        "narrative_pre_dispatch_failed": 1,
        "narrative_finalized": 3,
        "narrative_fallback_finalized": 1,
        "narrative_ambiguous_timeout": 0,
        "narrative_invalid_output": 0,
        "narrative_active": 0,
        "runtime_leased": 0,
        "reservation_released": 2,
        "reservation_consumed": 4,
        "reservation_reserved": 0,
        "unsafe_dispatch": 0,
    }
    values.update(changes)
    return drain.AggregateSnapshot(**values)


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Containers:
    def __init__(self, exited):
        self.identities = (_identity("report-worker", "a"), _identity("narrative-worker", "b"))
        self.exited = iter(exited)
        self.events = []
        self._last = False

    def capture(self):
        self.events.append("capture")
        return self.identities

    def disable_restart(self, identity):
        self.events.append(("restart-none", identity.name))

    def send_sigterm(self, identity):
        self.events.append(("SIGTERM", identity.name))

    def all_exited(self, identities):
        assert identities == self.identities
        try:
            self._last = next(self.exited)
        except StopIteration:
            pass
        return self._last


class Database:
    def __init__(self, snapshots):
        self.snapshots = iter(snapshots)
        self._last = None
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        try:
            self._last = next(self.snapshots)
        except StopIteration:
            pass
        assert self._last is not None
        return self._last


def _policy(**changes):
    values = {
        "deadline_seconds": 12,
        "shutdown_grace_seconds": 3,
        "provider_timeout_seconds": 3,
        "gateway_timeout_seconds": 3,
        "stable_interval_seconds": 2,
        "poll_interval_seconds": 1,
    }
    values.update(changes)
    return drain.DrainPolicy(**values)


def _run(containers, database, policy=None):
    clock = Clock()
    return drain.drain_workers(
        containers,
        database,
        policy or _policy(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


def test_idle_or_queued_pending_work_drains_after_two_stable_snapshots() -> None:
    containers = Containers([True, True, True])
    database = Database([_snapshot(), _snapshot(), _snapshot()])
    result = _run(containers, database)
    assert result.outcome == "drained"
    assert database.calls == 3
    assert containers.events == [
        "capture",
        ("restart-none", "report-worker"),
        ("restart-none", "narrative-worker"),
        ("SIGTERM", "report-worker"),
        ("SIGTERM", "narrative-worker"),
    ]
    output = json.loads(result.privacy_safe_json())
    assert output["aggregate"]["report_queued"] == 2
    assert "db_clock" not in output["aggregate"]
    assert output["db_clock"] == "2026-08-28 00:00:00+00"
    assert output["report_worker_container"] == "c" * 64
    assert output["narrative_worker_container"] == "d" * 64
    serialized = result.privacy_safe_json()
    assert "report-worker" not in serialized
    assert "narrative-worker" not in serialized


def test_graceful_completion_waits_for_process_exit_and_all_active_predicates() -> None:
    containers = Containers([False, False, True, True, True, True])
    database = Database([
        _snapshot(report_running=1),
        _snapshot(narrative_active=1, runtime_leased=1, reservation_reserved=1),
        _snapshot(),
        _snapshot(),
    ])
    assert _run(containers, database).outcome == "drained"
    assert database.calls == 5


@pytest.mark.parametrize(
    "unsafe",
    (
        {"report_running": 1},
        {"outbox_leased": 1},
        {"narrative_active": 1},
        {"runtime_leased": 1},
        {"reservation_reserved": 1},
        {"unsafe_dispatch": 1},
    ),
)
def test_every_unsafe_db_predicate_stops_at_deadline_without_force_kill(unsafe) -> None:
    containers = Containers([True])
    database = Database([_snapshot(**unsafe)])
    with pytest.raises(drain.DrainError, match="deadline"):
        _run(containers, database, _policy(deadline_seconds=6))
    assert all(event[0] != "SIGKILL" for event in containers.events if isinstance(event, tuple))


def test_live_process_at_deadline_never_queries_db_or_escalates_signal() -> None:
    containers = Containers([False])
    database = Database([])
    with pytest.raises(drain.DrainError, match="deadline"):
        _run(containers, database, _policy(deadline_seconds=6))
    assert database.calls == 0
    assert [event for event in containers.events if isinstance(event, tuple) and event[0] == "SIGTERM"]
    assert not any("KILL" in event[0] and event[0] != "SIGTERM" for event in containers.events if isinstance(event, tuple))


def test_changing_safe_counts_never_satisfy_stability_window() -> None:
    containers = Containers([True])
    database = Database([_snapshot(report_queued=value) for value in range(20)])
    with pytest.raises(drain.DrainError, match="deadline"):
        _run(containers, database, _policy(deadline_seconds=6))


def test_deadline_must_cover_grace_provider_and_gateway_before_adapters_run() -> None:
    with pytest.raises(drain.DrainError, match="shorter"):
        _policy(deadline_seconds=3, gateway_timeout_seconds=4)
    with pytest.raises(drain.DrainError, match="fit"):
        _policy(deadline_seconds=4, stable_interval_seconds=4)
    assert _policy(shutdown_grace_seconds=0).shutdown_grace_seconds == 0


def test_container_settings_are_exact_json_without_shell_evaluation() -> None:
    names = drain._REQUIRED_SETTINGS
    rows = [
        "IGNORED=value",
        "DATABASE_URL=postgresql://user:secret@db/app",
        "COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS=30",
        "DATANEWTON_TIMEOUT_SECONDS=10",
        "COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS=20",
    ]
    settings = drain._parse_container_environment(json.dumps(rows), names)
    assert set(settings) == names
    assert drain._numeric_setting(settings, "DATANEWTON_TIMEOUT_SECONDS") == 10
    with pytest.raises(drain.DrainError, match="incomplete"):
        drain._parse_container_environment(json.dumps(rows[:-1]), names)
    with pytest.raises(drain.DrainError, match="invalid"):
        drain._parse_container_environment(json.dumps([*rows, rows[1]]), names)


def test_psql_connection_secret_is_environment_only(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgresql://user:secret@db/app"

    def run(arguments, **kwargs):
        assert database_url not in arguments
        assert kwargs["env"]["PGDATABASE"] == database_url
        return SimpleNamespace(returncode=0, stdout=json.dumps(drain.asdict(_snapshot())) + "\n")

    monkeypatch.setattr(drain.subprocess, "run", run)
    snapshot = drain.PsqlAggregateAdapter(database_url).snapshot()
    assert snapshot.report_running == 0


def test_aggregate_sql_uses_migrated_company_report_job_state_column() -> None:
    report_cte = drain._AGGREGATE_SQL.split("), outbox AS (", 1)[0]
    assert "status" not in report_cte
    for state in ("queued", "succeeded", "failed", "running"):
        assert f"FILTER (WHERE state = '{state}')" in report_cte


def test_validate_only_is_sha_and_database_bound_without_worker_mutation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[object] = []
    identities = (_identity("report-worker", "a"), _identity("narrative-worker", "b"))
    settings = {
        "DATABASE_URL": "postgresql+asyncpg://user:secret@db/app",
        "COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS": "30",
        "DATANEWTON_TIMEOUT_SECONDS": "10",
        "COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS": "20",
    }

    class ReadOnlyContainers:
        def __init__(self, names):
            assert names == ["report-worker", "narrative-worker"]

        def capture(self):
            events.append("capture")
            return identities

        def environment(self, container_id, names):
            assert container_id in {"report-worker", "narrative-worker"}
            assert names == drain._REQUIRED_SETTINGS
            events.append(("environment", container_id))
            return settings

        def disable_restart(self, identity):
            raise AssertionError("validate-only changed restart policy")

        def send_sigterm(self, identity):
            raise AssertionError("validate-only sent a signal")

    class ReadOnlyDatabase:
        def __init__(self, database_url):
            assert database_url == settings["DATABASE_URL"]

        def snapshot(self):
            events.append("snapshot")
            return _snapshot()

    monkeypatch.setattr(drain, "DockerCliAdapter", ReadOnlyContainers)
    monkeypatch.setattr(drain, "PsqlAggregateAdapter", ReadOnlyDatabase)
    monkeypatch.setattr(
        drain,
        "drain_workers",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("validate-only entered worker drain")
        ),
    )
    release_sha = "e" * 40
    assert drain.main([
        "--container", "report-worker",
        "--container", "narrative-worker",
        "--settings-container", "report-worker",
        "--deadline-seconds", "300",
        "--stable-interval-seconds", "10",
        "--validate-only",
        "--release-sha", release_sha,
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["outcome"] == "validated"
    assert output["release_sha"] == release_sha
    assert output["database_target_sha256"] == drain.sha256(
        settings["DATABASE_URL"].encode("utf-8")
    ).hexdigest()
    assert "secret" not in json.dumps(output)
    assert events == [
        "capture",
        ("environment", "report-worker"),
        ("environment", "report-worker"),
        ("environment", "narrative-worker"),
        "snapshot",
    ]


def test_validate_only_rejects_unsafe_snapshot_before_worker_mutation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    identities = (_identity("report-worker", "a"), _identity("narrative-worker", "b"))
    settings = {
        "DATABASE_URL": "postgresql://user:secret@db/app",
        "COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS": "30",
        "DATANEWTON_TIMEOUT_SECONDS": "10",
        "COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS": "20",
    }

    class ContainersWithoutMutation:
        def __init__(self, names):
            pass

        def capture(self):
            return identities

        def environment(self, container_id, names):
            return settings

    class UnsafeDatabase:
        def __init__(self, database_url):
            pass

        def snapshot(self):
            return _snapshot(report_running=1)

    monkeypatch.setattr(drain, "DockerCliAdapter", ContainersWithoutMutation)
    monkeypatch.setattr(drain, "PsqlAggregateAdapter", UnsafeDatabase)
    monkeypatch.setattr(
        drain,
        "drain_workers",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unsafe preflight entered worker drain")
        ),
    )
    assert drain.main([
        "--container", "report-worker",
        "--container", "narrative-worker",
        "--settings-container", "report-worker",
        "--deadline-seconds", "300",
        "--stable-interval-seconds", "10",
        "--validate-only",
        "--release-sha", "e" * 40,
    ]) == 2
    assert "unsafe for deployment preflight" in capsys.readouterr().err


def test_regular_main_executes_exact_snapshot_before_entering_drain(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    identities = (_identity("report-worker", "a"), _identity("narrative-worker", "b"))
    settings = {
        "DATABASE_URL": "postgresql://user:secret@db/app",
        "COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS": "30",
        "DATANEWTON_TIMEOUT_SECONDS": "10",
        "COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS": "20",
    }

    class Containers:
        def __init__(self, names):
            pass

        def capture(self):
            events.append("capture")
            return identities

        def environment(self, container_id, names):
            return settings

    class Database:
        def __init__(self, database_url):
            pass

        def snapshot(self):
            events.append("snapshot")
            return _snapshot()

    def run_drain(containers, database, policy, *, identities):
        assert identities == (
            _identity("report-worker", "a"),
            _identity("narrative-worker", "b"),
        )
        events.append("drain")
        return drain.DrainResult(
            "drained", 1, _snapshot(), "c" * 64, "d" * 64,
            f"sha256:{'a' * 64}", f"sha256:{'b' * 64}",
        )

    monkeypatch.setattr(drain, "DockerCliAdapter", Containers)
    monkeypatch.setattr(drain, "PsqlAggregateAdapter", Database)
    monkeypatch.setattr(drain, "drain_workers", run_drain)
    assert drain.main([
        "--container", "report-worker",
        "--container", "narrative-worker",
        "--settings-container", "report-worker",
        "--deadline-seconds", "300",
        "--stable-interval-seconds", "10",
    ]) == 0
    assert events == ["capture", "snapshot", "drain"]
    assert json.loads(capsys.readouterr().out)["outcome"] == "drained"


def test_regular_main_aggregate_sql_failure_stops_before_worker_mutation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = {
        "DATABASE_URL": "postgresql://user:secret@db/app",
        "COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS": "30",
        "DATANEWTON_TIMEOUT_SECONDS": "10",
        "COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS": "20",
    }

    class Containers:
        def __init__(self, names):
            pass

        def capture(self):
            return (_identity("report-worker", "a"), _identity("narrative-worker", "b"))

        def environment(self, container_id, names):
            return settings

        def disable_restart(self, identity):
            raise AssertionError("SQL failure changed restart policy")

        def send_sigterm(self, identity):
            raise AssertionError("SQL failure sent a signal")

    class FailingDatabase:
        def __init__(self, database_url):
            pass

        def snapshot(self):
            raise drain.DrainError("worker aggregate database query failed")

    monkeypatch.setattr(drain, "DockerCliAdapter", Containers)
    monkeypatch.setattr(drain, "PsqlAggregateAdapter", FailingDatabase)
    monkeypatch.setattr(
        drain,
        "drain_workers",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("SQL failure entered worker drain")
        ),
    )
    assert drain.main([
        "--container", "report-worker",
        "--container", "narrative-worker",
        "--settings-container", "report-worker",
        "--deadline-seconds", "300",
        "--stable-interval-seconds", "10",
    ]) == 2
    assert "aggregate database query failed" in capsys.readouterr().err


def test_deploy_result_binds_database_without_exposing_connection_secret() -> None:
    database_url = "postgresql+asyncpg://user:secret@db.example/app"
    result = drain.DrainResult(
        "drained", 1, _snapshot(), "c" * 64, "d" * 64,
        f"sha256:{'a' * 64}", f"sha256:{'b' * 64}",
    )
    encoded = drain.deployment_result_json(result, database_url)
    data = json.loads(encoded)
    assert data["database_target_sha256"] == drain.sha256(database_url.encode("utf-8")).hexdigest()
    assert database_url not in encoded and "secret" not in encoded and "db.example" not in encoded


def test_cli_and_sql_contract_have_no_force_path_or_row_identity_output() -> None:
    source = MODULE.read_text(encoding="utf-8")
    assert "--force" not in source
    assert "SIGKILL" not in source
    assert '"stop"' not in source
    assert "source " not in source
    assert "--settings-container" in source
    assert "docker\", \"kill\", \"--signal=TERM" not in source  # assembled as exact args, not shell
    assert "SELECT json_build_object" in source
    output = drain.DrainResult(
        "drained",
        1,
        _snapshot(),
        "c" * 64,
        "d" * 64,
        f"sha256:{'a' * 64}",
        f"sha256:{'b' * 64}",
    ).privacy_safe_json()
    for forbidden in ("report_id", "generation_identity", "gateway_dispatch_id'", "canonical_path", "inn"):
        assert forbidden not in output
