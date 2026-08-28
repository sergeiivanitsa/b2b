from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


_MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0019_company_card_v2_rollout_control.py"
)


class _Scalar:
    def __init__(self, value: bool = False) -> None:
        self._value = value

    def scalar(self) -> bool:
        return self._value


class _Bind:
    def __init__(self, values: tuple[bool, ...] = ()) -> None:
        self._values = iter(values)
        self.statements: list[str] = []

    def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        return _Scalar(next(self._values, False) if sql.startswith("SELECT") else False)


class _Op:
    def __init__(self, bind: _Bind) -> None:
        self.bind = bind
        self.events: list[tuple[str, object, object]] = []

    def get_bind(self):
        return self.bind

    def f(self, name: str) -> str:
        return name

    def __getattr__(self, name: str):
        def record(*args, **kwargs):
            self.events.append((name, args, kwargs))

        return record


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("iteration25_migration", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_is_append_only_and_replaces_subject_bound_journal_fk(monkeypatch) -> None:
    migration = _load()
    bind = _Bind((False,))
    operation = _Op(bind)
    monkeypatch.setattr(migration, "op", operation)

    migration.upgrade()

    assert migration.revision == "0019_company_card_v2_rollout_control"
    assert migration.down_revision == "0018_company_card_v2_arbitration"
    assert "a.subject_id <> j.subject_id" in bind.statements[0]
    names = [event[0] for event in operation.events]
    assert "create_table" in names
    assert names.count("add_column") == 4
    assert "drop_table" not in names
    assert (
        "create_unique_constraint",
        (
            "uq_company_report_presentation_assignment_id_subject",
            "company_report_presentation_assignments",
            ["id", "subject_id"],
        ),
        {},
    ) in operation.events
    assignment_fks = [
        event
        for event in operation.events
        if event[0] == "create_foreign_key"
        and event[1][0]
        == "fk_company_report_presentation_journal_assignment_subject"
    ]
    assert len(assignment_fks) == 1
    assert assignment_fks[0][1][3:] == (
        ["assignment_id", "subject_id"],
        ["id", "subject_id"],
    )
    assert assignment_fks[0][2]["ondelete"] == "CASCADE"


def test_downgrade_locks_in_exact_order_before_guard_and_ddl(monkeypatch) -> None:
    migration = _load()
    bind = _Bind((False, False, False))
    operation = _Op(bind)
    monkeypatch.setattr(migration, "op", operation)

    migration.downgrade()

    assert bind.statements[:4] == [
        "LOCK TABLE company_card_v2_rollout_decisions IN SHARE ROW EXCLUSIVE MODE",
        "LOCK TABLE company_report_presentation_assignments IN SHARE ROW EXCLUSIVE MODE",
        "LOCK TABLE company_report_presentation_pins IN SHARE ROW EXCLUSIVE MODE",
        "LOCK TABLE company_report_presentation_assignment_journal IN SHARE ROW EXCLUSIVE MODE",
    ]
    assert "projection_scope IS NOT NULL" in bind.statements[4]
    assert "decision_id IS NOT NULL" in bind.statements[5]
    assert "company_card_v2_rollout_decisions" in bind.statements[6]
    assert operation.events[0][0] == "drop_constraint"


def test_downgrade_refuses_before_any_ddl_for_each_new_data_class(monkeypatch) -> None:
    for values in ((True,), (False, True), (False, False, True)):
        migration = _load()
        bind = _Bind(values)
        operation = _Op(bind)
        monkeypatch.setattr(migration, "op", operation)

        try:
            migration.downgrade()
        except RuntimeError as exc:
            assert str(exc) == "iteration25_rollout_control_data_present"
        else:  # pragma: no cover - an unsafe downgrade must never proceed
            raise AssertionError("unsafe downgrade was accepted")
        assert operation.events == []


def test_pin_shapes_keep_legacy_rows_and_require_resolved_active_binding() -> None:
    migration = _load()
    shape = migration._PIN_SHAPE_0019

    assert "projection_scope IS NULL" in shape
    assert "projection_scope = 'staged_publication'" in shape
    assert "projection_scope = 'active_publication'" in shape
    assert "canonical_path IS NOT NULL AND published_lastmod IS NOT NULL" in shape
    assert "narrative_binding_status = 'resolved'" in shape
    assert "projection_digest ~ '^[0-9a-f]{64}$'" in shape


def test_journal_audit_shape_requires_all_or_none_fields() -> None:
    migration = _load()
    shape = migration._JOURNAL_AUDIT_SHAPE

    assert "decision_id IS NULL AND decision_digest IS NULL AND reason_code IS NULL" in shape
    assert "decision_id IS NOT NULL" in shape
    assert "decision_digest IS NOT NULL" in shape
    assert "reason_code IS NOT NULL" in shape


def test_global_decision_shape_requires_indexable_ga_and_closed_rollback() -> None:
    migration = _load()
    shape = migration._DECISION_SHAPE

    assert "stage <> 'ga' OR h2_indexable = true" in shape
    assert "action = 'rollback' AND stage = 'emergency_rollback'" in shape
    assert "target_contract = 'company_public_h1_v1' AND h2_indexable = false" in shape
