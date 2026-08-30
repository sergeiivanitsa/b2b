from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
from types import ModuleType

import pytest

from tests_support.junit_guard import JUnitEvidenceError, validate_junit_evidence
from tests_support.archive_guard import (
    ReviewedArchiveError,
    _validate_members,
    extract_reviewed_archive,
)


def _load_acceptance_seeder() -> ModuleType:
    script = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "seed-iteration25-company-card-v2-acceptance.py"
    )
    spec = importlib.util.spec_from_file_location("iteration25_acceptance_seed", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, body: str, *, mtime_ns: int | None = None) -> None:
    path.write_text(body, encoding="utf-8")
    if mtime_ns is not None:
        os.utime(path, ns=(mtime_ns, mtime_ns))


def test_clean_nonzero_junit_is_accepted(tmp_path: Path) -> None:
    started = time.time_ns()
    path = tmp_path / "clean.xml"
    _write(
        path,
        "<testsuites><testsuite><testcase name='one'/><testcase name='two'/>"
        "</testsuite></testsuites>",
    )

    summary = validate_junit_evidence(path, phase="clean", not_before_ns=started)

    assert (summary.tests, summary.failures, summary.errors, summary.skipped) == (
        2,
        0,
        0,
        0,
    )
    assert summary.path == path.resolve()


@pytest.mark.parametrize(
    ("name", "body", "message"),
    (
        ("zero", "<testsuite tests='0'/>", "zero tests"),
        (
            "skipped",
            "<testsuite><testcase><skipped/></testcase></testsuite>",
            "skipped=1",
        ),
        (
            "failed",
            "<testsuite><testcase><failure/></testcase></testsuite>",
            "failures=1",
        ),
        (
            "errored",
            "<testsuite><testcase><error/></testcase></testsuite>",
            "errors=1",
        ),
        ("malformed", "<testsuite><testcase>", "malformed"),
    ),
)
def test_unclean_or_malformed_junit_is_rejected(
    tmp_path: Path,
    name: str,
    body: str,
    message: str,
) -> None:
    path = tmp_path / f"{name}.xml"
    _write(path, body)
    with pytest.raises(JUnitEvidenceError, match=message):
        validate_junit_evidence(path, phase=name, not_before_ns=0)


def test_missing_and_stale_junit_are_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "missing.xml"
    with pytest.raises(JUnitEvidenceError, match="missing"):
        validate_junit_evidence(missing, phase="missing", not_before_ns=0)

    stale = tmp_path / "stale.xml"
    _write(stale, "<testsuite><testcase/></testsuite>", mtime_ns=1_000_000_000)
    with pytest.raises(JUnitEvidenceError, match="stale"):
        validate_junit_evidence(stale, phase="stale", not_before_ns=2_000_000_000)


def test_checker_cli_prints_only_validated_summary(tmp_path: Path) -> None:
    started = time.time_ns()
    path = tmp_path / "phase.xml"
    _write(path, "<testsuite><testcase name='one'/></testsuite>")
    script = Path(__file__).resolve().parents[3] / "scripts" / "check-iteration25-test-results.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--phase",
            "exact-0018",
            "--junit",
            str(path),
            "--not-before-ns",
            str(started),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert json.loads(completed.stdout) == {
        "errors": 0,
        "failures": 0,
        "phase": "exact-0018",
        "skipped": 0,
        "tests": 1,
    }


