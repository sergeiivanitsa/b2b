from __future__ import annotations

import base64
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
from uuid import UUID

from pydantic import SecretStr
import pytest

from product_api.company_reports.company_card_v2.canary import (
    CanaryExecutionError,
    CanaryRuntimeConfig,
    _active_h2_job,
    _load_private_plan,
    _local_schema_head,
    _read_target,
    _write_private_decisions,
    _write_private_file,
    build_canary_decisions,
    main,
    prepare_canary,
    validate_runtime_config,
)
from product_api.company_reports.company_card_v2.canary_models import (
    CanaryExpectedAssignmentV1,
    CanaryExpectedH2V1,
    CanaryH1RollbackV1,
    CanaryPlanError,
    CompanyCardV2CanaryPlanV1,
    canary_plan_bytes,
    canary_plan_digest,
    parse_canary_plan_bytes,
)


INN = "7707079463"
RELEASE = "a" * 40
REVISION = "0019_company_card_v2_rollout_control"


def _plan() -> CompanyCardV2CanaryPlanV1:
    return CompanyCardV2CanaryPlanV1(
        schema_version="company_card_v2_canary_plan_v1",
        release_commit=RELEASE,
        database_schema_revision=REVISION,
        rollout_generation=7,
        arbitration_mask_key_id="active_2026",
        target_subject_id="00000000-0000-0000-0000-000000000001",
        target_inn=INN,
        expected_assignment=CanaryExpectedAssignmentV1(
            generation=0,
            presentation_contract=None,
            pin_generation=None,
        ),
        h1_rollback=CanaryH1RollbackV1(
            source_kind="active_publication",
            report_id="00000000-0000-0000-0000-000000000002",
            snapshot_hash="b" * 64,
            pin_generation=1,
            pin_exists=False,
            publication_policy_version="publication_sufficiency_v1",
            canonical_path=f"/company/{INN}-company",
            published_lastmod="2026-08-29T00:00:00.000000Z",
        ),
        expected_h2=CanaryExpectedH2V1(
            head_generation=0,
            head_report_id=None,
            active_report_id=None,
            active_job_state=None,
        ),
    )


def _settings(*, gates_open: bool) -> SimpleNamespace:
    encoded = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode("ascii")
    return SimpleNamespace(
        database_url="postgresql+asyncpg://operator:secret@localhost/private",
        datanewton_enabled=gates_open,
        datanewton_api_key="provider-secret" if gates_open else "",
        company_card_v2_presentations_enabled=gates_open,
        company_card_v2_writer_enabled=gates_open,
        company_card_v2_rollout_generation=7,
        company_card_v2_allowlist_inns=[INN],
        company_card_v2_percentage_basis_points=0,
        company_card_v2_arbitration_collection_enabled=True,
        company_card_v2_arbitration_mask_active_key_id="active_2026",
        company_card_v2_arbitration_mask_keyring_json=SecretStr(
            f'{{"active_2026":"{encoded}"}}'
        ),
        company_card_v2_narrative_enabled=False,
        company_card_v2_narrative_kill_switch=True,
        company_card_v2_narrative_daily_limit=0,
        company_card_v2_narrative_monthly_limit=0,
        company_card_v2_narrative_concurrency=0,
    )


