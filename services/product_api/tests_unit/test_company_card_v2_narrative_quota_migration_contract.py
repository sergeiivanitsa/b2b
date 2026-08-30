from __future__ import annotations

import importlib.util
from pathlib import Path


_MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0020_company_card_narrative_quota_mode.py"
)


class _Scalar:
    def __init__(self, value: bool) -> None:
        self.value = value

    def scalar(self) -> bool:
        return self.value


class _Bind:
    def __init__(self, *, unlimited: bool = False) -> None:
        self.unlimited = unlimited
        self.statements: list[str] = []

    def execute(self, statement):
        rendered = str(statement)
        self.statements.append(rendered)
        return _Scalar(self.unlimited if rendered.startswith("SELECT") else False)


class _Op:
    def __init__(self, bind: _Bind) -> None:
        self.bind = bind
        self.events: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def get_bind(self):
        return self.bind

    def __getattr__(self, name: str):
        def record(*args, **kwargs):
            self.events.append((name, args, kwargs))

        return record


def _load():
    spec = importlib.util.spec_from_file_location("narrative_quota_migration", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_adds_explicit_quota_mode_and_closed_shape(monkeypatch) -> None:
    migration = _load()
    operation = _Op(_Bind())
    monkeypatch.setattr(migration, "op", operation)

    migration.upgrade()

    assert migration.revision == "0020_company_card_narrative_quota_mode"
    assert migration.down_revision == "0019_company_card_v2_rollout_control"
    assert [event[0] for event in operation.events] == [
        "add_column",
        "create_check_constraint",
    ]
    quota_column = operation.events[0][1][1]
    assert quota_column.name == "quota_mode"
    assert quota_column.nullable is False
    assert str(quota_column.server_default.arg) == "bounded"
    quota_shape = str(operation.events[1][1][2])
    assert "quota_mode IN ('bounded', 'unlimited')" in quota_shape
    assert "daily_limit = 0 AND monthly_limit = 0" in quota_shape
    assert "concurrency_limit > 0" in quota_shape


def test_downgrade_locks_and_refuses_to_discard_unlimited_mode(monkeypatch) -> None:
    migration = _load()
    bind = _Bind(unlimited=True)
    operation = _Op(bind)
    monkeypatch.setattr(migration, "op", operation)

    try:
        migration.downgrade()
    except RuntimeError as exc:
        assert str(exc) == "refuse to discard unlimited narrative quota mode"
    else:  # pragma: no cover - guard contract
        raise AssertionError("downgrade unexpectedly discarded unlimited mode")

    assert bind.statements[0].startswith(
        "LOCK TABLE company_card_narrative_runtime_control"
    )
    assert "quota_mode <> 'bounded'" in bind.statements[1]
    assert operation.events == []