def test_iteration25_runner_owns_forward_head_and_two_junit_phases() -> None:
    root = Path(__file__).resolve().parents[3]
    runner = (root / "scripts" / "run-iteration25-postgres-tests.ps1").read_text(
        encoding="utf-8"
    )
    historical_runner = root / "scripts" / "run-iteration24-postgres-tests.ps1"
    migration_test = (
        root
        / "services"
        / "product_api"
        / "tests"
        / "test_company_report_iteration24_migration.py"
    ).read_text(encoding="utf-8")

    assert "com.b2b.iteration25.disposable" in runner
    assert (
        "postgres:16.9-alpine@sha256:"
        "b441677c946de564fe88ae4245ba80fe84a69485b22bf560e9c7c3710cd5e21d"
        in runner
    )
    assert '"--platform", "linux/amd64"' in runner
    assert "i24_guard_$short" in runner
    assert "i24_roundtrip_$short" in runner
    assert "i24u$short" in runner
    assert "i25_suite_$short" in runner
    assert '"0020_company_card_narrative_quota_mode"' in runner
    checks = tuple(
        line.strip()
        for line in runner.splitlines()
        if line.lstrip().startswith("Invoke-JUnitCheck ")
    )
    assert checks == (
        'Invoke-JUnitCheck "exact-0018" $junit0018 $phase0018Started',
        'Invoke-JUnitCheck "affected-head" $junitAffected $phaseAffectedStarted',
        'Invoke-JUnitCheck "browser-e2e" $junitBrowser $phaseBrowserStarted',
    )
    assert "--ignore=services/product_api/tests/test_company_report_iteration24_migration.py" in runner
    assert historical_runner.name not in runner
    assert '[ValidateSet("PostgresFull", "BrowserE2E")]' in runner
    assert '[string]$Mode = "PostgresFull"' in runner
    assert all(
        name in runner
        for name in (
            "ReleaseArtifactRoot",
            "PlaywrightImage",
            "FontInventory",
            "ReleaseSha",
            "UpdateSnapshots",
        )
    )
    assert "DATABASE_URL" in runner
    assert "COMPANY_CARD_V2_E2E_BASE_URL" in runner
    assert "COMPANY_CARD_V2_E2E_MANIFEST" in runner
    assert "SEO_PUBLIC_BASE_URL" in runner
    assert "tests_support.network_guard:guarded_product_app" in runner
    assert "e2e/companyCardV2/loopback-stack.mjs" in runner
    assert "e2e/companyCardV2/loopback-proxy.mjs" not in runner
    assert (
        "mcr.microsoft.com/playwright:v1.62.1-noble@sha256:"
        "c091b21d9fae78c76e85cd4356431e9b018402f172a214fc7d7a5e9a7e29d8ac"
        in runner
    )
    assert '"host.docker.internal:host-gateway"' in runner
    assert '"--network", "container:$stackContainerId"' in runner
    assert '"--product-target-host", $productTargetHost' in runner
    assert '"--product-relay-port", "$productRelayPort"' in runner
    assert '$stackNodeVersion -ne "v24.18.1"' in runner
    assert "Wait-ContainerLoopbackReady" in runner
    assert 'release-manifest-$ReleaseSha.json' in runner
    assert 'deploy\\product_api\\release_manifest.py' in runner
    assert "BrowserE2E canonical release manifest validation" in runner
    assert "exact_0018_junit_sha256=$exact0018Digest" in runner
    assert "affected_head_junit_sha256=$affectedHeadDigest" in runner
    assert "junit_sha256=$browserDigest" in runner
    assert "web-ui-playwright-runtime-$ReleaseSha.tgz" in runner
    assert '"test:e2e:update-snapshots"' in runner
    assert '"test:e2e:ci"' in runner
    assert "& npm run test:e2e" not in runner
    assert (
        '$browserRuntimeMountPoint = [IO.Path]::GetFullPath((Join-Path $webRoot "node_modules"))'
        in runner
    )
    assert "$ownsBrowserRuntimeMountPoint = $false" in runner
    assert (
        "if (-not (Test-Path -LiteralPath $browserRuntimeMountPoint))" in runner
    )
    assert "$ownsBrowserRuntimeMountPoint = $true" in runner
    assert (
        "BrowserE2E runtime mountpoint must be the exact plain node_modules directory"
        in runner
    )
    assert (
        "BrowserE2E runner-owned runtime mountpoint must remain empty" in runner
    )
    assert (
        "BrowserE2E runtime mountpoint failed its exact empty ownership check"
        in runner
    )
    assert runner.count("$browserRuntimeMountPointItem.LinkType") == 2
    assert runner.count(
        "@(" + "Get-ChildItem -LiteralPath $browserRuntimeMountPoint -Force" + ").Count -ne 0"
    ) == 2
    assert '"--volume", "${repoRoot}:/workspace:ro"' in runner
    assert (
        '"--volume", "${resolvedRuntimeRoot}:/workspace/services/web_ui/node_modules:ro"'
        in runner
    )
    assert (
        '"--volume", "${browserOutput}:/workspace/services/web_ui/.tmp/iteration25-playwright:rw"'
        in runner
    )
    finally_start = runner.index("finally {")
    container_cleanup = runner.index("foreach ($ownedContainer in @(", finally_start)
    mountpoint_cleanup = runner.index(
        "if ($ownsBrowserRuntimeMountPoint)", container_cleanup
    )
    assert container_cleanup < mountpoint_cleanup
    assert "npm ci" not in runner
    assert "npm install" not in runner
    assert 'command.upgrade(config, "head")' not in migration_test
    assert migration_test.count("command.upgrade(config, REVISION)") == 3


