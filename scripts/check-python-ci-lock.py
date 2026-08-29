"""Validate iteration-25 Python hash locks and, optionally, the live CI env."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import sys
import tomllib

from packaging.requirements import Requirement
from packaging.version import Version

_ENTRY = re.compile(
    r"^(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)==(?P<version>[A-Za-z0-9][A-Za-z0-9.!+_-]*) "
    r"--hash=sha256:(?P<digest>[0-9a-f]{64})$"
)
_HEADER = (
    "# company-card-v2-python-lock-v1",
    "# target-python: 3.12.11",
    "# target-platform: linux_x86_64_manylinux2014",
    "# resolver: pip==25.1.1",
    "# resolver-wheel-sha256: 2913a38a2abf4ea6b64ab507bd9e967f3b53dc1ede74b01b0931e1ce548751af",
    "# generated: 2026-08-28",
    "# binary wheels only; install with --no-deps --only-binary=:all: --require-hashes",
    "",
)
_LOCK_NAMES = {
    "bootstrap": "python-bootstrap.lock",
    "product": "python-product-runtime.lock",
    "gateway": "python-gateway-runtime.lock",
    "test": "python-test.lock",
}
_BOOTSTRAP = {"pip", "setuptools", "wheel"}
_LOCAL = {"product-api": "0.1.0", "gateway-api": "0.1.0"}
_SHARED_RUNTIME = {
    "annotated-doc", "annotated-types", "anyio", "certifi", "click", "fastapi",
    "h11", "httpcore", "httptools", "httpx", "idna", "pydantic",
    "pydantic-core", "pydantic-settings", "python-dotenv", "pyyaml", "starlette",
    "typing-extensions", "typing-inspection", "uvicorn", "uvloop", "watchfiles",
    "websockets",
}
_PRODUCT_ONLY_RUNTIME = {
    "alembic", "asyncpg", "dnspython", "email-validator", "greenlet", "mako",
    "markupsafe", "python-multipart", "sqlalchemy",
}
_TEST_ONLY = {"pytest", "pytest-asyncio", "pluggy", "iniconfig", "pygments", "packaging"}


class LockError(RuntimeError):
    pass


def normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


@dataclass(frozen=True)
class LockedDistribution:
    name: str
    version: str
    digest: str


def parse_lock(path: Path) -> dict[str, LockedDistribution]:
    raw = path.read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n") or raw.startswith(b"\xef\xbb\xbf"):
        raise LockError(f"{path.name}: lock bytes invalid")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise LockError(f"{path.name}: lock is not ASCII") from exc
    if tuple(lines[: len(_HEADER)]) != _HEADER:
        raise LockError(f"{path.name}: lock header mismatch")
    rows: dict[str, LockedDistribution] = {}
    observed_order: list[str] = []
    for line in lines[len(_HEADER) :]:
        if not line:
            raise LockError(f"{path.name}: unexpected blank line")
        match = _ENTRY.fullmatch(line)
        if match is None:
            raise LockError(f"{path.name}: unpinned, unhashed or non-wheel entry")
        name = normalize_name(match.group("name"))
        if name in rows:
            raise LockError(f"{path.name}: duplicate distribution")
        try:
            Version(match.group("version"))
        except Exception as exc:
            raise LockError(f"{path.name}: invalid version") from exc
        rows[name] = LockedDistribution(name, match.group("version"), match.group("digest"))
        observed_order.append(name)
    if not rows or observed_order != sorted(observed_order):
        raise LockError(f"{path.name}: entries are empty or unsorted")
    return rows


def _requirements(pyproject: Path, *, include_test: bool) -> dict[str, Requirement]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        raise LockError(f"{pyproject}: missing project table")
    raw_requirements = list(project.get("dependencies", ()))
    if include_test:
        optional = project.get("optional-dependencies", {})
        if not isinstance(optional, dict):
            raise LockError(f"{pyproject}: invalid optional dependencies")
        raw_requirements.extend(optional.get("test", ()))
    result: dict[str, Requirement] = {}
    for raw in raw_requirements:
        requirement = Requirement(raw)
        name = normalize_name(requirement.name)
        prior = result.get(name)
        if prior is not None and str(prior.specifier) != str(requirement.specifier):
            raise LockError(f"{pyproject}: inconsistent duplicate requirement")
        result[name] = requirement
    return result


def _require_direct(lock: dict[str, LockedDistribution], requirements: dict[str, Requirement], label: str) -> None:
    for name, requirement in requirements.items():
        row = lock.get(name)
        if row is None:
            raise LockError(f"{label}: direct requirement {name} is missing")
        if not requirement.specifier.contains(row.version, prereleases=True):
            raise LockError(f"{label}: {name} does not satisfy pyproject")


def validate_repository(root: Path) -> dict[str, dict[str, LockedDistribution]]:
    lock_root = root / ".github/ci"
    locks = {label: parse_lock(lock_root / filename) for label, filename in _LOCK_NAMES.items()}
    if set(locks["bootstrap"]) != _BOOTSTRAP:
        raise LockError("bootstrap lock must contain exactly pip/setuptools/wheel")
    for label in ("product", "gateway", "test"):
        if _BOOTSTRAP & set(locks[label]):
            raise LockError(f"{label}: bootstrap distribution leaked into dependency lock")

    product_runtime = _requirements(root / "services/product_api/pyproject.toml", include_test=False)
    gateway_runtime = _requirements(root / "services/gateway_api/pyproject.toml", include_test=False)
    product_test = _requirements(root / "services/product_api/pyproject.toml", include_test=True)
    gateway_test = _requirements(root / "services/gateway_api/pyproject.toml", include_test=True)
    _require_direct(locks["product"], product_runtime, "product runtime lock")
    _require_direct(locks["gateway"], gateway_runtime, "gateway runtime lock")
    _require_direct(locks["test"], {**product_test, **gateway_test}, "test lock")

    expected_names = {
        "product": _SHARED_RUNTIME | _PRODUCT_ONLY_RUNTIME,
        "gateway": _SHARED_RUNTIME,
        "test": _SHARED_RUNTIME | _PRODUCT_ONLY_RUNTIME | _TEST_ONLY,
    }
    for label, names in expected_names.items():
        if set(locks[label]) != names:
            raise LockError(f"{label}: audited dependency closure differs")

    for label in ("product", "gateway"):
        for name, row in locks[label].items():
            tested = locks["test"].get(name)
            if tested != row:
                raise LockError(f"{label}: runtime distribution differs from tested lock: {name}")
    common = set(locks["product"]) & set(locks["gateway"])
    for name in common:
        if locks["product"][name] != locks["gateway"][name]:
            raise LockError(f"shared runtime distribution mismatch: {name}")
    return locks


def validate_environment(locks: dict[str, dict[str, LockedDistribution]]) -> None:
    if sys.version_info[:3] != (3, 12, 11):
        raise LockError("strict CI environment requires CPython 3.12.11")
    if platform.system() != "Linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise LockError("strict CI environment requires Linux x86_64")
    expected = {
        **{name: row.version for name, row in locks["bootstrap"].items()},
        **{name: row.version for name, row in locks["test"].items()},
        **_LOCAL,
    }
    observed: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = normalize_name(distribution.metadata["Name"])
        if name in observed and observed[name] != distribution.version:
            raise LockError(f"duplicate installed distribution: {name}")
        observed[name] = distribution.version
    if observed != expected:
        missing = sorted(set(expected) - set(observed))
        extra = sorted(set(observed) - set(expected))
        mismatched = sorted(name for name in set(expected) & set(observed) if expected[name] != observed[name])
        raise LockError(
            "strict CI environment mismatch: "
            f"missing={missing}, extra={extra}, version_mismatch={mismatched}"
        )


def validate_installed_manifest(
    path: Path,
    service: str,
    locks: dict[str, dict[str, LockedDistribution]],
) -> None:
    if service not in {"product", "gateway"}:
        raise LockError("installed manifest service must be product or gateway")
    raw = path.read_bytes()
    if (
        len(raw) > 256 * 1024
        or raw.startswith(b"\xef\xbb\xbf")
        or b"\r" in raw
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
    ):
        raise LockError("installed distribution manifest bytes invalid")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LockError("installed distribution manifest json invalid") from exc
    if not isinstance(value, list) or any(
        not isinstance(row, list)
        or len(row) != 2
        or not all(isinstance(item, str) for item in row)
        for row in value
    ):
        raise LockError("installed distribution manifest schema invalid")
    normalized = [(normalize_name(name), version) for name, version in value]
    if normalized != sorted(normalized) or len({name for name, _version in normalized}) != len(normalized):
        raise LockError("installed distribution manifest order invalid")
    canonical = (json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8")
    if canonical != raw:
        raise LockError("installed distribution manifest is not canonical json")
    local_name = f"{service}-api"
    expected = {
        **{name: row.version for name, row in locks["bootstrap"].items()},
        **{name: row.version for name, row in locks[service].items()},
        local_name: _LOCAL[local_name],
    }
    observed = dict(normalized)
    if observed != expected:
        missing = sorted(set(expected) - set(observed))
        extra = sorted(set(observed) - set(expected))
        mismatched = sorted(name for name in set(expected) & set(observed) if expected[name] != observed[name])
        raise LockError(
            "release installed manifest mismatch: "
            f"missing={missing}, extra={extra}, version_mismatch={mismatched}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict-environment", action="store_true")
    parser.add_argument("--service", choices=("product", "gateway"))
    parser.add_argument("--installed-manifest", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        locks = validate_repository(root)
        if args.strict_environment:
            validate_environment(locks)
        if (args.service is None) != (args.installed_manifest is None):
            raise LockError("--service and --installed-manifest must be provided together")
        if args.installed_manifest is not None:
            validate_installed_manifest(args.installed_manifest.resolve(strict=True), args.service, locks)
    except (OSError, LockError, tomllib.TOMLDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result = {label: len(rows) for label, rows in locks.items()}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")) if args.json else "python CI lock contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