def _private(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    os.chmod(path, 0o600)
    return path


def test_plan_is_canonical_private_and_redacted() -> None:
    plan = _plan()
    raw = canary_plan_bytes(plan)

    assert parse_canary_plan_bytes(raw) == plan
    assert len(canary_plan_digest(plan)) == 64
    rendered = repr(plan) + repr(plan.h1_rollback)
    assert INN not in rendered
    assert plan.target_subject_id not in rendered

    with pytest.raises(CanaryPlanError):
        parse_canary_plan_bytes(raw + b"\n")


@pytest.mark.parametrize(
    ("contract", "pin_generation"),
    (
        ("company_public_h1_v1", None),
        (None, 1),
    ),
)
def test_plan_rejects_partial_assignment_identity(
    contract: str | None,
    pin_generation: int | None,
) -> None:
    with pytest.raises(ValueError, match="assignment shape is invalid"):
        CanaryExpectedAssignmentV1(
            generation=1,
            presentation_contract=contract,
            pin_generation=pin_generation,
        )


def test_runtime_requires_open_gates_only_for_inspect_and_prepare() -> None:
    closed = _settings(gates_open=False)
    with pytest.raises(CanaryExecutionError, match="canary_configuration_invalid"):
        validate_runtime_config(
            closed,
            target_inn=INN,
            release_commit=RELEASE,
            schema_revision=REVISION,
            require_open_gates=True,
        )

    runtime = validate_runtime_config(
        closed,
        target_inn=INN,
        release_commit=RELEASE,
        schema_revision=REVISION,
        require_open_gates=False,
    )
    assert runtime.arbitration_mask_key_id == "active_2026"
    assert "secret" not in repr(runtime)


def test_schema_head_supports_release_image_layout_outside_installed_wheel(
    tmp_path: Path,
) -> None:
    source_alembic = Path(__file__).resolve().parents[1] / "alembic"
    release_alembic = tmp_path / "app" / "alembic"
    shutil.copytree(source_alembic, release_alembic)
    installed_wheel_guess = (
        tmp_path
        / "usr"
        / "local"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "alembic"
    )

    assert _local_schema_head(
        script_locations=(release_alembic.resolve(), installed_wheel_guess.resolve())
    ) == REVISION

    with pytest.raises(CanaryExecutionError, match="canary_schema_invalid"):
        _local_schema_head(script_locations=(installed_wheel_guess.resolve(),))


@pytest.mark.parametrize(
    "change",
    (
        {"company_card_v2_allowlist_inns": [INN, "7701234568"]},
        {"company_card_v2_percentage_basis_points": 1},
        {"company_card_v2_arbitration_collection_enabled": False},
        {"company_card_v2_arbitration_mask_active_key_id": "missing"},
        {"company_card_v2_narrative_enabled": True},
        {"company_card_v2_narrative_kill_switch": False},
        {"company_card_v2_narrative_daily_limit": 1},
        {"company_card_v2_narrative_monthly_limit": 1},
        {"company_card_v2_narrative_concurrency": 1},
    ),
)
def test_runtime_rejects_nonexact_canary_binding(change) -> None:
    settings = _settings(gates_open=True)
    for key, value in change.items():
        setattr(settings, key, value)
    with pytest.raises(CanaryExecutionError, match="canary_configuration_invalid"):
        validate_runtime_config(
            settings,
            target_inn=INN,
            release_commit=RELEASE,
            schema_revision=REVISION,
        )


def test_private_target_and_plan_files_are_exact(tmp_path: Path) -> None:
    target = _private(tmp_path / "target", INN.encode("ascii"))
    plan_path = _private(tmp_path / "plan", canary_plan_bytes(_plan()))
    assert _read_target(target) == INN
    assert _load_private_plan(plan_path) == _plan()

    newline = _private(tmp_path / "newline", f"{INN}\n".encode("ascii"))
    with pytest.raises(CanaryExecutionError, match="canary_target_invalid"):
        _read_target(newline)

    other_inn = "7701234567"
    other = _private(tmp_path / "other", other_inn.encode("ascii"))
    with pytest.raises(CanaryExecutionError, match="canary_target_invalid"):
        _read_target(other)
    wrong_settings = _settings(gates_open=True)
    wrong_settings.company_card_v2_allowlist_inns = [other_inn]
    with pytest.raises(CanaryExecutionError, match="canary_configuration_invalid"):
        validate_runtime_config(
            wrong_settings,
            target_inn=other_inn,
            release_commit=RELEASE,
            schema_revision=REVISION,
        )


def test_private_output_is_no_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "decision.json"
    synced: list[Path] = []
    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.canary._fsync_parent_directory",
        lambda path: synced.append(path.parent),
    )
    _write_private_file(output.resolve(), b"{}")
    assert output.read_bytes() == b"{}"
    assert synced == [output.resolve().parent]
    if os.name != "nt":
        assert (output.stat().st_mode & 0o777) == 0o600
    with pytest.raises(CanaryExecutionError, match="canary_output_exists"):
        _write_private_file(output.resolve(), b"changed")
    assert output.read_bytes() == b"{}"