def test_iteration25_postgres_bootstrap_waits_for_final_tcp_server() -> None:
    root = Path(__file__).resolve().parents[3]
    runner = (root / "scripts" / "run-iteration25-postgres-tests.ps1").read_text(
        encoding="utf-8"
    )
    start_marker = "    $ready = $false"
    end_marker = '    $guardUrl = "postgresql+asyncpg://'
    assert runner.count(start_marker) == 1
    assert runner.count(end_marker) == 1
    bootstrap_start = runner.index(start_marker)
    bootstrap_end = runner.index(end_marker, bootstrap_start)
    bootstrap = runner[bootstrap_start:bootstrap_end]

    tcp_readiness = (
        "& docker exec $containerId pg_isready --host 127.0.0.1 --port 5432 "
        "--username $pgUser --dbname postgres *> $null"
    )
    socket_only_readiness = (
        "& docker exec $containerId pg_isready --username $pgUser "
        "--dbname postgres *> $null"
    )
    createdb = (
        "& docker exec $containerId createdb --username $pgUser "
        "--owner $pgUser $database"
    )
    readiness_lines = tuple(
        line.strip() for line in bootstrap.splitlines() if "pg_isready" in line
    )
    createdb_lines = tuple(
        line.strip() for line in bootstrap.splitlines() if " createdb " in line
    )

    assert readiness_lines == (tcp_readiness,)
    assert socket_only_readiness not in bootstrap
    assert createdb_lines == (createdb,)
    assert "$isWindowsHost" not in bootstrap

    sentinels = (
        tcp_readiness,
        "if ($LASTEXITCODE -eq 0)",
        "$ready = $true",
        "break",
        "if (-not $ready)",
        "foreach ($database in @($guardDatabase, $roundtripDatabase, $suiteDatabase))",
        createdb,
    )
    positions = [bootstrap.index(sentinel) for sentinel in sentinels]
    assert positions == sorted(positions)


