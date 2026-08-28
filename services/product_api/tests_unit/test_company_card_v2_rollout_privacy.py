from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from product_api.company_reports.company_card_v2.canonical_json import (
    canonical_json_bytes,
)
from product_api.company_reports.company_card_v2.rollout import (
    RolloutExecutionError,
    RolloutExecutionResult,
    RolloutRuntimeConfig,
    RolloutSigterm,
    RolloutTargetResult,
    _cleanup_rollout_connection,
    _read_rollout_decision_binding_matches,
    _runtime_from_environment,
    main,
    run_rollout_mutation,
)
from product_api.company_reports.company_card_v2.rollout_models import (
    parse_rollout_decision,
)
from product_api.company_reports.persistence.presentations import (
    PresentationAssignmentConflict,
    RolloutAssignmentCommand,
    bind_rollout_decision,
)


def _activate():
    return parse_rollout_decision(
        canonical_json_bytes(
            {
                "schema_version": "company_card_v2_rollout_decision_v1",
                "decision_id": "00000000-0000-0000-0000-000000000000",
                "authorization_reference": "P3-test",
                "release_commit": "a" * 40,
                "rollout_generation": 7,
                "action": "activate",
                "stage": "allowlist",
                "target_contract": "company_public_h2_v1",
                "h2_indexable": False,
                "allowlist_inns": ["7701234567"],
                "percentage_basis_points": 0,
                "maximum_batch_size": 1,
                "observation_window_seconds": 60,
                "abort_policy_reference": "P4-test",
                "targets": [
                    {
                        "subject_id": "00000000-0000-0000-0000-000000000001",
                        "inn": "7701234567",
                        "expected_assignment_generation": 0,
                        "expected_current_contract": None,
                        "expected_current_pin_generation": None,
                        "source_h2_pin_generation": 1,
                        "expected_active_h2_pin_generation": 2,
                        "expected_active_projection_digest": "b" * 64,
                        "h1_rollback_pin_generation": 1,
                    }
                ],
            }
        )
    )


@pytest.mark.asyncio
async def test_read_only_plan_rejects_conflicting_global_decision_binding() -> None:
    parsed = _activate()
    decision = parsed.decision

    class Rows:
        def __init__(self, values):
            self.values = values

        def all(self):
            return self.values

    class Session:
        def __init__(self, values):
            self.values = values

        async def scalars(self, _statement):
            return Rows(self.values)

    exact = SimpleNamespace(
        decision_id=decision.decision_uuid,
        decision_digest=parsed.decision_digest,
        schema_version=decision.schema_version,
        release_commit=decision.release_commit,
        action=decision.action,
        stage=decision.stage,
        target_contract=decision.target_contract,
        h2_indexable=decision.h2_indexable,
        target_count=len(decision.targets),
    )

    assert await _read_rollout_decision_binding_matches(Session([]), parsed)
    assert await _read_rollout_decision_binding_matches(Session([exact]), parsed)
    conflict = SimpleNamespace(**{**vars(exact), "release_commit": "f" * 40})
    assert not await _read_rollout_decision_binding_matches(
        Session([conflict]), parsed
    )


