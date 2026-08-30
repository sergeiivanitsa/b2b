"""Static fail-closed contracts for iteration-25 CI and release surfaces."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / ".github/workflows/qa.yml"
DEPLOY = ROOT / ".github/workflows/deploy_prod.yml"
LEGACY_BOOTSTRAP = ROOT / ".github/workflows/deploy_prod_legacy_0015_bootstrap.yml"
LEGACY_BOOTSTRAP_RUNNER = ROOT / "deploy/product_api/legacy_0015_bootstrap_runner.sh"
SEED = ROOT / ".github/workflows/company_public_h2_seed_bundle.yml"
RECOVERY_SPEC = ROOT / "docs/development/iterations/iteration-25-production-recovery.md"
RECOVERY_PLAN = ROOT / "docs/development/plans/iteration-25-production-recovery.md"
FRESH_INSTALL_SPEC = ROOT / "docs/development/iterations/iteration-25-production-fresh-install.md"
FRESH_INSTALL_PLAN = ROOT / "docs/development/plans/iteration-25-production-fresh-install.md"
RECOVERY_RUNBOOK = ROOT / "docs/development/runbooks/company-card-v2-rollout.md"

POSTGRES_IMAGE = "postgres:16.9-alpine@sha256:b441677c946de564fe88ae4245ba80fe84a69485b22bf560e9c7c3710cd5e21d"
PLAYWRIGHT_IMAGE = "mcr.microsoft.com/playwright:v1.62.1-noble@sha256:c091b21d9fae78c76e85cd4356431e9b018402f172a214fc7d7a5e9a7e29d8ac"
PYTHON_BASE = "python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49"
BUILDX_VERSION = "v0.25.0"
RELEASE_IMPORT_SMOKE_VARS = ROOT / ".github/ci/release-import-smoke.vars"
RELEASE_IMPORT_SMOKE_KEYS = frozenset(
    {
        "APP_ENV",
        "DATABASE_URL",
        "GATEWAY_URL",
        "GATEWAY_SHARED_SECRET",
        "AUTH_TOKEN_SECRET",
        "CLAIM_EDIT_TOKEN_SECRET",
        "CLAIMS_UPLOAD_DIR",
        "INVITE_TOKEN_SECRET",
        "SESSION_SECRET",
        "EMAIL_FROM",
    }
)
PRODUCT_IMPORTS = (
    "import product_api.main; "
    "import product_api.company_reports.worker; "
    "import product_api.company_reports.company_card_v2.narrative.worker"
)
GATEWAY_IMPORTS = "import gateway_api.main"


def _release_import_smoke_values() -> dict[str, str]:
    raw = RELEASE_IMPORT_SMOKE_VARS.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    values: dict[str, str] = {}
    for line_number, row in enumerate(raw.splitlines(), start=1):
        if not row or row.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(\S+)", row)
        assert match is not None, f"invalid smoke env row {line_number}: {row!r}"
        key, value = match.groups()
        assert key not in values, f"duplicate smoke env key: {key}"
        values[key] = value
    return values


def _dockerfile_instructions(text: str) -> list[str]:
    instructions: list[str] = []
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or (not current and line.startswith("#")):
            continue
        current = f"{current} {line}".strip()
        if current.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        instructions.append(current)
        current = ""
    assert not current
    return instructions


def _release_import_subprocess_env(*, include_smoke_values: bool) -> dict[str, str]:
    relevant = RELEASE_IMPORT_SMOKE_KEYS | {"OPENAI_API_KEY"}
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in relevant
    }
    if include_smoke_values:
        environment.update(_release_import_smoke_values())
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        str(path.resolve())
        for path in (
            ROOT / "services/product_api/src",
            ROOT / "services/gateway_api/src",
            ROOT,
        )
    )
    return environment


def _workflows() -> list[Path]:
    return sorted((ROOT / ".github/workflows").glob("*.yml"))


def test_workflows_have_no_floating_actions_images_runtimes_or_direct_install() -> None:
    for path in _workflows():
        text = path.read_text(encoding="utf-8")
        assert "ubuntu-latest" not in text
        assert re.search(r"uses:\s+[^\s]+@v\d", text) is None
        assert "python:3.12-slim" not in text
        assert "postgres:16-alpine" not in text
        if path.parent.name == "workflows":
            assert "python -m pip install" not in text
    action = (ROOT / ".github/actions/setup-python-ci/action.yml").read_text(encoding="utf-8")
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in action
    assert "python-version: 3.12.11" in action


def test_qa_has_one_exact_sha_and_all_required_build_once_jobs() -> None:
    text = QA.read_text(encoding="utf-8")
    for token in (
        "pull_request:", "workflow_call:", "resolve-release:", "python-unit-contract:",
        "postgres-full:", "web-static:", "release-build:", "browser-e2e-visual:",
        "release-contract:", "qa-required:",
    ):
        assert token in text
    assert "github.event.pull_request.head.sha" in text
    assert "github.sha" not in text
    assert "merge ref" not in text
    assert "qa-release-${{ needs.resolve-release.outputs.release_sha }}" in text
    assert text.count("ref: ${{ needs.resolve-release.outputs.release_sha }}") == 7
    assert "web-ui-playwright-runtime-$RELEASE_SHA.tgz" in text
    assert text.count("python deploy/product_api/release_manifest.py") == 2
    assert "install_web_ui_release.sh verify" in text
    assert "npm run build --prefix services/web_ui" in text
    assert text.count("npm run build --prefix services/web_ui") == 1
    assert f"version: {BUILDX_VERSION}" in text
    assert "version: latest" not in text
    assert "--network=none" in text and "--no-index" in (
        (ROOT / "services/product_api/Dockerfile").read_text(encoding="utf-8")
        + (ROOT / "services/gateway_api/Dockerfile").read_text(encoding="utf-8")
    )


def test_postgres_and_browser_identities_are_literal_and_runner_parity_is_exact() -> None:
    qa = QA.read_text(encoding="utf-8")
    runner = (ROOT / "scripts/run-iteration25-postgres-tests.ps1").read_text(encoding="utf-8")
    assert POSTGRES_IMAGE in qa
    assert POSTGRES_IMAGE in runner
    assert PLAYWRIGHT_IMAGE in qa
    assert "-Mode BrowserE2E" in qa
    assert "-ReleaseArtifactRoot" in qa
    assert "-ReleaseSha" in qa
    assert "COMPANY_CARD_V2_E2E_BASE_URL" not in qa
    assert "COMPANY_CARD_V2_E2E_MANIFEST" not in qa
    assert (ROOT / ".github/ci/playwright-font-inventory.sha256").read_text(encoding="ascii").strip() == "705c330e71882ba9b680add251004054dcdc680b5c646e814b5b5ea2b6b341b3"

    browser_job = qa.split("  browser-e2e-visual:", 1)[1].split(
        "  release-contract:", 1
    )[0]
    prepare = "- name: Prepare SHA-bound browser failure evidence"
    run_browser = "- name: Run runner-owned browser acceptance lifetime"
    upload = "- name: Upload SHA-bound browser failure evidence"
    assert browser_job.index(prepare) < browser_job.index(run_browser)
    assert browser_job.index(run_browser) < browser_job.index(upload)
    assert 'evidence_root="services/web_ui/.tmp/iteration25-playwright"' in browser_job
    assert 'printf \'release_sha=%s\\n\' "$RELEASE_SHA" > "$evidence_root/runner-context.txt"' in browser_job
    assert "if: always()" in browser_job.split(run_browser, 1)[0]
    upload_step = browser_job.split(upload, 1)[1]
    assert "if: failure()" in upload_step
    assert "path: services/web_ui/.tmp/iteration25-playwright/" in upload_step
    assert "include-hidden-files: true" in upload_step
    assert "if-no-files-found: error" in upload_step
    assert "services/web_ui/test-results/" not in browser_job
    assert "services/web_ui/playwright-report/" not in browser_job


def test_release_dockerfiles_share_exact_base_and_offline_audited_target() -> None:
    for path, service in (
        (ROOT / "services/product_api/Dockerfile", "product"),
        (ROOT / "services/gateway_api/Dockerfile", "gateway"),
    ):
        text = path.read_text(encoding="utf-8")
        assert f"FROM {PYTHON_BASE} AS base" in text
        assert "PIP_NO_CACHE_DIR=1" in text
        release = text.split("FROM base AS release", 1)[1].split("FROM base AS local", 1)[0]
        assert "--no-index" in release
        assert "--no-deps" in release
        assert "--require-hashes" in release
        assert "sha256sum -c wheelhouse.sha256" in release
        assert "pip check" in release
        assert "python-installed.json" in release
        assert " -e " not in release and "--upgrade" not in release
        other = "gateway_api" if service == "product" else "product_api"
        assert other not in release


def test_release_import_smoke_vars_are_exact_synthetic_and_network_unroutable() -> None:
    values = _release_import_smoke_values()

    assert set(values) == RELEASE_IMPORT_SMOKE_KEYS
    assert "OPENAI_API_KEY" not in values
    assert all("release-import-smoke" in value for value in values.values())

    database = urlsplit(values["DATABASE_URL"])
    assert database.scheme == "postgresql+asyncpg"
    assert database.hostname is not None and database.hostname.endswith(".invalid")
    assert database.username is None
    assert database.password is None
    assert database.query == "" and database.fragment == ""

    gateway = urlsplit(values["GATEWAY_URL"])
    assert gateway.scheme == "https"
    assert gateway.hostname is not None and gateway.hostname.endswith(".invalid")
    assert gateway.username is None and gateway.password is None
    assert gateway.query == "" and gateway.fragment == ""

    email_local, separator, email_domain = values["EMAIL_FROM"].partition("@")
    assert email_local and separator == "@" and email_domain.endswith(".invalid")
    assert values["CLAIMS_UPLOAD_DIR"].startswith("/tmp/release-import-smoke-")
    for key in (
        "GATEWAY_SHARED_SECRET",
        "AUTH_TOKEN_SECRET",
        "CLAIM_EDIT_TOKEN_SECRET",
        "INVITE_TOKEN_SECRET",
        "SESSION_SECRET",
    ):
        assert values[key].endswith("-not-a-secret")


def test_release_dockerfiles_mount_smoke_vars_read_only_without_persisting_them() -> None:
    mount = (
        "--mount=type=bind,source=.github/ci/release-import-smoke.vars,"
        "target=/run/release-import-smoke.vars,readonly"
    )
    for path, expected_imports in (
        (ROOT / "services/product_api/Dockerfile", PRODUCT_IMPORTS),
        (ROOT / "services/gateway_api/Dockerfile", GATEWAY_IMPORTS),
    ):
        text = path.read_text(encoding="utf-8")
        release = text.split("FROM base AS release", 1)[1].split(
            "FROM base AS local", 1
        )[0]
        assert release.count(mount) == 1
        assert release.index("set -a") < release.index(
            ". /run/release-import-smoke.vars"
        )
        assert release.index(". /run/release-import-smoke.vars") < release.index(
            "set +a"
        )
        assert release.index("set +a") < release.index(expected_imports)

        for instruction in _dockerfile_instructions(text):
            directive = instruction.split(maxsplit=1)[0].upper()
            if directive in {"ARG", "ENV"}:
                for key in RELEASE_IMPORT_SMOKE_KEYS:
                    assert re.search(rf"\b{re.escape(key)}\b", instruction) is None
            if directive == "COPY":
                assert "release-import-smoke.vars" not in instruction
                assert re.match(r"^COPY\s+(?:--\S+\s+)*\.\s", instruction) is None


def test_product_release_image_loads_flattened_alembic_layout_offline() -> None:
    product = (ROOT / "services/product_api/Dockerfile").read_text(encoding="utf-8")
    gateway = (ROOT / "services/gateway_api/Dockerfile").read_text(encoding="utf-8")
    release = product.split("FROM base AS release", 1)[1].split(
        "FROM base AS local", 1
    )[0]
    smoke = "python -m alembic -c /app/alembic.ini ensure_version --sql >/dev/null"

    assert "COPY services/product_api/alembic.ini /app/alembic.ini" in release
    assert "COPY services/product_api/alembic /app/alembic" in release
    assert release.count(smoke) == 1
    assert release.index("set +a") < release.index(smoke) < release.index(
        "rm -rf /wheelhouse /locks"
    )
    assert smoke not in gateway

    env = (ROOT / "services/product_api/alembic/env.py").read_text(encoding="utf-8")
    assert "BASE_DIR.parents[1]" not in env
    assert '(BASE_DIR, *BASE_DIR.parents)' in env
    assert 'candidate / "shared" / "__init__.py"' in env
    assert 'raise RuntimeError("unable to locate shared package root")' in env


def test_release_dockerfiles_require_numeric_epoch_without_runtime_env_leak() -> None:
    for path in (
        ROOT / "services/product_api/Dockerfile",
        ROOT / "services/gateway_api/Dockerfile",
    ):
        text = path.read_text(encoding="utf-8")
        release = text.split("FROM base AS release", 1)[1].split(
            "FROM base AS local", 1
        )[0]
        release_instructions = _dockerfile_instructions(release)

        epoch_args = [
            instruction
            for instruction in release_instructions
            if instruction == "ARG SOURCE_DATE_EPOCH"
        ]
        assert epoch_args == ["ARG SOURCE_DATE_EPOCH"]
        assert release.index("ARG SOURCE_DATE_EPOCH") < release.index("RUN ")
        assert release.index("ARG SOURCE_DATE_EPOCH") < release.index("pip install")

        case_start = 'case "$SOURCE_DATE_EPOCH" in'
        rejected_values = "''|*[!0-9]*)"
        rejection_message = "SOURCE_DATE_EPOCH must be a non-negative integer"
        assert case_start in release
        assert rejected_values in release
        assert rejection_message in release
        assert "exit 1" in release
        assert release.index(case_start) < release.index("pip install")
        assert release.index(rejected_values) < release.index("pip install")

        env_instructions = [
            instruction
            for instruction in _dockerfile_instructions(text)
            if instruction.split(maxsplit=1)[0].upper() == "ENV"
        ]
        assert all("SOURCE_DATE_EPOCH" not in instruction for instruction in env_instructions)


def test_qa_builds_and_loads_cached_and_no_cache_docker_archives_with_the_same_epoch() -> None:
    qa = QA.read_text(encoding="utf-8")
    build_lines = [
        line.strip()
        for line in qa.splitlines()
        if line.strip().startswith("docker buildx build ")
    ]
    epoch_arg = '--build-arg "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"'

    assert len(build_lines) == 2
    for line in build_lines:
        assert line.count(epoch_arg) == 1
        assert '--output "type=docker,oci-mediatypes=true,' in line
        assert "rewrite-timestamp=true" in line
        assert "--target release" in line
        assert "--network=none" in line
        assert "--load" not in line

    cached = next(line for line in build_lines if "--no-cache" not in line)
    reproducible = next(line for line in build_lines if "--no-cache" in line)
    assert 'dest=$first,rewrite-timestamp=true' in cached
    assert 'dest=$second,rewrite-timestamp=true' in reproducible
    assert '--tag "$image:$RELEASE_SHA"' in cached
    assert '--tag "$image:repro-$RELEASE_SHA"' in reproducible

    build_job = qa.split("  release-build:", 1)[1].split(
        "  browser-e2e-visual:", 1
    )[0]
    load_lines = [
        line.strip()
        for line in build_job.splitlines()
        if line.strip().startswith("docker load ")
    ]
    assert load_lines == [
        'docker load --input "$first"',
        'docker load --input "$second"',
    ]
    assert build_job.index(reproducible) < build_job.index(load_lines[0])
    assert build_job.index(load_lines[0]) < build_job.index(load_lines[1])
    assert build_job.index(load_lines[1]) < build_job.index(
        'docker run --rm --network=none --env-file '
    )
    assert 'bundle.extractfile("manifest.json")' in build_job
    assert 'bundle.extractfile("index.json")' in build_job
    assert "OCI manifest/config identity is not reproducible" in build_job


def test_release_contract_loads_exact_archives_without_rebuild() -> None:
    qa = QA.read_text(encoding="utf-8")
    contract = qa.split("  release-contract:", 1)[1].split(
        "  qa-required:", 1
    )[0]
    load_lines = [
        line.strip()
        for line in contract.splitlines()
        if line.strip().startswith("docker load ")
    ]

    assert load_lines == [
        'docker load --input ".release/verified/product-api-$RELEASE_SHA.oci.tar"',
        'docker load --input ".release/verified/gateway-api-$RELEASE_SHA.oci.tar"',
    ]
    assert "docker build" not in contract
    assert contract.index(load_lines[0]) < contract.index(load_lines[1])
    assert contract.index(load_lines[1]) < contract.index(
        'docker run --rm --network=none --env-file '
    )
    assert "mapfile -t expected_images" in contract
    assert 'get("config_digest")' in contract
    assert 're.fullmatch(r"sha256:[0-9a-f]{64}", digest)' in contract
    assert 'test "${#expected_images[@]}" -eq 2' in contract
    assert (
        "docker image inspect --format '{{.Id}}' \"b2b-product-api:$RELEASE_SHA\""
        in contract
    )
    assert (
        "docker image inspect --format '{{.Id}}' \"b2b-gateway-api:$RELEASE_SHA\""
        in contract
    )


def test_qa_uses_one_ephemeral_env_file_for_every_offline_image_import() -> None:
    qa = QA.read_text(encoding="utf-8")
    env_option = "--env-file .github/ci/release-import-smoke.vars"
    smoke_runs = [
        line.strip()
        for line in qa.splitlines()
        if "docker run " in line and "--entrypoint python" in line
    ]

    assert len(smoke_runs) == 3
    assert all("--rm --network=none" in line for line in smoke_runs)
    assert all(env_option in line for line in smoke_runs)
    assert qa.count(env_option) == 3
    assert f'smoke_imports="{PRODUCT_IMPORTS}"' in qa
    assert f'smoke_imports="{GATEWAY_IMPORTS}"' in qa
    assert any(PRODUCT_IMPORTS in line for line in smoke_runs)
    assert any(GATEWAY_IMPORTS in line for line in smoke_runs)

    assert 'for built_image in "$image:$RELEASE_SHA" "$image:repro-$RELEASE_SHA"; do' in qa
    assert "docker image inspect \"$built_image\" --format '{{range .Config.Env}}{{println .}}{{end}}'" in qa
    assert "while IFS='=' read -r key smoke_value; do" in qa
    assert 'grep -q "^${key}=" <<< "$image_env"' in qa
    assert "done < .github/ci/release-import-smoke.vars" in qa


def test_release_smoke_vars_import_all_product_and_gateway_entrypoints(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"{PRODUCT_IMPORTS}; {GATEWAY_IMPORTS}"],
        cwd=tmp_path,
        env=_release_import_subprocess_env(include_smoke_values=True),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_release_entrypoints_remain_fail_closed_without_smoke_vars(
    tmp_path: Path,
) -> None:
    environment = _release_import_subprocess_env(include_smoke_values=False)
    for imports, required_key in (
        (PRODUCT_IMPORTS, "DATABASE_URL"),
        (GATEWAY_IMPORTS, "GATEWAY_SHARED_SECRET"),
    ):
        result = subprocess.run(
            [sys.executable, "-c", imports],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode != 0
        assert required_key in result.stdout + result.stderr


def test_product_compose_keeps_local_sha_optional_and_deploy_supplies_exact_sha() -> None:
    compose = (ROOT / "docker-compose.product.yml").read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert "target: local" in compose
    assert "target: release" not in compose
    assert compose.count("- PRODUCT_RELEASE_COMMIT") == 3
    assert "PRODUCT_RELEASE_COMMIT:?" not in compose
    assert "PRODUCT_RELEASE_COMMIT='$RELEASE_SHA'" in deploy
    assert "--no-build --force-recreate product_api company_report_worker company_card_narrative_worker" in deploy


def test_normal_deploy_preserves_exact_claims_bind_for_candidate_and_rollback() -> None:
    compose = (ROOT / "docker-compose.product.yml").read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")
    product = compose.split("  product_api:", 1)[1].split(
        "  company_report_worker:", 1
    )[0]
    workers = compose.split("  company_report_worker:", 1)[1]
    assert "source: ${CLAIMS_UPLOAD_ROOT:" in product
    assert "target: ${CLAIMS_UPLOAD_DIR:" in product
    assert "CLAIMS_UPLOAD_ROOT" not in workers
    for token in (
        "CLAIMS_UPLOAD_ROOT') == '/var/lib/pork/claims-uploads/v1'",
        "CLAIMS_UPLOAD_DIR') == '/data/claims_uploads'",
        "stat -c '%u:%g:%a'",
        "/var/lib/pork/claims-uploads/v1|/data/claims_uploads|true",
    ):
        assert token in deploy
    candidate = deploy.split(
        "Upgrade additive schema and recreate exact Product/workers", 1
    )[1].split("Recreate and verify exact Gateway", 1)[0]
    rollback = deploy.split(
        "Fail-closed restore of prior Product and workers", 1
    )[1].split("Fail-closed restore of prior Gateway", 1)[0]
    for section in (candidate, rollback):
        assert "/var/lib/pork/claims-uploads/v1|/data/claims_uploads|true" in section
        assert 'if test \\"\\$service\\" = product_api' in section


def test_gateway_release_identity_is_exact_in_normal_deploy_and_rollback() -> None:
    compose = (ROOT / "deploy/us/compose/docker-compose.gateway.yml").read_text(
        encoding="utf-8"
    )
    deploy = DEPLOY.read_text(encoding="utf-8")
    settings = (ROOT / "services/gateway_api/src/gateway_api/settings.py").read_text(
        encoding="utf-8"
    )
    main = (ROOT / "services/gateway_api/src/gateway_api/main.py").read_text(
        encoding="utf-8"
    )
    assert "- GATEWAY_RELEASE_COMMIT" in compose
    assert 're.fullmatch(r"[0-9a-f]{40}"' in settings
    assert '"release_commit": settings.gateway_release_commit' in main
    assert "prior-gateway-release-sha" in deploy
    assert "GATEWAY_RELEASE_COMMIT='$RELEASE_SHA'" in deploy
    assert 'grep -Fx \'GATEWAY_RELEASE_COMMIT=$RELEASE_SHA\'' in deploy
    rollback = deploy.split("Fail-closed restore of prior Gateway", 1)[1]
    assert 'GATEWAY_RELEASE_COMMIT=\\"\\$old_commit\\"' in rollback
    assert "grep -Eq '^[0-9a-f]{40}$' '$US_STAGE/prior-gateway-release-sha'" in rollback


def test_product_example_keeps_privacy_key_unset_and_collection_closed() -> None:
    lines = (ROOT / "services/product_api/.env.example").read_text(encoding="utf-8").splitlines()
    assert "COMPANY_CARD_V2_ARBITRATION_COLLECTION_ENABLED=false" in lines
    active = [line for line in lines if line and not line.startswith("#")]
    assert not any(line.startswith("COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID=") for line in active)
    assert not any(line.startswith("COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON=") for line in active)


def test_deploy_is_manual_current_main_protected_qa_consumer_in_exact_order() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    candidate = (ROOT / "deploy/product_api/fresh_install_candidate.py").read_text(
        encoding="utf-8"
    )
    assert "workflow_dispatch:" in text
    assert "push:" not in text and "pull_request:" not in text
    assert "group: prod-deploy" in text
    assert "cancel-in-progress: false" in text
    assert "environment: production" in text
    assert "github.workflow_sha" in text and "github.workflow_ref" in text
    assert "ref: refs/heads/main" in text
    assert "git cat-file -e \"$RELEASE_SHA^{commit}\"" in text
    assert "git merge-base --is-ancestor" in text
    assert "required_statuses" in text and '["qa-required"]' in text
    assert "production_environment_required_reviewers" in text
    assert "deployment_window_start_utc" in text and "deployment_window_end_utc" in text
    assert 'data["release_sha"] != os.environ["RELEASE_SHA"]' in text
    assert "company_card_v2_qa_attestation_v1" in text
    assert 'set(jobs) != {' in text
    assert "needs: [trusted-main-and-p1, qa]" in text
    assert "npm run build" not in text and "docker build" not in text
    assert "|| true" not in text
    sentinels = [
        "Download sole build-once release",
        "Read-only RU/US preflight",
        "Offline verify candidate provider preservation before live mutation",
        "Install and loopback-verify H2 assets",
        "Drain both exact old workers",
        "python -m alembic -c /app/alembic.ini upgrade head",
        "Recreate and verify exact Gateway",
        "Atomically switch Web",
    ]
    positions = [text.index(token) for token in sentinels]
    assert positions == sorted(positions)
    for gate in range(1, 10):
        assert f"p{gate}_" in text.lower()
    assert "provider_mode" in text and "preserve" in text
    assert "prior-provider-state" in text
    assert "--provider-state" in text
    assert "fallback-only" in text and "noindex-no-assignment" in text
    assert ". /opt/b2b/.env.product" not in text
    assert "prior-product-env" not in text
    assert "--settings-container" in text
    assert "worker-drain-result.json" in text
    assert "database_target_sha256" in text
    assert 'test \\"\\$candidate_db_sha\\" = \\"\\$drained_db_sha\\"' in text
    assert text.count("['images'][sys.argv[2]]['config_digest']") == 3
    assert text.count('test \\"\\$candidate_image\\" = \\"\\$expected_image\\"') == 3
    assert text.count("docker inspect --format '{{.Image}}'") >= 4
    assert "sha256sum --strict --ignore-missing --check" in text
    assert "com.docker.compose.project" in text
    assert "prior-product-compose-project" in text
    assert "prior-gateway-compose-project" in text
    assert text.count('docker compose -p \\"\\$project\\"') >= 8
    assert "secrets.PROD_SSH_KEY" in text
    assert "ssh-add - >/dev/null" in text
    assert "ssh-agent -k >/dev/null" in text
    assert "steps.h2.outputs.armed == 'true'" in text
    assert "steps.product.outputs.armed == 'true'" in text
    assert "steps.gateway.outputs.armed == 'true'" in text
    assert "steps.web.outputs.armed == 'true'" in text
    assert "fresh_install_candidate.py" in text
    assert "python - settings --release-sha '$RELEASE_SHA'" in text
    assert "python - gateway --release-sha '$RELEASE_SHA'" in text
    assert "settings.company_card_v2_allowlist_inns == []" in candidate
    assert "settings.company_card_v2_narrative_daily_limit == 0" in candidate
    assert "settings.company_card_v2_arbitration_mask_keyring_json is None" in candidate
    assert "candidate settings contract mismatch; STOP" in candidate
    assert "assert " not in text
    assert text.count("python deploy/product_api/release_manifest.py") == 1


def test_deploy_checks_effective_provider_and_secret_presence_before_any_live_mutation() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    candidate = (ROOT / "deploy/product_api/fresh_install_candidate.py").read_text(
        encoding="utf-8"
    )
    offline_name = "Offline verify candidate provider preservation before live mutation"
    offline = text.split(offline_name, 1)[1].split(
        "Install and loopback-verify H2 assets before process or DB mutation", 1
    )[0]
    assert text.index("prior-provider-state") < text.index(offline_name)
    assert text.index(offline_name) < text.index("Install and loopback-verify H2 assets")
    assert text.index(offline_name) < text.index("Drain both exact old workers")
    assert text.index(offline_name) < text.index(
        "python -m alembic -c /app/alembic.ini upgrade head"
    )
    assert "docker run --rm --network none --env-file /opt/b2b/.env.product" in offline
    assert "fresh_install_candidate.py settings" in offline
    assert "provider == provider_state" in candidate
    assert "datanewton_api_key" in candidate
    assert 'key_ok = provider != "enabled" or bool(' in candidate
    for token in (
        "not s.company_card_v2_presentations_enabled",
        "not s.company_card_v2_writer_enabled",
        "s.company_card_v2_rollout_generation == 0",
        "s.company_card_v2_allowlist_inns == []",
        "s.company_card_v2_percentage_basis_points == 0",
        "not s.company_card_v2_arbitration_collection_enabled",
        "s.company_card_v2_arbitration_mask_active_key_id is None",
        "s.company_card_v2_arbitration_mask_keyring_json is None",
        "not s.company_card_v2_narrative_enabled",
        "s.company_card_v2_narrative_kill_switch",
        "s.company_card_v2_narrative_daily_limit == 0",
        "s.company_card_v2_narrative_monthly_limit == 0",
        "s.company_card_v2_narrative_concurrency == 0",
    ):
        assert token.replace("s.", "settings.") in candidate
    assert "print(settings.datanewton_api_key" not in candidate
    assert "echo $DATANEWTON" not in text


def test_legacy_0015_bootstrap_is_manual_exact_main_and_one_time_guarded() -> None:
    text = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "push:" not in text and "pull_request:" not in text
    assert "group: prod-deploy" in text and "cancel-in-progress: false" in text
    assert "environment: production" in text
    assert "ref: refs/heads/main" in text
    assert "github.workflow_ref" in text and "github.workflow_sha" in text
    assert "git merge-base --is-ancestor" in text
    assert text.count("6bee95e881a3e9ea1fe324ca13c11ae239f896f4") >= 2
    assert "0015_claims_company_report_handoff" in text
    assert "needs: [trusted-exact-legacy-guard, qa]" in text
    assert "npm run build" not in text and "docker build" not in text
    assert "|| true" not in text
    for identity in (
        "prior_product_image_config_sha256",
        "prior_product_compose_sha256",
        "prior_nginx_sha256",
        "prior_web_tree_sha256",
    ):
        assert identity in text
    assert "for name in PRIOR_IMAGE_CONFIG_SHA256 PRIOR_COMPOSE_SHA256 PRIOR_NGINX_SHA256 PRIOR_WEB_TREE_SHA256" in text
    assert text.count("^[0-9a-f]{64}$") >= 4


def test_legacy_0015_bootstrap_requires_exact_qa_seed_and_external_recovery() -> None:
    workflow = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
    runner = LEGACY_BOOTSTRAP_RUNNER.read_text(encoding="utf-8")
    combined = workflow + "\n" + runner
    for token in (
        "qa-release-{release_sha}",
        "company_card_v2_qa_attestation_v1",
        "company-public-h2-seed-bundle-e7478a2fba9aaca17829c3d99e89e8d83d4b3188",
        "seed_bundle_run_id",
        "seed_bundle_sha256",
        "database_backup_artifact_id",
        "database_backup_artifact_sha256",
        "database_recovery_hook_sha256",
        "RU_LEGACY_0015_DB_RECOVERY_HOOK",
        "RU_LEGACY_0015_DB_BACKUP_ARTIFACT",
    ):
        assert token in workflow
    assert "verify-bundle" in combined
    assert ".release/seed/extracted/seed-bundle/seed-inventory.json" in workflow
    assert '"$seed_extract/seed-inventory.json"' in runner
    assert "seed archive member invalid; STOP" in workflow
    assert '"$recovery_hook" verify-current-frozen ' in runner
    assert '"$recovery_hook" restore ' in runner
    assert '"$recovery_hook" verify-restored ' in runner
    assert "frozen/PITR recovery set covering writes through quiesce" in workflow
    assert "atomically bind" in workflow and "exact quiesced revision-0015 recovery" in workflow
    assert "never creates" in workflow and "pretends to create" in workflow
    assert "pg_dump" not in combined and "pg_restore" not in combined


def test_legacy_0015_bootstrap_guards_runtime_shape_and_initial_stores() -> None:
    workflow = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
    runner = LEGACY_BOOTSTRAP_RUNNER.read_text(encoding="utf-8")
    combined = workflow + "\n" + runner
    for token in (
        "com.docker.compose.service",
        "company_report_worker",
        "company_card_narrative_worker",
        "root /opt/b2b/services/web_ui/dist;",
        "test ! -e /var/lib/pork/web-ui/v1/current",
        "test ! -e /var/lib/pork/web-ui/v1/release-set.json",
        "prior-docker-compose.product.yml",
        "prior-nginx.conf",
        "prior-provider-state",
    ):
        assert token in combined
    assert "legacy_0015_worker_drain.py" in combined
    assert runner.count("--container") == 1
    assert "worker_drain.py' --container" not in combined
    assert combined.count("docker port") >= 2
    assert combined.count("127.0.0.1:8000") >= 2
    preflight = workflow.split(
        "Exact read-only legacy-0015 preflight and external recovery verification", 1
    )[1].split("Reset only exact stale retry markers after guarded preflight", 1)[0]
    assert preflight.count("HostConfig.RestartPolicy.Name") == 2
    assert "global_product_output=$(docker ps -q" in preflight
    assert "global_report_output=$(docker ps -q" in preflight
    assert "global_narrative_output=$(docker ps -q" in preflight
    assert "mapfile -t global_product_ids <<<" in preflight
    assert "mapfile -t global_report_ids <<<" in preflight
    assert "mapfile -t global_narrative_ids <<<" in preflight
    assert 'test "${#global_product_ids[@]}" -eq 1' in preflight
    assert 'test "${#global_report_ids[@]}" -eq 1' in preflight
    assert 'test "${#global_narrative_ids[@]}" -eq 0' in preflight
    assert 'test "${global_product_ids[0]}" = "$product_id"' in preflight
    assert 'test "${global_report_ids[0]}" = "$report_id"' in preflight
    assert 'test "$old_image" = "sha256:$PRIOR_IMAGE_CONFIG_SHA256"' in preflight
    assert "sha256sum /opt/b2b/docker-compose.product.yml" in preflight
    assert "sha256sum /etc/nginx/sites-available/pork.su.conf" in preflight
    assert 'test "$legacy_web_tree_sha256" = "$PRIOR_WEB_TREE_SHA256"' in preflight
    assert "rolled_back_retry=false" in preflight
    assert preflight.count('test "$rolled_back_retry" = false') == 2
    assert "find /var/lib/pork/web-ui/v1 -mindepth 1 -maxdepth 1" in preflight
    assert "find /var/lib/pork/company-public-h2/v1 -mindepth 1 -maxdepth 1" in preflight
    assert "one-time bootstrap already succeeded; repeat execution is forbidden; STOP" in preflight
    candidate = runner.split(
        "--force-recreate product_api company_report_worker company_card_narrative_worker", 1
    )[1].split("marker product-complete", 1)[0]
    assert "{{.Config.Image}}" in candidate
    assert "{{.State.Running}}" in candidate
    assert "candidate_global_products" in candidate
    assert "candidate_global_reports" in candidate
    assert "candidate_global_narratives" in candidate
    assert 'docker port "$candidate_product_id" 8000/tcp' in candidate


def test_legacy_0015_bootstrap_phase_order_and_db_first_rollback_are_explicit() -> None:
    workflow = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
    runner = LEGACY_BOOTSTRAP_RUNNER.read_text(encoding="utf-8")
    workflow_sentinels = (
        "Exact read-only legacy-0015 preflight and external recovery verification",
        "Reset only exact stale retry markers after guarded preflight",
        "Upload exact candidate, reviewed seed and bootstrap tools",
        "Offline verify bootstrap candidate provider preservation before live mutation",
        "Launch one durable remote bootstrap transaction",
        "Wait for durable bridge, drain, migration, Web and public checks",
    )
    assert [workflow.index(value) for value in workflow_sentinels] == sorted(
        workflow.index(value) for value in workflow_sentinels
    )
    runner_sentinels = (
        "# Phase 1:",
        "product_api_legacy_0015_h2_bootstrap.conf",
        "# Phase 2:",
        "marker drain-armed",
        "legacy_0015_worker_drain.py",
        "# Phase 3:",
        '"$recovery_hook" verify-current-frozen ',
        "marker migration-armed",
        "python -m alembic -c /app/alembic.ini upgrade head",
        "marker product-complete",
        "# Phase 4:",
        "install_web_ui_release.sh",
        "product_api.conf",
        "https://pork.su/api/internal/whoami",
        "marker bootstrap-success",
    )
    forward = runner.split("# Phase 1:", 1)[1]
    runner_sentinels = runner_sentinels[1:]
    assert [forward.index(value) for value in runner_sentinels] == sorted(
        forward.index(value) for value in runner_sentinels
    )

    rollback = runner.split("rollback_legacy() (", 1)[1].split("finish() {", 1)[0]
    candidate_stop = rollback.index("stop_exact_container")
    restore = rollback.index('"$recovery_hook" restore ')
    verified = rollback.index('"$recovery_hook" verify-restored ')
    old_runtime = rollback.index("b2b-product-api:legacy-0015-rollback")
    legacy_up = rollback.index("--force-recreate product_api company_report_worker")
    runtime_verified = rollback.index("sole_legacy_revision")
    nginx_restore = rollback.index('install -m 640 "$stage/prior-nginx.conf"')
    assert candidate_stop < restore < verified < old_runtime < legacy_up
    assert legacy_up < runtime_verified < nginx_restore
    assert "SIGKILL" not in rollback
    assert "docker kill --signal=TERM" in runner
    assert "company_card_narrative_worker" in rollback and "docker rm" in rollback

    pre_migration = rollback.split('if path_present "$stage/migration-armed"; then', 2)[2]
    drain_armed = pre_migration.split('if path_present "$stage/drain-armed"; then', 1)[1]
    product_stop = drain_armed.index('stop_exact_container "$product_id"')
    report_stop = drain_armed.index('stop_exact_container "$report_id"')
    restart = drain_armed.index("docker update --restart=unless-stopped")
    report_running = drain_armed.index(
        'test "$(rollback_bounded docker inspect --format \'{{.State.Running}}\' "$report_id")" = true',
        restart,
    )
    assert product_stop < report_stop < restart < report_running


def test_legacy_0015_bootstrap_is_a_durable_cancel_independent_transaction() -> None:
    workflow = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
    runner = LEGACY_BOOTSTRAP_RUNNER.read_text(encoding="utf-8")
    launch = workflow.split("Launch one durable remote bootstrap transaction", 1)[1].split(
        "Wait for durable bridge, drain, migration, Web and public checks", 1
    )[0]
    assert "systemd-run" not in launch and "--scope" not in launch
    assert 'unit_path="/etc/systemd/system/$unit.service"' in launch
    assert "Description=One-time exact legacy-0015 production bootstrap with boot recovery" in launch
    assert "WantedBy=multi-user.target" in launch
    assert "Restart=on-failure" in launch and "RestartSec=30" in launch
    assert "Type=exec" in launch and "User=root" in launch
    assert "KillMode=control-group" in launch and "KillSignal=SIGTERM" in launch
    assert "RuntimeMaxSec=7200" in launch and "TimeoutStopSec=3600" in launch
    assert "SendSIGKILL=yes" in launch
    assert 'systemctl enable --now "$unit.service"' in launch
    assert "legacy_0015_bootstrap_runner.sh" in launch
    assert "runner_sha" in launch
    assert "legacy-bootstrap-tools-$release_sha.sha256" in launch
    assert 'sha256sum --strict --check "$tool_manifest"' in launch
    assert 'sync -f "$stage/$name"' in launch
    assert 'sync -f "$recovery_hook"' in launch
    assert 'sync -f "$backup_artifact"' in launch
    assert 'sync -f "$stage"' in launch
    assert 'mv -T "$unit_temporary" "$unit_path"' in launch
    assert 'sync -f "$unit_path"' in launch
    assert "install -m 644 \"$unit_temporary\"" not in launch
    assert 'if test -e "$unit_path" || test -L "$unit_path"; then' in launch
    assert 'test "$(stat -c \'%u:%a\' -- "$unit_path")" = "0:640"' in launch
    exact_existing_unit = launch.index('cmp -s "$unit_temporary" "$unit_path"')
    enable = launch.index('systemctl enable --now "$unit.service"')
    assert exact_existing_unit < enable
    assert "matching durable bootstrap unit is already active; STOP" not in launch
    assert workflow.index("Offline verify bootstrap candidate") < workflow.index(
        "Launch one durable remote bootstrap transaction"
    )
    assert "exec 9<\"$stage\"" in runner and "flock -x 9" in runner
    assert "trap finish EXIT" in runner
    assert "trap 'exit 143' TERM INT HUP" in runner
    assert runner.index("marker bridge-armed") < runner.index(
        "product_api_legacy_0015_h2_bootstrap.conf"
    )
    assert runner.index("marker drain-armed") < runner.index(
        "docker update --restart=no \"$product_id\""
    )
    assert runner.index("marker migration-armed") < runner.index(
        "python -m alembic -c /app/alembic.ini upgrade head"
    )
    web_forward = runner.split("# Phase 4:", 1)[1]
    assert web_forward.index("marker web-armed") < web_forward.index(
        "install_web_ui_release.sh"
    )
    assert web_forward.index("https://pork.su/api/internal/whoami") < web_forward.index(
        "marker bootstrap-success"
    )
    assert "sync -f \"$temporary\"" in runner and "sync -f \"$stage\"" in runner
    assert "rollback_bounded" in runner
    assert "timeout --foreground --signal=TERM --kill-after=30" in runner
    assert "rollback_deadline_epoch=$((EPOCHSECONDS + 3300))" in runner
    assert "rollback_deadline_epoch - EPOCHSECONDS - 90" in runner
    assert "terminal_bounded()" in runner and "120s" in runner
    assert 'sync -f "$unit_path"' in runner
    assert "multi-user.target.wants/$unit_name.service" in runner
    assert "operation_timeout_seconds" in workflow
    assert "rollback_timeout_seconds" in workflow
    assert "drain deadline plus shutdown margin" in workflow
    assert "reconciliation_only=true" in runner
    assert runner.index("reconciliation_only=true") < runner.index("# Phase 1:")
    assert "marker_once rollback-complete terminal_bounded" in runner
    assert "status=0" in runner
    assert 'systemctl disable "$unit_name.service"' in runner
    observer = workflow.split(
        "Observe durable DB-first rollback after any unsuccessful transaction", 1
    )[1].split("Stop local bootstrap credential agent", 1)[0]
    assert "always()" in observer
    assert "steps.bootstrap_success.outputs.complete != 'true'" in observer
    assert '"$recovery_hook" restore ' not in workflow
    assert "failure()" not in workflow

    runtime_seconds = 7200
    stop_seconds = 3600
    poll_seconds = 5
    poll_attempts = 2220
    observer_timeout_minutes = 190
    assert poll_attempts * poll_seconds >= runtime_seconds + stop_seconds + 300
    assert observer_timeout_minutes * 60 >= poll_attempts * poll_seconds
    assert workflow.count("timeout-minutes: 190") >= 2
    assert workflow.count("for attempt in $(seq 1 2220)") >= 2


def test_legacy_0015_bootstrap_atomic_seed_is_retry_independent() -> None:
    runner = LEGACY_BOOTSTRAP_RUNNER.read_text(encoding="utf-8")
    h2 = runner.split("# Phase 1:", 1)[1].split("# Phase 2:", 1)[0]
    assert 'mktemp -d -p "$stage" .seed-extract.' in h2
    assert 'mktemp -d -p "$stage" .candidate-h2.' in h2
    assert "seed_company_public_h2_assets.sh" in h2
    assert 'company_public_h2_seed.py seed "$h2_root"' not in h2
    assert "os.rename(source, target)" not in h2
    assert "rm -rf" not in h2
    assert "values not in (seed, candidate)" in h2
    assert "candidate H2 set mismatch" in h2
    assert "stat -c '%u:%g:%a'" in h2
    assert 'ensure_private_directory "$h2_parent"' in h2
    assert 'ensure_private_directory "$h2_root"' in h2
    assert "8#$parent_mode & 8#022" in runner
    assert 'bounded install -d -m 750 "$h2_parent"' not in h2


def test_legacy_0015_bootstrap_preserves_provider_and_keeps_h2_default_off() -> None:
    workflow = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
    runner = LEGACY_BOOTSTRAP_RUNNER.read_text(encoding="utf-8")
    combined = workflow + "\n" + runner
    assert "options: [preserve]" in workflow
    assert "EXPECTED_PROVIDER_STATE" in combined
    offline = workflow.split(
        "Offline verify bootstrap candidate provider preservation before live mutation", 1
    )[1].split("Launch one durable remote bootstrap transaction", 1)[0]
    assert "datanewton_api_key" in offline
    assert "key_ok=actual != 'enabled'" in offline
    for token in (
        "not s.company_card_v2_presentations_enabled",
        "not s.company_card_v2_writer_enabled",
        "s.company_card_v2_rollout_generation == 0",
        "s.company_card_v2_allowlist_inns == []",
        "s.company_card_v2_percentage_basis_points == 0",
        "not s.company_card_v2_arbitration_collection_enabled",
        "s.company_card_v2_arbitration_mask_active_key_id is None",
        "s.company_card_v2_arbitration_mask_keyring_json is None",
        "not s.company_card_v2_narrative_enabled",
        "s.company_card_v2_narrative_kill_switch",
        "s.company_card_v2_narrative_daily_limit == 0",
        "s.company_card_v2_narrative_monthly_limit == 0",
        "s.company_card_v2_narrative_concurrency == 0",
    ):
        assert token in offline
        assert token in runner


def test_legacy_0015_bootstrap_requires_exact_sole_revision_not_matching_output() -> None:
    workflow = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
    runner = LEGACY_BOOTSTRAP_RUNNER.read_text(encoding="utf-8")
    assert "alembic -c alembic.ini current | grep" not in workflow
    assert "alembic -c alembic.ini current | grep" not in runner
    assert "legacy_revision=$(docker exec" in workflow
    assert "legacy database must have exactly sole revision 0015; STOP" in workflow
    assert "sole_legacy_revision" in runner
    assert "database is not exactly sole revision 0015; STOP" in runner
    assert runner.count("sole_legacy_revision") >= 2


def test_legacy_0015_bootstrap_rechecks_exact_legacy_web_tree_before_mutation_and_rollback() -> None:
    workflow = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
    runner = LEGACY_BOOTSTRAP_RUNNER.read_text(encoding="utf-8")
    assert 'printf \'%s\\n\' "$legacy_web_tree_sha256" > "$stage/prior-web-tree-sha256"' in workflow
    assert "prior-web-tree-sha256" in workflow.split(
        "Launch one durable remote bootstrap transaction", 1
    )[1]
    assert "legacy_web_tree_sha256()" in runner
    assert runner.count("legacy_web_tree_sha256 /opt/b2b/services/web_ui/dist") == 2
    assert "legacy_web_tree_sha256 /opt/b2b/services/web_ui/dist rollback_bounded" in runner
    rollback = runner.split("rollback_legacy() (", 1)[1].split("finish() {", 1)[0]
    assert rollback.index("legacy_web_tree_sha256 /opt/b2b/services/web_ui/dist") < rollback.index(
        'install -m 640 "$stage/prior-nginx.conf"'
    )
    assert '\"$limiter\" python3 - "$root"' in runner


def test_legacy_0015_bootstrap_docker_identity_queries_propagate_failures() -> None:
    workflow = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
    runner = LEGACY_BOOTSTRAP_RUNNER.read_text(encoding="utf-8")
    assert "collect_ids()" in runner
    assert "mapfile -t ids < <(rollback_bounded docker" not in runner
    assert "mapfile -t products < <(bounded docker" not in runner
    preflight = workflow.split(
        "Exact read-only legacy-0015 preflight and external recovery verification", 1
    )[1].split("Reset only exact stale retry markers after guarded preflight", 1)[0]
    assert "mapfile -t global_product_ids < <(docker" not in preflight
    assert "global_product_output=$(docker ps -q" in preflight


def test_legacy_0015_bootstrap_retry_contract_retains_only_immutable_orphans() -> None:
    workflow = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
    runner = LEGACY_BOOTSTRAP_RUNNER.read_text(encoding="utf-8")
    combined = workflow + "\n" + runner
    assert "rollback-uninitialized" in runner
    assert "rm -rf" not in combined and "rmtree" not in combined
    assert "legacy-worker-drain-result.json" in runner
    assert "cat \"$stage/legacy-worker-drain-result.json\"" not in runner
    reset = workflow.split(
        "Reset only exact stale retry markers after guarded preflight", 1
    )[1].split("Upload exact candidate, reviewed seed and bootstrap tools", 1)[0]
    assert "one-time bootstrap already succeeded; repeat execution is forbidden; STOP" in reset
    assert 'success="$stage/bootstrap-success"' in reset
    assert 'unlink "$success"' not in reset
    assert "rolled_back=false" in reset and 'test "$rolled_back" = true' in reset
    deletion = reset.split("for name in bridge-armed bridge-complete", 2)[2]
    assert "bootstrap-success" not in deletion
    nonterminal_unlink = deletion.index('unlink "$path"')
    durable_nonterminal_delete = deletion.index('sync -f "$stage"', nonterminal_unlink)
    terminal_unlink = deletion.index('unlink "$rollback_complete"')
    durable_terminal_delete = deletion.index('sync -f "$stage"', terminal_unlink)
    assert nonterminal_unlink < durable_nonterminal_delete < terminal_unlink < durable_terminal_delete
    for forbidden in ("DATABASE_URL=", "PGPASSWORD", '"report_id":', '"inn":'):
        assert forbidden not in combined


def test_recovery_docs_are_superseded_by_schema_only_fresh_install() -> None:
    old_spec = RECOVERY_SPEC.read_text(encoding="utf-8")
    old_plan = RECOVERY_PLAN.read_text(encoding="utf-8")
    spec = FRESH_INSTALL_SPEC.read_text(encoding="utf-8")
    plan = FRESH_INSTALL_PLAN.read_text(encoding="utf-8")
    runbook = RECOVERY_RUNBOOK.read_text(encoding="utf-8")
    for old in (old_spec, old_plan):
        assert "SUPERSEDED BY OWNER DECISION" in old
        assert "iteration-25-production-fresh-install.md" in old
    for current in (spec, plan, runbook):
        assert "DROP-AND-RECREATE-PRODUCTION-PUBLIC-SCHEMA" in current
        assert "Claims" in current
        assert "backup" in current.lower() and "bootstrap" in current.lower()
    assert "DROP SCHEMA public CASCADE" in spec
    assert "never delete/copy Claims paths" in runbook


def test_asset_installers_bind_exact_nginx_worker_group_in_bootstrap_and_normal_deploy() -> None:
    bootstrap = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
    runner = LEGACY_BOOTSTRAP_RUNNER.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")
    bootstrap_preflight = bootstrap.split(
        "Exact read-only legacy-0015 preflight and external recovery verification", 1
    )[1].split("Reset only exact stale retry markers after guarded preflight", 1)[0]
    for token in (
        "getent group www-data",
        "nginx -T",
        "ps -C nginx -o user=,group=",
        "www-data:www-data",
    ):
        assert token in bootstrap_preflight
    assert bootstrap.index("nginx_workers=") < bootstrap.index("Launch one durable remote bootstrap transaction")
    assert "'Group=www-data'" in bootstrap
    assert "$EGID" not in runner
    assert "runner_gid=$(id -g)" in runner
    assert 'test "$(id -gn)" = www-data' in runner
    assert runner.count("verify_nginx_tree_access") == 4
    assert "runuser --user www-data --group www-data -- find" in runner
    assert runner.index("ensure_private_directory /var/lib/pork") < runner.index(
        'ensure_private_directory "$h2_parent"'
    )

    normal_preflight = deploy.split("Read-only RU/US preflight", 1)[1].split(
        "Upload exact verified release and owned deploy tools", 1
    )[0]
    assert "nginx_workers=" in normal_preflight
    assert "www-data:www-data" in normal_preflight
    assert "stat -c '%u:%g:%a'" in normal_preflight
    assert "! -group www-data" in normal_preflight
    assert "-type d ! -perm 0750" in normal_preflight
    assert "-type f ! -perm 0640" in normal_preflight
    assert "runuser --user www-data --group www-data -- find" in normal_preflight
    assert "runuser --user root --group www-data -- bash install_company_public_h2_assets.sh" in deploy
    assert "runuser --user root --group www-data -- python3 '$RU_STAGE/install_web_ui_release.sh'" in deploy
    assert "runuser --user root --group www-data -- install -m 640 '$RU_STAGE/prior-h2-manifest-set.json'" in deploy
    assert "runuser --user root --group www-data -- install -m 640 '$RU_STAGE/prior-web-release-set.json'" in deploy
    assert deploy.count("runuser --user www-data --group www-data -- find /var/lib/pork/company-public-h2/v1") >= 2
    assert deploy.count("runuser --user www-data --group www-data -- find /var/lib/pork/web-ui/v1") >= 2


def test_normal_and_legacy_deploys_fail_closed_against_fresh_install_recovery() -> None:
    deploy = DEPLOY.read_text(encoding="utf-8")
    bootstrap = LEGACY_BOOTSTRAP.read_text(encoding="utf-8")
    normal_preflight = deploy.split(
        "Read-only RU/US preflight and record compatible prior identities", 1
    )[1].split("Upload exact verified release and owned deploy tools", 1)[0]
    bootstrap_preflight = bootstrap.split(
        "Exact read-only legacy-0015 preflight and external recovery verification", 1
    )[1].split("Reset only exact stale retry markers after guarded preflight", 1)[0]

    assert 'state_root=/var/lib/pork/deploy-state' in normal_preflight
    assert 'test ! -e "$active" && test ! -L "$active"' in normal_preflight
    assert 'test -f "$success" && test ! -L "$success"' in normal_preflight
    for canonical_receipt_token in (
        '"phase": "success"',
        '"schema_version": "production_fresh_install_global_v1"',
        '"stage": f"{release_root}/{release_sha}-fresh-install"',
        'raw != json.dumps(expected, separators=(",", ":"), sort_keys=True) + "\\n"',
    ):
        assert canonical_receipt_token in normal_preflight
    assert normal_preflight.index('state_root=/var/lib/pork/deploy-state') < normal_preflight.index(
        "mkdir -p .release/prior"
    )

    assert 'state_root=/var/lib/pork/deploy-state' in bootstrap_preflight
    assert 'test ! -e "$active" && test ! -L "$active"' in bootstrap_preflight
    assert 'test ! -e "$success" && test ! -L "$success"' in bootstrap_preflight
    assert bootstrap_preflight.index('state_root=/var/lib/pork/deploy-state') < bootstrap_preflight.index(
        'install -d -m 750 "$stage"'
    )

    for guarded_workflow in (normal_preflight, bootstrap_preflight):
        assert "systemctl list-units --all --type=service" in guarded_workflow
        assert "systemctl list-unit-files --type=service" in guarded_workflow
        assert "'pork-production-fresh-install-*.service'" in guarded_workflow
    assert "a production fresh-install recovery unit remains installed; STOP" in bootstrap_preflight
    for guarded_workflow in (normal_preflight,):
        assert "active|activating|deactivating|reloading|failed" in guarded_workflow
        assert "enabled|enabled-runtime|linked|linked-runtime|alias" in guarded_workflow
        assert 'systemctl show --property=ActiveState --value "$unit"' in guarded_workflow
        assert 'systemctl is-enabled "$unit"' in guarded_workflow


def test_preflight_runbook_scopes_external_protection_payload_to_normal_deploy() -> None:
    runbook = RECOVERY_RUNBOOK.read_text(encoding="utf-8")
    assert "For the normal post-install `deploy_prod.yml` path only" in runbook
    assert "The one-time fresh install does not" in runbook
    assert "protected-main workflow/SHA" in runbook


def test_seed_bundle_is_manual_fixed_three_release_non_production_artifact() -> None:
    text = SEED.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text and "push:" not in text
    for identity in (
        "cfbd37c02c99c569e47806337ed0306c9a722551",
        "e48fa51389f5365f9fe445b0c49a0a2224103502a6b742ca1cb9bd705f63a6d6",
        "867c0d21558dc8e73a0e55a42167b38ced6d6b67",
        "506b92be298a1e81d8550dad08c5ce4b5ece8fa3d163a78d286642ec75b4b060",
        "e7478a2fba9aaca17829c3d99e89e8d83d4b3188",
        "97a76daefbb73e1b78935916516fa093f3db5027e09ea44f52df6f63ac18222b",
    ):
        assert identity in text
    assert "ssh " not in text and "scp " not in text
    assert "seed-inventory.json" in text
    assert "seed-bundle-checksums.txt" in text
    assert "seed release asset graph mismatch" in text
    assert "seed release asset bytes mismatch" in text