def test_acceptance_registry_builds_exact_browser_manifest() -> None:
    seeder = _load_acceptance_seeder()
    profiles = seeder.load_profile_registry()

    manifest = seeder.build_e2e_manifest(profiles, release_sha="a" * 40)

    assert tuple(profile["profile_id"] for profile in profiles) == seeder.PROFILE_IDS
    assert set(manifest) == {"schema_version", "release_sha", "routes", "profiles"}
    assert manifest["schema_version"] == "company_card_v2_e2e_manifest_v1"
    assert manifest["routes"] == {
        "robots_path": "/robots.txt",
        "sitemap_index_path": "/sitemaps/index.xml",
    }
    expected_profile_keys = {
        "profile_id",
        "canonical_path",
        "wrong_slug_path",
        "expected_report_id",
        "expected_indexable",
        "expected_lazy_hosts",
        "expected_visible_text",
        "forbidden_visible_text",
        "lazy_failure_chunk",
    }
    assert all(set(profile) == expected_profile_keys for profile in manifest["profiles"])
    assert len({profile["canonical_path"] for profile in manifest["profiles"]}) == 5
    assert len({profile["expected_report_id"] for profile in manifest["profiles"]}) == 5
    expected_hosts = {
        profile_id: list(seeder.LAZY_HOSTS) for profile_id in seeder.PROFILE_IDS
    }
    expected_hosts["sparse_missing_fallback_v1"] = list(seeder.LAZY_HOSTS[4:])
    assert {
        profile["profile_id"]: profile["expected_lazy_hosts"]
        for profile in manifest["profiles"]
    } == expected_hosts


@pytest.mark.parametrize(
    "url",
    (
        "postgresql+asyncpg://i24u0123456789ab:i25p0123456789ab00000000000000000000@example.com:5432/i25_suite_0123456789ab",
        "postgresql+asyncpg://wrong:i25p0123456789ab00000000000000000000@127.0.0.1:5432/i25_suite_0123456789ab",
        "postgresql+asyncpg://i24u0123456789ab:wrong@127.0.0.1:5432/i25_suite_0123456789ab",
        "postgresql+asyncpg://i24u0123456789ab:i25p0123456789ab00000000000000000000@127.0.0.1:5432/production",
        "postgresql+asyncpg://i24u0123456789ab:i25pffffffffffff00000000000000000000@127.0.0.1:5432/i25_suite_0123456789ab",
    ),
)
def test_acceptance_seeder_rejects_non_runner_database(url: str) -> None:
    seeder = _load_acceptance_seeder()
    with pytest.raises(seeder.SeederContractError, match="runner-owned"):
        seeder.validate_runner_database(url, "i25_suite_0123456789ab")


def test_acceptance_seeder_accepts_exact_runner_database() -> None:
    seeder = _load_acceptance_seeder()
    url = (
        "postgresql+asyncpg://i24u0123456789ab:"
        "i25p0123456789ab00000000000000000000@127.0.0.1:5432/"
        "i25_suite_0123456789ab"
    )
    target = seeder.validate_runner_database(url, "i25_suite_0123456789ab")
    assert target.host == "127.0.0.1"
    assert target.port == 5432
    assert target.database == "i25_suite_0123456789ab"


def test_acceptance_profile_facts_cover_closed_edge_matrix() -> None:
    from product_api.company_reports.company_card_v2.finance import build_finance_views

    seeder = _load_acceptance_seeder()
    profiles = {
        profile["profile_id"]: seeder._snapshot(profile)
        for profile in seeder.load_profile_registry()
    }

    complete = profiles["sks_morphology_complete_v1"]
    assert all(
        view is not None
        for view in build_finance_views(complete.finance_basis, anchor_year=2025).values()
    )

    sparse = profiles["sparse_missing_fallback_v1"]
    assert sparse.finance_basis.cells == ()
    assert all(
        view is None
        for view in build_finance_views(sparse.finance_basis, anchor_year=2025).values()
    )
    assert "expected_rollout_generation=h2.rollout_generation" in Path(
        seeder.__file__
    ).read_text(encoding="utf-8")

    partial = profiles["partial_long_limitations_v1"]
    assert len(partial.counterparty.address or "") > 900
    assert any(cell.state == "missing" for cell in partial.finance_basis.cells)

    large = profiles["large_n_signed_masked_v1"]
    states = {cell.state for cell in large.finance_basis.cells}
    assert {"available_nonzero", "missing", "zero_unverified"} <= states
    assert any(
        cell.value is not None and cell.value < 0 for cell in large.finance_basis.cells
    )
    assert large.arbitration_basis.source_total == 25
    assert len(large.arbitration_basis.sanitized_cases) == 25
    assert all(
        case.opponent_tokens
        and all(token.key_id == "active_2026" for token in case.opponent_tokens)
        for case in large.arbitration_basis.sanitized_cases
    )

    lazy = profiles["lazy_failure_v1"]
    assert lazy.finance_basis == complete.finance_basis
    assert lazy.arbitration_basis == complete.arbitration_basis