def test_decision_crash_boundary_never_leaves_activation_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SimulatedProcessCrash(BaseException):
        pass

    calls: list[str] = []

    def crash_before_activation(path: Path, payload: bytes) -> None:
        calls.append(path.name)
        if path.name == "company-card-v2-canary-activate.json":
            raise SimulatedProcessCrash
        _write_private_file(path, payload)

    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.canary._write_private_file",
        crash_before_activation,
    )
    with pytest.raises(SimulatedProcessCrash):
        _write_private_decisions(
            tmp_path.resolve(), b"activation", b"rollback"
        )
    assert calls == [
        "company-card-v2-canary-rollback.json",
        "company-card-v2-canary-activate.json",
    ]
    assert not (tmp_path / "company-card-v2-canary-activate.json").exists()
    assert (
        tmp_path / "company-card-v2-canary-rollback.json"
    ).read_bytes() == b"rollback"


def test_activation_parent_fsync_failure_durably_cleans_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def fail_second_parent_fsync(_path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise CanaryExecutionError("canary_output_write_failed")

    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.canary._fsync_parent_directory",
        fail_second_parent_fsync,
    )
    with pytest.raises(CanaryExecutionError, match="canary_output_write_failed"):
        _write_private_decisions(
            tmp_path.resolve(), b"activation", b"rollback"
        )
    assert calls == 4
    assert list(tmp_path.iterdir()) == []