def test_runtime_allowlist_matches_settings_csv_semantics(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/test")
    monkeypatch.delenv("COMPANY_CARD_V2_ALLOWLIST_INNS", raising=False)
    assert _runtime_from_environment().allowlist_inns == ()

    monkeypatch.setenv(
        "COMPANY_CARD_V2_ALLOWLIST_INNS",
        " 500100732259, 7701234567 ",
    )
    assert _runtime_from_environment().allowlist_inns == (
        "500100732259",
        "7701234567",
    )


@pytest.mark.parametrize(
    "value",
    (
        "7701234567,500100732259",
        "7701234567,7701234567",
        "[]",
        "770123456X",
    ),
)
def test_runtime_allowlist_rejects_noncanonical_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/test")
    monkeypatch.setenv("COMPANY_CARD_V2_ALLOWLIST_INNS", value)
    with pytest.raises(RolloutExecutionError, match="rollout_configuration_invalid"):
        _runtime_from_environment()


def test_public_result_and_repr_do_not_disclose_target_identity() -> None:
    result = RolloutExecutionResult(
        decision_id="00000000-0000-0000-0000-000000000000",
        decision_digest="d" * 64,
        mode="apply",
        results=(RolloutTargetResult(1, "presentation_assignment_conflict"),),
        stopped=True,
    )
    config = RolloutRuntimeConfig(
        database_url="postgresql+asyncpg://operator:secret@localhost/private",
        product_release_commit="a" * 40,
        rollout_generation=7,
        allowlist_inns=("7701234567",),
        percentage_basis_points=0,
    )

    rendered = repr(result) + repr(config) + str(result.public_json())
    assert "7701234567" not in rendered
    assert "operator" not in rendered
    assert "secret" not in rendered
    assert result.public_json()["targets"] == [
        {"ordinal": 1, "code": "presentation_assignment_conflict"}
    ]


def test_h2_cas_command_cannot_omit_exact_source_pin() -> None:
    values = {
        "decision_id": UUID("00000000-0000-0000-0000-000000000000"),
        "decision_digest": "d" * 64,
        "schema_version": "company_card_v2_rollout_decision_v1",
        "release_commit": "a" * 40,
        "action": "activate",
        "stage": "allowlist",
        "h2_indexable": False,
        "target_count": 1,
        "reason_code": "activate_allowlist",
        "subject_id": UUID("00000000-0000-0000-0000-000000000001"),
        "inn": "7701234567",
        "expected_assignment_generation": 0,
        "expected_current_contract": None,
        "expected_current_pin_generation": None,
        "expected_rollout_generation": 1,
        "target_contract": "company_public_h2_v1",
        "target_pin_generation": 2,
        "h1_rollback_pin_generation": 1,
        "expected_target_projection_digest": "e" * 64,
    }

    with pytest.raises(ValueError, match="H2 rollout assignment command"):
        RolloutAssignmentCommand(**values)
    assert RolloutAssignmentCommand(
        **values,
        source_h2_pin_generation=1,
    ).source_h2_pin_generation == 1


@pytest.mark.asyncio
async def test_decision_unique_insert_race_reselects_inside_usable_transaction() -> None:
    decision_id = UUID("00000000-0000-0000-0000-000000000000")
    binding = SimpleNamespace(
        decision_id=decision_id,
        decision_digest="d" * 64,
        schema_version="company_card_v2_rollout_decision_v1",
        release_commit="a" * 40,
        action="activate",
        stage="allowlist",
        target_contract="company_public_h2_v1",
        h2_indexable=False,
        target_count=1,
    )

    class Scalars:
        def __init__(self, values) -> None:
            self.values = values

        def all(self):
            return self.values

    class Savepoint:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

    class Session:
        def __init__(self) -> None:
            self.reads = 0
            self.added = None

        async def scalars(self, statement):
            self.reads += 1
            return Scalars([] if self.reads == 1 else [binding])

        def begin_nested(self):
            return Savepoint()

        def add(self, value) -> None:
            self.added = value

        async def flush(self) -> None:
            raise IntegrityError("insert", {}, RuntimeError("unique race"))

    session = Session()
    result = await bind_rollout_decision(
        session,
        decision_id=decision_id,
        decision_digest="d" * 64,
        schema_version="company_card_v2_rollout_decision_v1",
        release_commit="a" * 40,
        action="activate",
        stage="allowlist",
        target_contract="company_public_h2_v1",
        h2_indexable=False,
        target_count=1,
    )

    assert result is binding
    assert session.reads == 2


@pytest.mark.asyncio
async def test_decision_digest_collision_is_closed() -> None:
    class Scalars:
        def all(self):
            return [
                SimpleNamespace(
                    decision_id=UUID("00000000-0000-0000-0000-000000000002"),
                    decision_digest="d" * 64,
                )
            ]

    class Session:
        async def scalars(self, statement):
            return Scalars()

    with pytest.raises(PresentationAssignmentConflict, match="identity conflicts"):
        await bind_rollout_decision(
            Session(),
            decision_id=UUID("00000000-0000-0000-0000-000000000001"),
            decision_digest="d" * 64,
            schema_version="company_card_v2_rollout_decision_v1",
            release_commit="a" * 40,
            action="activate",
            stage="allowlist",
            target_contract="company_public_h2_v1",
            h2_indexable=False,
            target_count=1,
        )


@pytest.mark.asyncio
async def test_sigterm_unlocks_and_closes_before_controlled_termination(
    monkeypatch,
) -> None:
    parsed = _activate()
    events: list[str] = []

    class Transaction:
        def __init__(self, connection) -> None:
            self.connection = connection

        async def __aenter__(self):
            assert not self.connection.transaction
            self.connection.transaction = True
            events.append("begin")
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            self.connection.transaction = False
            events.append("rollback" if exc_type else "commit")

    class Connection:
        invalidated = False
        closed = False
        transaction = False

        def begin(self):
            return Transaction(self)

        async def get_raw_connection(self):
            return SimpleNamespace(driver_connection=SimpleNamespace())

        async def execute(self, statement, parameters):
            events.append("acquire")
            return SimpleNamespace(one=lambda: (4321, True))

        async def scalar(self, statement, parameters=None):
            sql = str(statement)
            if "pg_advisory_unlock" in sql:
                events.append("unlock")
            else:
                events.append("guard")
            return True

        def in_transaction(self) -> bool:
            return self.transaction

        async def rollback(self) -> None:
            self.transaction = False
            events.append("outer_rollback")

        async def close(self) -> None:
            self.closed = True
            events.append("close")

    class Engine:
        def __init__(self) -> None:
            self.connection = Connection()

        async def connect(self):
            events.append("connect")
            return self.connection

        async def dispose(self) -> None:
            events.append("dispose")

    class Session:
        async def flush(self) -> None:
            events.append("flush")

        async def close(self) -> None:
            events.append("session_close")

    async def bind_decision(session, value) -> None:
        events.append("bind")

    def install(handler):
        events.append("install")
        handler()

        def restore() -> None:
            events.append("restore")

        return restore

    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.rollout._bound_session",
        lambda connection: Session(),
    )
    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.rollout._bind_decision",
        bind_decision,
    )
    engine = Engine()
    config = RolloutRuntimeConfig(
        database_url="postgresql+asyncpg://localhost/test",
        product_release_commit="a" * 40,
        rollout_generation=7,
        allowlist_inns=("7701234567",),
        percentage_basis_points=0,
    )

    with pytest.raises(RolloutSigterm):
        await run_rollout_mutation(
            parsed,
            config,
            mode="apply",
            confirm_digest=parsed.decision_digest,
            engine_factory=lambda url: engine,
            signal_handler_installer=install,
        )

    assert events.index("unlock") < events.index("close")
    assert events.index("close") < events.index("dispose")
    assert events.index("dispose") < events.index("restore")


