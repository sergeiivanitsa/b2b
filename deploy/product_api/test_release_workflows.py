"""Static fail-closed contracts for iteration-25 CI and release surfaces."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / ".github/workflows/qa.yml"
DEPLOY = ROOT / ".github/workflows/deploy_prod.yml"
SEED = ROOT / ".github/workflows/company_public_h2_seed_bundle.yml"

POSTGRES_IMAGE = "postgres:16.9-alpine@sha256:b441677c946de564fe88ae4245ba80fe84a69485b22bf560e9c7c3710cd5e21d"
PLAYWRIGHT_IMAGE = "mcr.microsoft.com/playwright:v1.62.1-noble@sha256:c091b21d9fae78c76e85cd4356431e9b018402f172a214fc7d7a5e9a7e29d8ac"
PYTHON_BASE = "python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49"
BUILDX_VERSION = "v0.25.0"


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


def test_product_compose_keeps_local_sha_optional_and_deploy_supplies_exact_sha() -> None:
    compose = (ROOT / "docker-compose.product.yml").read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert "target: local" in compose
    assert "target: release" not in compose
    assert compose.count("- PRODUCT_RELEASE_COMMIT") == 3
    assert "PRODUCT_RELEASE_COMMIT:?" not in compose
    assert "PRODUCT_RELEASE_COMMIT='$RELEASE_SHA'" in deploy
    assert "--no-build --force-recreate product_api company_report_worker company_card_narrative_worker" in deploy


def test_product_example_keeps_privacy_key_unset_and_collection_closed() -> None:
    lines = (ROOT / "services/product_api/.env.example").read_text(encoding="utf-8").splitlines()
    assert "COMPANY_CARD_V2_ARBITRATION_COLLECTION_ENABLED=false" in lines
    active = [line for line in lines if line and not line.startswith("#")]
    assert not any(line.startswith("COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID=") for line in active)
    assert not any(line.startswith("COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON=") for line in active)


def test_deploy_is_manual_current_main_protected_qa_consumer_in_exact_order() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
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
    assert "provider_mode" in text and "disabled" in text
    assert "fallback-only" in text and "noindex-no-assignment" in text
    assert ". /opt/b2b/.env.product" not in text
    assert "prior-product-env" not in text
    assert "--settings-container" in text
    assert "worker-drain-result.json" in text
    assert "database_target_sha256" in text
    assert 'test \\"\\$candidate_db_sha\\" = \\"\\$drained_db_sha\\"' in text
    assert text.count("['images'][sys.argv[2]]['config_digest']") == 2
    assert text.count('test \\"\\$candidate_image\\" = \\"\\$expected_image\\"') == 2
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
    assert "s.company_card_v2_allowlist_inns == []" in text
    assert "s.company_card_v2_narrative_daily_limit == 0" in text
    assert "s.company_card_v2_arbitration_mask_keyring_json is None" in text
    assert "default-off verification failed" in text
    assert "assert " not in text
    assert text.count("python deploy/product_api/release_manifest.py") == 1


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