def test_activation_cleanup_failure_retains_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    original_unlink = Path.unlink

    def fail_second_parent_fsync(_path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise CanaryExecutionError("canary_output_write_failed")

    def refuse_activation_unlink(path: Path, *args, **kwargs) -> None:
        if path.name == "company-card-v2-canary-activate.json":
            raise PermissionError("synthetic activation cleanup failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.canary._fsync_parent_directory",
        fail_second_parent_fsync,
    )
    monkeypatch.setattr(Path, "unlink", refuse_activation_unlink)
    with pytest.raises(CanaryExecutionError, match="canary_output_write_failed"):
        _write_private_decisions(
            tmp_path.resolve(), b"activation", b"rollback"
        )
    assert (tmp_path / "company-card-v2-canary-activate.json").exists()
    assert (
        tmp_path / "company-card-v2-canary-rollback.json"
    ).read_bytes() == b"rollback"


@pytest.mark.asyncio
async def test_prepare_digest_mismatch_has_zero_database_access() -> None:
    calls = 0

    def forbidden_engine(_url: str):
        nonlocal calls
        calls += 1
        raise AssertionError("database must not be opened")

    with pytest.raises(CanaryExecutionError, match="canary_plan_digest_mismatch"):
        await prepare_canary(
            plan=_plan(),
            confirm_digest="0" * 64,
            receipt_path=(Path.cwd() / "unused-receipt.json").resolve(),
            config=CanaryRuntimeConfig(
                database_url="postgresql+asyncpg://private",
                release_commit=RELEASE,
                schema_revision=REVISION,
                rollout_generation=7,
                arbitration_mask_key_id="active_2026",
            ),
            engine_factory=forbidden_engine,
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_build_decisions_rejects_equal_ids_before_database_access(
    tmp_path: Path,
) -> None:
    calls = 0

    def forbidden_engine(_url: str):
        nonlocal calls
        calls += 1
        raise AssertionError("database must not be opened")

    same_id = "00000000-0000-4000-8000-000000000901"
    with pytest.raises(CanaryExecutionError, match="canary_arguments_invalid"):
        await build_canary_decisions(
            plan=_plan(),
            receipt=None,  # type: ignore[arg-type]
            config=CanaryRuntimeConfig(
                database_url="postgresql+asyncpg://private",
                release_commit=RELEASE,
                schema_revision=REVISION,
                rollout_generation=7,
                arbitration_mask_key_id="active_2026",
            ),
            authorization_reference="P3-production-recovery",
            abort_policy_reference="P4-production-recovery",
            observation_window_seconds=60,
            h2_indexable=True,
            activate_decision_id=same_id,
            rollback_decision_id=same_id,
            output_dir=tmp_path.resolve(),
            engine_factory=forbidden_engine,
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_build_decisions_rejects_noindex_before_database_access(
    tmp_path: Path,
) -> None:
    calls = 0

    def forbidden_engine(_url: str):
        nonlocal calls
        calls += 1
        raise AssertionError("database must not be opened")

    with pytest.raises(
        CanaryExecutionError, match="canary_indexability_not_authorized"
    ):
        await build_canary_decisions(
            plan=_plan(),
            receipt=None,  # type: ignore[arg-type]
            config=CanaryRuntimeConfig(
                database_url="postgresql+asyncpg://private",
                release_commit=RELEASE,
                schema_revision=REVISION,
                rollout_generation=7,
                arbitration_mask_key_id="active_2026",
            ),
            authorization_reference="production-recovery",
            abort_policy_reference="production-recovery-abort",
            observation_window_seconds=60,
            h2_indexable=False,
            activate_decision_id="00000000-0000-4000-8000-000000000901",
            rollback_decision_id="00000000-0000-4000-8000-000000000902",
            output_dir=tmp_path.resolve(),
            engine_factory=forbidden_engine,
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_active_job_rejects_non_v3_report_identity() -> None:
    subject_id = UUID("00000000-0000-4000-8000-000000000001")
    report_id = UUID("00000000-0000-4000-8000-000000000002")
    job = SimpleNamespace(
        subject_id=subject_id,
        report_id=report_id,
        state="queued",
        writer_profile="company_card_v2_writer_v3",
        presentation_contract="company_public_h2_v1",
        rollout_generation=7,
        arbitration_collection_enabled=True,
        arbitration_mask_key_id="active_2026",
    )
    report = SimpleNamespace(
        id=report_id,
        subject_id=subject_id,
        lifecycle_status="pending",
        writer_profile="company_card_v2_writer_v3",
        presentation_contract="company_public_h2_v1",
        report_version="2",
        rollout_generation=7,
        arbitration_collection_enabled=True,
        arbitration_mask_key_id="active_2026",
    )

    class _Rows:
        def all(self):
            return [(job, report)]

    class _Session:
        async def execute(self, _statement):
            return _Rows()

    with pytest.raises(CanaryExecutionError, match="canary_active_job_conflict"):
        await _active_h2_job(
            _Session(),
            subject=SimpleNamespace(id=subject_id),
            config=CanaryRuntimeConfig(
                database_url="postgresql+asyncpg://private",
                release_commit=RELEASE,
                schema_revision=REVISION,
                rollout_generation=7,
                arbitration_mask_key_id="active_2026",
            ),
        )


def test_main_redacts_unexpected_exception(monkeypatch, capsys) -> None:
    async def failed(_args):
        raise RuntimeError(
            f"postgresql://operator:secret@example/{INN}/"
            "00000000-0000-0000-0000-000000000001"
        )

    monkeypatch.setattr(
        "product_api.company_reports.company_card_v2.canary._async_main",
        failed,
    )
    assert main(
        [
            "status",
            "--plan-file",
            "unused.json",
            "--receipt-file",
            "unused-receipt.json",
        ]
    ) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == '{"error":{"code":"canary_failed"}}\n'
    assert "secret" not in captured.err
    assert INN not in captured.err


def test_main_redacts_invalid_arguments(capsys) -> None:
    attacker = f"postgresql://operator:secret@example/{INN}"
    assert main(["status", "--plan-file", "unused.json", attacker]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == '{"error":{"code":"canary_arguments_invalid"}}\n'
    assert "secret" not in captured.err
    assert INN not in captured.err
