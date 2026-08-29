"""Fail-closed contracts for the one-time destructive production fresh install."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/deploy_prod_fresh_install.yml"
RUNNER = ROOT / "deploy/product_api/fresh_install_runner.sh"
BOOT_GUARD = ROOT / "deploy/product_api/fresh_install_boot_guard.sh"
DATABASE = ROOT / "deploy/product_api/fresh_install_database.py"
CANDIDATE = ROOT / "deploy/product_api/fresh_install_candidate.py"
GATEWAY_RECEIPT = ROOT / "deploy/product_api/fresh_install_gateway_receipt.py"
COMPOSE = ROOT / "docker-compose.product.yml"


def _database_module():
    spec = importlib.util.spec_from_file_location("fresh_install_database", DATABASE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate_module():
    spec = importlib.util.spec_from_file_location("fresh_install_candidate", CANDIDATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _gateway_receipt_module():
    spec = importlib.util.spec_from_file_location(
        "fresh_install_gateway_receipt", GATEWAY_RECEIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_fresh_install_is_manual_exact_main_qa_and_environment_protected() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "schedule:" not in text
    assert "environment: production" in text
    assert "refs/heads/main" in text
    assert "git merge-base --is-ancestor" in text
    assert "github.workflow_sha" in text
    assert "github.workflow_ref" in text
    assert "uses: ./.github/workflows/qa.yml" in text
    assert "needs: [trusted-main, qa]" in text
    assert "verified_release_sha == needs.trusted-main.outputs.release_sha" in text
    assert "release-manifest-$RELEASE_SHA.json" in text
    assert "qa-attestation-{release_sha}.json" in text
    assert "set(jobs.values()) != {\"success\"}" in text
    assert "33253311395" in text
    assert "708fb8d9a665e31854a15183328234b728cd996e276b6db1d74c887dedd28937" in text
    assert "seed_bundle_run_id:" not in text
    assert "seed_bundle_sha256:" not in text


def test_confirmation_is_exact_and_scope_is_only_public_schema() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    database = DATABASE.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    assert "confirm_database_schema_reset:" in workflow
    assert workflow.count("DROP-AND-RECREATE-PRODUCTION-PUBLIC-SCHEMA") == 2
    assert "destructive_confirmation" not in workflow
    assert "DROP SCHEMA public CASCADE" in database
    assert "CREATE SCHEMA public AUTHORIZATION" in database
    assert "DROP DATABASE" not in database.upper()
    assert "dropdb" not in workflow.lower() + runner.lower()
    assert "docker compose down -v" not in workflow + runner
    for legacy_input in (
        "p1_protection_evidence",
        "p2_evidence",
        "database_backup_artifact",
        "database_recovery_hook",
        "prior_release_sha",
    ):
        assert legacy_input not in workflow


def test_preflight_is_read_only_and_binds_legacy_topology_database_and_uploads() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    preflight = text.split(
        "- name: Exact read-only live RU legacy topology and database preflight", 1
    )[1].split("- name: Stage exact release", 1)[0]
    assert "0015_claims_company_report_handoff" in preflight
    assert "6bee95e881a3e9ea1fe324ca13c11ae239f896f4" in preflight
    assert "company_card_narrative_worker | wc -l)\" -eq 0" in preflight
    assert "EXPECTED_DATABASE_IDENTITY_SHA256" in preflight
    assert "RU_DATABASE_IDENTITY_SHA256" in text
    assert "RU_DATABASE_URL" not in text
    assert "legacy-claims --release-sha" in preflight
    assert "claims_upload_dir" in CANDIDATE.read_text(encoding="utf-8")
    assert "/data/claims_uploads" in preflight
    assert "CLAIMS_UPLOAD_ROOT" in preflight
    assert "/var/lib/pork/claims-uploads/v1" in preflight
    assert 'rows.get("SUPERADMIN_EMAIL", "")' in preflight
    assert "initial superadmin setting is invalid; STOP" in preflight
    assert "legacy-claims --release-sha" in preflight
    candidate = CANDIDATE.read_text(encoding="utf-8")
    assert "next(path.iterdir(), None)" in candidate
    assert "not path.is_symlink()" in candidate
    assert 'realpath -e -- "$claims_root"' in preflight
    assert 'stat -c "%u:%g:%a" -- "$claims_root"' in preflight
    assert 'realpath -e -- "$claims_parent"' in preflight
    assert "test -d /var/lib/pork && test ! -L /var/lib/pork" in preflight
    assert "fresh-install-active.json" in preflight
    assert "incompatible production fresh-install recovery unit is installed; STOP" in preflight
    assert "an incompatible legacy bootstrap recovery unit is installed; STOP" in preflight
    assert 'grep -Fqx "ExecStart=/bin/bash $stage/fresh_install_runner.sh' in preflight
    assert "active|activating|reloading|deactivating" in preflight
    assert "fresh_install_boot_guard.sh" in preflight
    for mutation in ("DROP SCHEMA", "alembic upgrade", "docker kill", "systemctl reload nginx"):
        assert mutation not in preflight


def test_claims_uploads_gain_one_exact_persistent_product_mount() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    product = compose.split("  product_api:", 1)[1].split("  company_report_worker:", 1)[0]
    workers = compose.split("  company_report_worker:", 1)[1]
    assert "source: ${CLAIMS_UPLOAD_ROOT:" in product
    assert "target: ${CLAIMS_UPLOAD_DIR:" in product
    assert "volumes:" in product
    assert "CLAIMS_UPLOAD_ROOT" not in workers
    runner = RUNNER.read_text(encoding="utf-8")
    assert "claims_root=/var/lib/pork/claims-uploads/v1" in runner
    assert "claims_target=/data/claims_uploads" in runner
    assert "candidate Claims upload persistence mapping invalid; STOP" in runner
    assert "/var/lib/pork/claims-uploads/v1|/data/claims_uploads|true" in runner
    assert runner.count("/var/lib/pork/claims-uploads/v1|/data/claims_uploads|true") == 2
    assert 'if ! path_present "$claims_root"' in runner
    assert "rm " + '"$claims_root"' not in runner
    base_guard = runner.index('test -d "$claims_base" && test ! -L "$claims_base"')
    parent_guard = runner.index('if path_present "$claims_parent"')
    parent_create = runner.index(
        'bounded install -d -m 750 -o root -g root "$claims_parent"'
    )
    assert base_guard < parent_guard < parent_create


def test_database_guard_uses_one_protected_digest_and_sanitized_receipts() -> None:
    text = DATABASE.read_text(encoding="utf-8")
    assert "EXPECTED_DATABASE_IDENTITY_SHA256" in text
    assert "EXPECTED_SCHEMA_INVENTORY_SHA256" in text
    assert "database_url_sha256" in text
    assert '"database_oid": observed.database_oid' in text
    assert '"session_role": observed.session_role' in text
    assert '"database_acl": observed.database_acl' in text
    assert '"server_version_num": observed.server_version_num' in text
    assert '"database_name": observed.database_name' in text
    receipt = text.split("def _receipt(", 1)[1].split("async def _run", 1)[0]
    assert '"database_identity_sha256"' not in receipt
    assert '"schema_inventory_sha256"' in receipt
    assert '"schema_grants_sha256"' in receipt
    assert '"database_name"' not in receipt
    assert '"server_identity"' not in receipt
    assert "database operation failed without a verified receipt; STOP" in text


def test_database_guard_sets_strict_acl_and_has_atomic_reset_reconciliation_marker() -> None:
    text = DATABASE.read_text(encoding="utf-8")
    assert "aclexplode" in text
    assert "REVOKE ALL ON SCHEMA public FROM PUBLIC" in text
    assert "WITH GRANT OPTION" in text
    assert "public schema ACL is not the approved strict contract; STOP" in text
    assert "COMMENT ON SCHEMA public" in text
    assert "production_fresh_install_schema_marker_v1" in text
    assert "database changed outside the exact reset reconciliation states; STOP" in text
    assert "0015_claims_company_report_handoff" in text
    assert "0019_company_card_v2_rollout_control" in text
    assert text.index("DROP SCHEMA public CASCADE") < text.index(
        "COMMENT ON SCHEMA public"
    )


def test_post_reset_acl_is_exact_runtime_only_and_not_legacy_acl_replay() -> None:
    module = _database_module()
    observed = module.ObservedIdentity(
        schema_version="production_fresh_install_db_identity_v1",
        database_url_sha256="a" * 64,
        database_name="app",
        database_oid=16384,
        server_identity="127.0.0.1:5432",
        database_role="app",
        session_role="app",
        schema_owner="app",
        database_owner="app",
        database_acl=None,
        server_version_num=160011,
        database_owner_member=True,
        schema_owner_member=True,
        schema_usage=True,
        schema_create=True,
        non_system_schemas=("public",),
        schema_grants=module._strict_grants("app"),
        other_sessions=0,
    )
    module._assert_strict_schema_contract(observed)
    with pytest.raises(module.FreshInstallDatabaseError):
        module._assert_strict_schema_contract(
            replace(
                observed,
                schema_grants=observed.schema_grants
                + (module.SchemaGrant("PUBLIC", "USAGE", False),),
            )
        )


def test_database_guard_validates_exact_default_off_head_and_empty_application_data() -> None:
    text = DATABASE.read_text(encoding="utf-8")
    assert "publication_sufficiency_v1" in text
    assert '(1, "paused", "publication_sufficiency_v1")' in text
    assert "(1, False, True, 0, 0, 0, 0)" in text
    assert "fresh schema contains application data; STOP" in text
    assert '"alembic_version"' in text
    assert '"company_card_narrative_runtime_control"' in text
    assert '"company_report_publication_control"' in text
    assert 'command in {"verify-head", "verify-runtime", "verify-live-runtime"}' in text
    assert "allow_application_data=command == \"verify-live-runtime\"" in text
    assert '"SELECT email, is_active FROM users "' in text
    assert '"WHERE is_superadmin ORDER BY id"' in text
    assert "live runtime superadmin identity is not exact; STOP" in text


def test_database_identifier_and_acl_sql_are_closed() -> None:
    module = _database_module()
    assert module._identifier("app-role") == '"app-role"'
    assert module._identifier('a"b') == '"a""b"'
    with pytest.raises(module.FreshInstallDatabaseError):
        module._identifier("bad\x00role")
    statements = module._grant_sql(
        (
            module.SchemaGrant("PUBLIC", "USAGE", False),
            module.SchemaGrant("app-role", "CREATE", True),
        )
    )
    assert statements == (
        "REVOKE ALL ON SCHEMA public FROM PUBLIC",
        'GRANT USAGE ON SCHEMA public TO PUBLIC',
        'GRANT CREATE ON SCHEMA public TO "app-role" WITH GRANT OPTION',
    )
    with pytest.raises(module.FreshInstallDatabaseError):
        module._grant_sql((module.SchemaGrant("PUBLIC", "DROP", False),))


def test_runner_is_durable_resumable_and_never_restarts_legacy_after_drop() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    assert "Description=One-time destructive exact-SHA production fresh install" in workflow
    assert "Restart=on-failure" in workflow
    assert "WantedBy=multi-user.target" in workflow
    assert "systemctl enable --now" in workflow
    assert "fresh-install-tools-$release_sha.sha256" in workflow
    assert "production_fresh_install_marker_v1" in runner
    assert "production_fresh_install_global_v1" in runner
    assert "fresh-install-active.json" in runner
    assert "fresh-install-success.json" in runner
    assert "roll-forward-required" in runner
    assert "schema-reset-armed" in runner
    assert "schema-reset-complete" in runner
    assert "legacy-0015-rollback" not in runner
    assert "prior-product-image" not in runner


def test_systemd_boot_guard_keeps_incomplete_release_fail_closed() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    guard = BOOT_GUARD.read_text(encoding="utf-8")
    recovery_unit = workflow.split(
        "Description=One-time destructive exact-SHA production fresh install", 1
    )[1].split("guard=pork-production-fresh-install-ingress-guard.service", 1)[0]
    assert "nginx.service" not in recovery_unit
    assert "Requires=docker.service" not in recovery_unit
    assert "Wants=docker.service network-online.target" in recovery_unit
    assert "Before=nginx.service" in workflow
    assert "RequiredBy=nginx.service" in workflow
    assert '"Requires=$guard"' in workflow
    assert '"After=$guard"' in workflow
    assert "fresh_install_boot_guard.sh" in workflow
    assert "fresh_install_boot_guard.sh" in workflow.split("sha256sum", 1)[1]
    assert "verify_receipt \"$active_receipt\" active" in guard
    assert guard.index('verify_receipt "$active_receipt" active') < guard.rindex(
        "product_api_legacy_0015_h2_bootstrap.conf"
    )
    assert "nginx -t" in guard
    assert "systemctl" not in guard
    assert "reload-or-restart nginx" in runner
    assert "systemctl reload nginx" not in runner
    retry = runner.split("global_receipt active", 1)[1].split(
        'cd "$stage"', 1
    )[0]
    assert 'path_present "$stage/ingress-armed"' in retry
    assert "force_maintenance_ingress" in retry
    finish = runner.split("finish() {", 1)[1].split("trap finish EXIT", 1)[0]
    assert 'path_present "$stage/ingress-armed"' in finish
    assert "systemctl stop nginx" in finish


def test_runner_phase_order_is_fail_closed_and_regular_ingress_is_last() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    storage = text.index("marker_once storage-complete")
    maintenance = text.rindex("marker_once maintenance-ingress")
    writers = text.index("marker_once writers-stopped")
    armed = text.rindex("marker_once schema-reset-armed")
    reset = text.index("marker_once schema-reset-complete")
    migration = text.index("marker_once migration-complete")
    product = text.index("marker_once product-complete")
    web = text.index("marker_once web-complete")
    signed_gateway = text.rindex('signed_gateway_smoke_container "$product_id"')
    regular_nginx = text.rindex('install -m 640 "$stage/product_api.conf"')
    ingress_armed = text.rindex("marker_once ingress-armed")
    ingress_complete = text.rindex("marker_once ingress-complete")
    success = text.index("marker_once fresh-install-success", regular_nginx)
    assert maintenance < storage < writers < armed < reset < migration < product < web
    assert web < signed_gateway < ingress_armed < regular_nginx < ingress_complete < success
    assert text.index("candidate_image_check none settings") < maintenance
    after_drop = text[text.index("marker_once schema-reset-armed") :]
    assert "b2b-product-api:6bee95" not in after_drop


def test_runner_reconciles_seed_candidate_reset_and_migration_crash_windows() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert 'print("empty")' in text
    assert 'print("seeded")' in text
    assert 'print("candidate")' in text
    assert "H2 root is outside the exact resumable graph; STOP" in text
    assert "db_guard reset" in text
    assert "db_guard verify-head" in text
    assert "db_guard prepare-upgrade" in text
    assert "db_guard verify-runtime" in text
    database = DATABASE.read_text(encoding="utf-8")
    assert "elif not revisions and inventory == empty_inventory" in database
    assert "reconciled schema marker mismatch; STOP" in database
    assert "_schema_dependency_addresses" in database
    assert "_assert_dependency_closure" in database
    assert "_ALEMBIC_STUB_OBJECTS" not in database
    assert "migration source object graph is invalid; STOP" in database
    assert text.index("db_guard prepare-upgrade") < text.index(
        "python -m alembic"
    )


def test_runner_reconciles_product_startup_superadmin_crash_window() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    migration = text.index("marker_once migration-complete")
    product = text.index("marker_once product-complete")
    window = text[migration:product]
    assert 'path_present "$stage/product-complete"' in window
    assert "db_guard verify-head" in window
    assert "db_guard verify-runtime" in window
    product_block = text[
        text.index('if ! path_present "$stage/product-complete"') : text.index(
            'if ! path_present "$stage/web-complete"'
        )
    ]
    assert product_block.index("db_guard verify-runtime") < product_block.index(
        "marker_once product-complete"
    )
    assert "db_guard verify-live-runtime" in text
    assert text.rindex("db_guard verify-live-runtime") < text.rindex(
        "marker_once ingress-complete"
    )


def test_release_sha_is_validated_before_database_engine_or_reset() -> None:
    text = DATABASE.read_text(encoding="utf-8")
    run = text.split("async def _run", 1)[1]
    validation = run.index('re.fullmatch(r"[0-9a-f]{40}", release_sha)')
    assert validation < run.index("create_async_engine")
    module = _database_module()
    with pytest.raises(module.FreshInstallDatabaseError):
        module._schema_marker("NOT-A-SHA", "a" * 64)


def test_exact_gateway_sha_precedes_drop_and_signed_ping_precedes_ingress() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    gateway = workflow.index("Deploy and verify same exact Gateway SHA")
    bind = workflow.index("Bind exact Gateway success to RU durable stage")
    launch = workflow.index("Launch durable fail-closed fresh-install transaction")
    assert gateway < bind < launch
    assert "b2b-gateway-api:$release_sha" in workflow
    assert "gateway-complete" in workflow and "gateway-complete" in runner
    candidate = CANDIDATE.read_text(encoding="utf-8")
    assert "/internal/ping" in candidate
    assert "_sign_headers" in candidate
    assert '"release_commit": release_sha' in candidate
    assert "fresh_install_candidate.py" in workflow
    gateway_step = workflow.split(
        "Deploy and verify same exact Gateway SHA before destructive boundary", 1
    )[1].split("Bind exact Gateway success to RU durable stage", 1)[0]
    signed_legacy = gateway_step.index(
        "docker exec -i '$legacy_product_id' python - gateway"
    )
    assert signed_legacy < gateway_step.index('echo "complete=true"')
    prearm = runner.split('marker_once gateway-signed-prearm', 1)[0]
    assert "candidate_image_check host gateway" in prearm
    assert "candidate_image_check none alembic" in prearm
    assert prearm.index("candidate_image_check none alembic") < prearm.index(
        "candidate_image_check host gateway"
    )
    boundary = runner.split("marker_once writers-stopped", 1)[1].split(
        "marker_once schema-reset-armed", 1
    )[0]
    assert "candidate_image_check host gateway" in boundary
    assert "production_fresh_install_gateway_v1" in runner


def test_failure_after_drop_forces_maintenance_or_stops_nginx() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    finish = runner.split("finish() {", 1)[1].split("trap finish EXIT", 1)[0]
    assert finish.index('path_present "$stage/schema-reset-armed"') < finish.index(
        "force_maintenance_ingress"
    )
    assert finish.index("force_maintenance_ingress") < finish.index(
        "terminal_bounded systemctl stop nginx"
    )
    assert finish.index("terminal_bounded systemctl stop nginx") < finish.index(
        "marker_once roll-forward-required"
    )


def test_claims_legacy_proof_is_frozen_immediately_before_product_stop() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    maintenance = runner.index("marker_once maintenance-ingress")
    checked = runner.index("marker_once claims-legacy-checked")
    frozen = runner.index("marker_once claims-legacy-frozen")
    product_stop = runner.index('stop_container "$legacy_product"')
    assert maintenance < checked < frozen < product_stop
    proof = runner[maintenance:product_stop]
    assert "docker ps -aq" in proof
    assert 'eq .Destination "/data/claims_uploads"' in proof
    assert "legacy-claims" in proof
    assert 'path_present "$stage/claims-legacy-checked"' in proof
    assert 'path_present "$stage/claims-legacy-frozen"' in proof
    assert "legacy Product topology is not singular; STOP" in proof


def test_success_marker_is_terminal_and_signal_after_commit_cannot_restore_maintenance() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    finish = runner.split("finish() {", 1)[1].split("trap finish EXIT", 1)[0]
    success = finish.index('path_present "$stage/fresh-install-success"')
    armed_failure = finish.index('path_present "$stage/schema-reset-armed"')
    assert success < armed_failure
    success_branch = finish[success:armed_failure]
    assert "marker_once fresh-install-success" in success_branch
    assert "exit 0" in success_branch
    tail = runner[runner.rindex("global_receipt success") :]
    assert tail.index("fresh-install-active.json") < tail.index(
        "marker_once fresh-install-success"
    )
    assert tail.index("marker_once fresh-install-success") < tail.index(
        "cleanup_boot_guard"
    )


def test_database_and_candidate_helpers_fail_without_secret_echo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database = _database_module()

    def fail_run(awaitable):
        awaitable.close()
        raise OSError("SECRET_CANARY")

    monkeypatch.setattr(database.asyncio, "run", fail_run)
    assert database.main(["guard", "inspect", "--release-sha", "a" * 40]) == 2
    output = capsys.readouterr()
    assert "SECRET_CANARY" not in output.out + output.err
    assert output.err == "database operation failed without a verified receipt; STOP\n"
    assert "--receipt" not in DATABASE.read_text(encoding="utf-8")

    candidate = _candidate_module()

    def fail_settings(*_args):
        raise RuntimeError("SECRET_CANARY")

    monkeypatch.setattr(candidate, "_validate_settings", fail_settings)
    assert (
        candidate.main(
            [
                "candidate",
                "settings",
                "--release-sha",
                "a" * 40,
                "--provider-state",
                "disabled",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert "SECRET_CANARY" not in output.out + output.err
    assert output.err == "candidate verification failed without details; STOP\n"


def test_candidate_provider_command_outputs_only_bounded_state(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    candidate = _candidate_module()
    monkeypatch.setattr(candidate, "_provider_state", lambda: "enabled")
    assert (
        candidate.main(
            ["candidate", "provider", "--release-sha", "a" * 40]
        )
        == 0
    )
    output = capsys.readouterr()
    assert output.out == "enabled\n"
    assert output.err == ""


def test_candidate_superadmin_length_is_bounded_before_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate_module()
    release_sha = "a" * 40
    monkeypatch.setenv("PRODUCT_RELEASE_COMMIT", release_sha)
    settings = SimpleNamespace(
        superadmin_email="x" * 320,
        datanewton_enabled=False,
        datanewton_api_key=None,
        claims_upload_dir="/data/claims_uploads",
        company_card_v2_presentations_enabled=False,
        company_card_v2_writer_enabled=False,
        company_card_v2_rollout_generation=0,
        company_card_v2_allowlist_inns=[],
        company_card_v2_percentage_basis_points=0,
        company_card_v2_arbitration_collection_enabled=False,
        company_card_v2_arbitration_mask_active_key_id=None,
        company_card_v2_arbitration_mask_keyring_json=None,
        company_card_v2_narrative_enabled=False,
        company_card_v2_narrative_kill_switch=True,
        company_card_v2_narrative_daily_limit=0,
        company_card_v2_narrative_monthly_limit=0,
        company_card_v2_narrative_concurrency=0,
    )
    candidate._settings_contract(settings, release_sha, "disabled")
    with pytest.raises(candidate.CandidateCheckError) as error:
        candidate._settings_contract(
            SimpleNamespace(**{**vars(settings), "superadmin_email": "x" * 321}),
            release_sha,
            "disabled",
        )
    assert "x" * 321 not in str(error.value)


def test_reset_empty_state_inventory_uses_postgres_dependency_closure() -> None:
    database = DATABASE.read_text(encoding="utf-8")
    dependency_objects = database.split(
        "async def _schema_dependency_objects", 1
    )[1].split(
        "async def _schema_state", 1
    )[0]
    for token in (
        "WITH RECURSIVE object_graph",
        "pg_depend",
        "pg_identify_object",
        "d.refclassid = parent.classid",
        "d.refobjid = parent.objid",
    ):
        assert token in dependency_objects
    schema_state = database.split("async def _schema_state", 1)[1].split(
        "async def _verify_upgrade_source", 1
    )[0]
    assert "_schema_dependency_objects(connection)" in schema_state
    reset = database.split('if command == "reset":', 1)[1].split(
        'if command == "verify-reset":', 1
    )[0]
    assert "reset_inventory != empty_inventory" in reset


def test_alembic_stub_uses_dynamic_raw_dependency_closure_and_rejects_extras() -> None:
    module = _database_module()
    exact = frozenset({(1259, 10, 0), (1247, 20, 0), (2606, 30, 0)})
    module._assert_dependency_closure(exact, exact)
    for unexpected in ((2620, 40, 0), (3256, 41, 0), (3456, 42, 0)):
        with pytest.raises(module.FreshInstallDatabaseError):
            module._assert_dependency_closure(exact | {unexpected}, exact)
    database = DATABASE.read_text(encoding="utf-8")
    source = database.split("async def _verify_upgrade_source", 1)[1].split(
        "def _receipt", 1
    )[0]
    assert source.index("_schema_dependency_addresses(connection)") < source.index(
        "if not objects and not addresses"
    )
    for catalog in (
        "pg_trigger",
        "pg_policy",
        "pg_collation",
        "pg_rewrite",
        "pg_attrdef",
        "pg_statistic_ext",
        "pg_inherits",
        "pg_publication_rel",
    ):
        assert catalog in source
    assert "pg_identify_object(" not in source
    assert "_assert_dependency_closure(addresses, allowed)" in source


def test_gateway_prior_identity_is_immutable_and_terminal_cleanup_covers_partial_mutation() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    arm = workflow.index("Arm reversible prior Gateway identity")
    candidate = workflow.index("Deploy and verify same exact Gateway SHA")
    durable = workflow.index("Launch durable fail-closed fresh-install transaction")
    cleanup = workflow.index("Restore prior Gateway when RU durable handoff is absent")
    assert arm < candidate < durable < cleanup
    assert "Restore prior Gateway if exact candidate did not become healthy" not in workflow
    assert workflow.count("prior-gateway.json") >= 5
    assert "production_fresh_install_prior_gateway_v1" in GATEWAY_RECEIPT.read_text(
        encoding="utf-8"
    )
    stage = workflow.split("Stage exact release, seed and fresh-install tools", 1)[1].split(
        "Arm reversible prior Gateway identity", 1
    )[0]
    assert "fresh_install_gateway_receipt.py" in stage
    assert ".release/preflight/us-topology.txt \"$US_TARGET:$US_STAGE/\"" not in stage
    arm_step = workflow[arm:candidate]
    assert "fresh_install_gateway_receipt.py write" in arm_step
    assert 'test "$current_image" != "$expected"' in arm_step
    assert "docker image inspect \"$tag\"" in arm_step


def test_healthy_gateway_is_restored_only_when_terminal_ru_handoff_probe_is_pre_boundary() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    wait = workflow.index("Wait for durable exact-SHA fresh-install success")
    cleanup = workflow.index("Restore prior Gateway when RU durable handoff is absent")
    stop_agent = workflow.index("Stop local deployment credential agent")
    assert wait < cleanup < stop_agent
    terminal = workflow[cleanup:stop_agent]
    assert "if: always()" in terminal
    assert "steps.gateway_arm.outputs.armed == 'true'" in terminal
    assert "steps.gateway.outputs.complete" not in terminal.split("shell: bash", 1)[0]
    assert "steps.success.outputs.complete != 'true'" in terminal
    assert 'receipt="$state_root/fresh-install-$phase.json"' in terminal
    assert "for phase in success active" in terminal
    assert "production_fresh_install_global_v1" in terminal
    assert "production_fresh_install_marker_v1" in terminal
    assert "systemctl is-enabled" in terminal
    assert "active|activating|deactivating|reloading" in terminal
    assert "enabled|enabled-runtime|linked|linked-runtime|alias" in terminal
    assert "RU durable handoff exists; exact Gateway rollback is forbidden" in terminal
    assert "fresh_install_gateway_receipt.py read" in terminal
    assert 'GATEWAY_IMAGE_TAG="fresh-install-prior-$release_sha"' in terminal
    decision = terminal.split('case "$handoff" in', 1)[1]
    assert decision.index('durable)') < decision.index('pre-boundary)')
    assert decision.index('pre-boundary)') < decision.index("restore_prior_gateway")
    assert "unknown fresh-install recovery state" in terminal
    assert "unknown fresh-install recovery enablement" in terminal


def test_prior_gateway_receipt_is_canonical_and_write_once() -> None:
    module = _gateway_receipt_module()
    release_sha = "a" * 40
    image_id = "sha256:" + "b" * 64
    payload = module._payload(release_sha, "b2b", image_id, "-")
    assert payload == {
        "gateway_image_id": image_id,
        "gateway_release_commit": None,
        "project": "b2b",
        "release_sha": release_sha,
        "schema_version": "production_fresh_install_prior_gateway_v1",
    }
    assert json.loads(module._canonical(payload)) == payload
    with pytest.raises(module.PriorGatewayReceiptError, match="release identity"):
        module._payload(release_sha, "b2b", image_id, "candidate")
    source = GATEWAY_RECEIPT.read_text(encoding="utf-8")
    for token in ("os.O_EXCL", "os.replace", "os.fsync", "receipt is immutable"):
        assert token in source


def test_fresh_install_receipt_examples_are_canonical() -> None:
    module = _database_module()
    payload = {
        "phase": "gateway-complete",
        "release_sha": "a" * 40,
        "schema_version": "production_fresh_install_marker_v1",
    }
    assert json.loads(module._canonical(payload)) == payload
    assert module._canonical(payload).endswith(b"\n")


def test_fingerprint_exposes_only_the_operator_binding_digest() -> None:
    module = _database_module()
    observed = module.ObservedIdentity(
        schema_version="production_fresh_install_db_identity_v1",
        database_url_sha256="a" * 64,
        database_name="app",
        database_oid=16384,
        server_identity="127.0.0.1:5432",
        database_role="app",
        session_role="app",
        schema_owner="pg_database_owner",
        database_owner="app",
        database_acl=None,
        server_version_num=160011,
        database_owner_member=True,
        schema_owner_member=True,
        schema_usage=True,
        schema_create=True,
        non_system_schemas=("public",),
        schema_grants=(module.SchemaGrant("app", "CREATE", False),),
        other_sessions=0,
    )
    digest = module._identity_digest(observed)
    assert len(digest) == 64
    assert digest != observed.database_url_sha256
    assert module._identity_digest(replace(observed, schema_owner="app")) == digest
    assert 'payload["database_identity_sha256"] = _identity_digest(observed)' in (
        DATABASE.read_text(encoding="utf-8")
    )


def test_seed_archive_is_bounded_and_traversal_checked_before_extract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    check = text.index("PurePosixPath")
    extract = text.index('tar -xzf "$seed"')
    assert check < extract
    assert 'parts[0] != "seed-bundle"' in text
    assert 'part in {"", ".", ".."}' in text
    assert "item.isfile() or item.isdir()" in text
    assert "256 * 1024 * 1024" in text