def test_acceptance_manifest_write_is_new_only(tmp_path: Path) -> None:
    seeder = _load_acceptance_seeder()
    destination = tmp_path / "manifest.json"
    manifest = seeder.build_e2e_manifest(
        seeder.load_profile_registry(), release_sha="b" * 40
    )

    seeder._write_manifest(destination, manifest)
    original = destination.read_bytes()

    with pytest.raises(seeder.SeederContractError, match="already exists"):
        seeder._write_manifest(destination, manifest)
    assert destination.read_bytes() == original


def test_iteration25_baseline_is_exact_and_contains_no_waiver() -> None:
    baseline_path = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "development"
        / "evidence"
        / "iteration-25-company-card-v2"
        / "iteration-25-test-baseline-v1.json"
    )
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    assert baseline["base_commit"] == "31b299ac88b5fac7d5c04082324fb122d63db7e7"
    assert baseline["failure_allowlist"] == []
    assert baseline["skip_allowlist"] == []
    assert all(
        result["failures"] == result["errors"] == result["skipped"] == 0
        and result["tests"] > 0
        for result in baseline["gates"].values()
    )


def test_reviewed_h2_archive_extracts_only_closed_graph(tmp_path: Path) -> None:
    archive = (tmp_path / "h2.tgz").resolve()
    destination = (tmp_path / "extracted").resolve()
    with tarfile.open(archive, "w:gz") as output:
        for name, body in (
            (
                "company-public-h2/public_h2_asset_manifest.json",
                b'{"schema_version":"company_public_h2_asset_manifest_v1"}\n',
            ),
            ("company-public-h2/assets/company-public-h2.abcdefgh.js", b"ok"),
        ):
            member = tarfile.TarInfo(name)
            member.size = len(body)
            output.addfile(member, io.BytesIO(body))

    root = extract_reviewed_archive(archive, destination, kind="h2-release")

    assert root == destination / "company-public-h2"
    assert (root / "assets" / "company-public-h2.abcdefgh.js").read_bytes() == b"ok"


def test_reviewed_archive_rejects_traversal_and_escaping_symlink(
    tmp_path: Path,
) -> None:
    archive = (tmp_path / "escape.tgz").resolve()
    destination = (tmp_path / "escape").resolve()
    with tarfile.open(archive, "w:gz") as output:
        body = b"escape"
        member = tarfile.TarInfo("company-public-h2/../outside")
        member.size = len(body)
        output.addfile(member, io.BytesIO(body))
    with pytest.raises(ReviewedArchiveError, match="escapes"):
        extract_reviewed_archive(archive, destination, kind="h2-release")

    root = tarfile.TarInfo("node_modules")
    root.type = tarfile.DIRTYPE
    link = tarfile.TarInfo("node_modules/.bin/playwright")
    link.type = tarfile.SYMTYPE
    link.linkname = "../../../outside"
    with pytest.raises(ReviewedArchiveError, match="escapes"):
        _validate_members([root, link], kind="playwright-runtime")


def test_reviewed_runtime_allows_only_internal_relative_symlink() -> None:
    root = tarfile.TarInfo("node_modules")
    root.type = tarfile.DIRTYPE
    package = tarfile.TarInfo("node_modules/@playwright/test/cli.js")
    package.size = 1
    link = tarfile.TarInfo("node_modules/.bin/playwright")
    link.type = tarfile.SYMTYPE
    link.linkname = "../@playwright/test/cli.js"

    _validate_members([root, package, link], kind="playwright-runtime")
