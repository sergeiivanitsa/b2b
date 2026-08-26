from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa


_MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0018_company_card_v2_arbitration.py"
)


class _ScalarResult:
    def __init__(self, value: bool) -> None:
        self._value = value

    def scalar(self) -> bool:
        return self._value


class _FakeBind:
    def __init__(self, report_exists: bool, job_exists: bool) -> None:
        self._exists = iter((report_exists, job_exists))
        self.statements: list[str] = []
        self.parameters: list[dict[str, object]] = []

    def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        self.parameters.append(dict(statement.compile().params))
        if sql.startswith("SELECT EXISTS"):
            return _ScalarResult(next(self._exists))
        return _ScalarResult(False)


class _FakeOp:
    def __init__(self, bind: _FakeBind) -> None:
        self.bind = bind
        self.events: list[tuple[str, object, object | None]] = []

    def get_bind(self) -> _FakeBind:
        return self.bind

    def add_column(self, table: str, column) -> None:
        self.events.append(("add_column", table, column))

    def create_check_constraint(self, name: str, table: str, condition: str) -> None:
        self.events.append(("create_check", (name, table), condition))

    def drop_constraint(self, name: str, table: str, *, type_: str) -> None:
        self.events.append(("drop_check", (name, table), type_))

    def drop_column(self, table: str, column: str) -> None:
        self.events.append(("drop_column", table, column))


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("iteration24_migration_contract", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_guard_locks_in_order_and_uses_independent_exists(monkeypatch) -> None:
    migration = _load_migration()
    bind = _FakeBind(False, False)
    monkeypatch.setattr(migration, "op", _FakeOp(bind))

    migration._guard_active_h2_lineage()

    assert bind.statements[:2] == [
        "LOCK TABLE company_reports IN SHARE ROW EXCLUSIVE MODE",
        "LOCK TABLE company_report_jobs IN SHARE ROW EXCLUSIVE MODE",
    ]
    report_sql, job_sql = bind.statements[2:]
    assert "FROM company_reports" in report_sql
    assert "lifecycle_status = 'pending'" in report_sql
    assert "report_version = '3'" in report_sql
    assert "FROM company_report_jobs" not in report_sql
    assert "JOIN" not in report_sql.upper()
    assert "FROM company_report_jobs" in job_sql
    assert "state IN ('queued', 'running')" in job_sql
    assert "FROM company_reports" not in job_sql
    assert "JOIN" not in job_sql.upper()
    assert bind.parameters[2:] == [
        {
            "profile": "company_card_v2_writer_v3",
            "contract": "company_public_h2_v1",
        },
        {
            "profile": "company_card_v2_writer_v3",
            "contract": "company_public_h2_v1",
        },
    ]
    assert "rollout_generation > 0" in report_sql
    assert "rollout_generation > 0" in job_sql


@pytest.mark.parametrize(
    ("report_exists", "job_exists"),
    [(True, False), (False, True), (True, True)],
)
def test_migration_guard_aborts_before_ddl_on_either_active_side(
    monkeypatch,
    report_exists: bool,
    job_exists: bool,
) -> None:
    migration = _load_migration()
    bind = _FakeBind(report_exists, job_exists)
    fake_op = _FakeOp(bind)
    monkeypatch.setattr(migration, "op", fake_op)

    with pytest.raises(RuntimeError, match="^iteration24_active_h2_lineage_ambiguous$"):
        migration.upgrade()

    assert len(bind.statements) == 4
    assert fake_op.events == []


def test_migration_adds_and_downgrades_exact_decision_shape(monkeypatch) -> None:
    migration = _load_migration()
    assert migration.revision == "0018_company_card_v2_arbitration"
    assert migration.down_revision == "0017_company_card_v2_ai_narrative"

    bind = _FakeBind(False, False)
    fake_op = _FakeOp(bind)
    monkeypatch.setattr(migration, "op", fake_op)

    migration.upgrade()

    added = [event for event in fake_op.events if event[0] == "add_column"]
    checks = [event for event in fake_op.events if event[0] == "create_check"]
    assert [(table, column.name) for _, table, column in added] == [
        ("company_reports", "arbitration_collection_enabled"),
        ("company_reports", "arbitration_mask_key_id"),
        ("company_report_jobs", "arbitration_collection_enabled"),
        ("company_report_jobs", "arbitration_mask_key_id"),
    ]
    for _, _, enabled in added[::2]:
        assert isinstance(enabled.type, sa.Boolean)
        assert enabled.nullable is False
        assert enabled.server_default is not None
        assert str(enabled.server_default.arg) == "false"
    for _, _, key_id in added[1::2]:
        assert isinstance(key_id.type, sa.String)
        assert key_id.type.length == 32
        assert key_id.nullable is True
        assert key_id.server_default is None
    assert [(name, table) for _, (name, table), _ in checks] == [
        ("company_reports_arbitration_decision", "company_reports"),
        ("company_report_jobs_arbitration_decision", "company_report_jobs"),
    ]
    assert all(
        condition == "arbitration_collection_enabled OR arbitration_mask_key_id IS NULL"
        for _, _, condition in checks
    )

    fake_op.events.clear()
    migration.downgrade()
    assert fake_op.events == [
        (
            "drop_check",
            ("company_report_jobs_arbitration_decision", "company_report_jobs"),
            "check",
        ),
        ("drop_column", "company_report_jobs", "arbitration_mask_key_id"),
        ("drop_column", "company_report_jobs", "arbitration_collection_enabled"),
        (
            "drop_check",
            ("company_reports_arbitration_decision", "company_reports"),
            "check",
        ),
        ("drop_column", "company_reports", "arbitration_mask_key_id"),
        ("drop_column", "company_reports", "arbitration_collection_enabled"),
    ]
