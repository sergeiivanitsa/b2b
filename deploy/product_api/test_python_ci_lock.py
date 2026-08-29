"""Static and mutation tests for the checked-in Python CI lock family."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/check-python-ci-lock.py"
SPEC = importlib.util.spec_from_file_location("python_ci_lock", MODULE)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def _copy_contract(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".github/ci").mkdir(parents=True)
    (root / "services/product_api").mkdir(parents=True)
    (root / "services/gateway_api").mkdir(parents=True)
    for path in (ROOT / ".github/ci").glob("python-*.lock"):
        shutil.copy2(path, root / ".github/ci" / path.name)
    shutil.copy2(ROOT / "services/product_api/pyproject.toml", root / "services/product_api/pyproject.toml")
    shutil.copy2(ROOT / "services/gateway_api/pyproject.toml", root / "services/gateway_api/pyproject.toml")
    return root


def test_actual_lock_family_matches_pyprojects_and_cross_lock_identity() -> None:
    locks = checker.validate_repository(ROOT)
    assert set(locks) == {"bootstrap", "product", "gateway", "test"}
    assert set(locks["bootstrap"]) == {"pip", "setuptools", "wheel"}
    assert locks["product"]["uvloop"] == locks["gateway"]["uvloop"] == locks["test"]["uvloop"]
    assert "pytest" in locks["test"] and "pytest" not in locks["product"]


@pytest.mark.parametrize("mutation", ("unhashed", "unpinned", "marker", "duplicate", "unsorted", "header"))
def test_lock_parser_rejects_every_non_hermetic_shape(tmp_path: Path, mutation: str) -> None:
    root = _copy_contract(tmp_path)
    path = root / ".github/ci/python-product-runtime.lock"
    lines = path.read_text(encoding="ascii").splitlines()
    if mutation == "unhashed":
        lines[-1] = lines[-1].split(" --hash", 1)[0]
    elif mutation == "unpinned":
        lines[-1] = lines[-1].replace("==", ">=", 1)
    elif mutation == "marker":
        lines[-1] += "; python_version >= '3.12'"
    elif mutation == "duplicate":
        lines.append(lines[-1])
    elif mutation == "unsorted":
        lines[-1], lines[-2] = lines[-2], lines[-1]
    else:
        lines[1] = "# target-python: 3.12"
    path.write_bytes(("\n".join(lines) + "\n").encode("ascii"))
    with pytest.raises(checker.LockError):
        checker.validate_repository(root)


def test_cross_lock_version_hash_and_project_coverage_are_fail_closed(tmp_path: Path) -> None:
    root = _copy_contract(tmp_path)
    gateway = root / ".github/ci/python-gateway-runtime.lock"
    gateway.write_text(
        gateway.read_text(encoding="ascii").replace(
            "fastapi==0.141.1", "fastapi==0.141.0", 1
        ),
        encoding="ascii",
        newline="\n",
    )
    with pytest.raises(checker.LockError, match="differs|mismatch"):
        checker.validate_repository(root)

    root = _copy_contract(tmp_path / "missing")
    product = root / ".github/ci/python-product-runtime.lock"
    lines = [line for line in product.read_text(encoding="ascii").splitlines() if not line.startswith("asyncpg==")]
    product.write_bytes(("\n".join(lines) + "\n").encode("ascii"))
    with pytest.raises(checker.LockError, match="direct requirement asyncpg"):
        checker.validate_repository(root)

    root = _copy_contract(tmp_path / "bootstrap-leak")
    test_lock = root / ".github/ci/python-test.lock"
    bootstrap_row = (root / ".github/ci/python-bootstrap.lock").read_text(encoding="ascii").splitlines()[-3]
    lines = test_lock.read_text(encoding="ascii").splitlines()
    lines.append(bootstrap_row)
    lines[len(checker._HEADER):] = sorted(
        lines[len(checker._HEADER):],
        key=lambda line: checker.normalize_name(line.split("==", 1)[0]),
    )
    test_lock.write_bytes(("\n".join(lines) + "\n").encode("ascii"))
    with pytest.raises(checker.LockError, match="bootstrap distribution leaked"):
        checker.validate_repository(root)

    root = _copy_contract(tmp_path / "service-closure-leak")
    gateway = root / ".github/ci/python-gateway-runtime.lock"
    product = root / ".github/ci/python-product-runtime.lock"
    leaked = next(
        line for line in product.read_text(encoding="ascii").splitlines()
        if line.startswith("asyncpg==")
    )
    lines = gateway.read_text(encoding="ascii").splitlines()
    lines.append(leaked)
    lines[len(checker._HEADER):] = sorted(
        lines[len(checker._HEADER):],
        key=lambda line: checker.normalize_name(line.split("==", 1)[0]),
    )
    gateway.write_bytes(("\n".join(lines) + "\n").encode("ascii"))
    with pytest.raises(checker.LockError, match="audited dependency closure differs"):
        checker.validate_repository(root)


def test_composite_action_has_only_exact_hash_locked_install_contract() -> None:
    action = (ROOT / ".github/actions/setup-python-ci/action.yml").read_text(encoding="utf-8")
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in action
    assert "python-version: 3.12.11" in action
    assert action.count("--require-hashes") == 2
    assert action.count("--no-deps") == 3
    assert "--only-binary=:all:" in action
    assert "--no-build-isolation" in action
    assert "pip check" in action
    assert "--strict-environment" in action
    assert "pip install -U" not in action and "pip install --upgrade" not in action


@pytest.mark.parametrize("service", ("product", "gateway"))
def test_release_installed_manifest_accepts_only_service_lock_and_local_wheel(
    tmp_path: Path, service: str,
) -> None:
    locks = checker.validate_repository(ROOT)
    local_name = f"{service}-api"
    rows = sorted([
        *([name, row.version] for name, row in locks["bootstrap"].items()),
        *([name, row.version] for name, row in locks[service].items()),
        [local_name, "0.1.0"],
    ])
    manifest = tmp_path / "python-installed.json"
    manifest.write_text(json.dumps(rows, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    checker.validate_installed_manifest(manifest, service, locks)

    rows.append(["pytest", locks["test"]["pytest"].version])
    rows.sort()
    manifest.write_text(json.dumps(rows, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(checker.LockError, match="extra"):
        checker.validate_installed_manifest(manifest, service, locks)