def test_main_maps_controlled_sigterm_to_exit_143(monkeypatch, capsys) -> None:
    async def terminated(args):
        raise RolloutSigterm()

    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.rollout._async_main",
        terminated,
    )
    assert main(["validate", "--decision-file", "unused.json"]) == 143
    assert capsys.readouterr().err == '{"error":{"code":"rollout_sigterm"}}\n'


def test_main_redacts_unexpected_runtime_exception(monkeypatch, capsys) -> None:
    async def failed(args):
        raise RuntimeError(
            "postgresql://production-user:secret@example.com/7701234567"
        )

    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.rollout._async_main",
        failed,
    )
    assert main(["validate", "--decision-file", "unused.json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == '{"error":{"code":"rollout_failed"}}\n'
    assert "secret" not in captured.err
    assert "7701234567" not in captured.err


def test_main_redacts_invalid_operator_arguments(capsys) -> None:
    attacker_value = "postgresql://user:secret@example.test/7701234567"

    assert main(["validate", "--decision-file", "unused.json", attacker_value]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == '{"error":{"code":"rollout_arguments_invalid"}}\n'
    assert "secret" not in captured.err
    assert "7701234567" not in captured.err


@pytest.mark.asyncio
async def test_invalidated_backend_cleanup_preserves_primary_lock_loss() -> None:
    events: list[str] = []

    class Connection:
        invalidated = True
        closed = False

        async def close(self) -> None:
            self.closed = True
            events.append("close")

        def in_transaction(self) -> bool:
            raise AssertionError("invalidated connection must not be reused")

        async def scalar(self, *_args, **_kwargs):
            raise AssertionError("invalidated backend cannot be unlocked")

    class Engine:
        async def dispose(self) -> None:
            events.append("dispose")

    class Driver:
        def terminate(self) -> None:
            events.append("terminate")

    await _cleanup_rollout_connection(
        connection=Connection(),
        engine=Engine(),
        lock_key=1,
        lock_acquired=True,
        driver_connection=Driver(),
    )

    assert events == ["terminate", "close", "dispose"]


@pytest.mark.asyncio
async def test_missing_lock_cleanup_does_not_override_primary_lock_loss() -> None:
    events: list[str] = []

    class Connection:
        invalidated = False
        closed = False

        async def close(self) -> None:
            self.closed = True
            events.append("close")

        def in_transaction(self) -> bool:
            raise AssertionError("lost-lock connection must not be reused")

        async def scalar(self, *_args, **_kwargs):
            raise AssertionError("lost advisory lock must not be unlocked")

    class Engine:
        async def dispose(self) -> None:
            events.append("dispose")

    class Driver:
        def terminate(self) -> None:
            events.append("terminate")

        def is_closed(self) -> bool:
            return False

    await _cleanup_rollout_connection(
        connection=Connection(),
        engine=Engine(),
        lock_key=1,
        lock_acquired=True,
        driver_connection=Driver(),
        primary_lock_lost=True,
    )

    assert events == ["terminate", "close", "dispose"]
