"""Fail-closed initial/DR seed tool for the immutable public-H2 asset store.

The normal release installer deliberately refuses an unseeded store.  This
module is the separately invoked bootstrap path: it accepts the three reviewed
release packages, validates all bytes before publishing a pointer, and never
deletes or replaces an existing store.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Iterable

from company_public_h2_release import (
    Manifest,
    ReleaseValidationError,
    _copy_immutable,
    _fsync_dir,
    _is_link,
    _replace_pointer,
    _require_approved_root,
    _validate_source_graph,
    manifest_set_bytes,
    parse_manifest_set,
    validate_store,
)

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_INVENTORY_LIMIT = 64 * 1024
_CHECKSUM_LIMIT = 1024 * 1024
_BUNDLE_FILE_LIMIT = 10_000
_BUNDLE_BYTE_LIMIT = 256 * 1024 * 1024
_SEED_PHASES = frozenset({"assets", "manifests", "before_pointer"})

# Oldest -> newest.  Replacing this reviewed set is a versioned decision, not
# an operator convenience flag.
APPROVED_RELEASES: tuple[tuple[str, str], ...] = (
    (
        "cfbd37c02c99c569e47806337ed0306c9a722551",
        "e48fa51389f5365f9fe445b0c49a0a2224103502a6b742ca1cb9bd705f63a6d6",
    ),
    (
        "867c0d21558dc8e73a0e55a42167b38ced6d6b67",
        "506b92be298a1e81d8550dad08c5ce4b5ece8fa3d163a78d286642ec75b4b060",
    ),
    (
        "e7478a2fba9aaca17829c3d99e89e8d83d4b3188",
        "97a76daefbb73e1b78935916516fa093f3db5027e09ea44f52df6f63ac18222b",
    ),
)


@dataclass(frozen=True)
class SeedRelease:
    commit: str
    manifest_sha256: str
    source: Path
    manifest: Manifest


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseValidationError("seed inventory has duplicate keys")
        result[key] = value
    return result


def _safe_relative_directory(value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ReleaseValidationError("seed source_dir is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseValidationError("seed source_dir is invalid")
    return Path(*path.parts)


def parse_inventory(
    inventory_path: Path,
    *,
    approved_releases: tuple[tuple[str, str], ...] = APPROVED_RELEASES,
) -> tuple[SeedRelease, SeedRelease, SeedRelease]:
    """Parse a canonical, bundle-relative inventory and validate all packages."""
    if _is_link(inventory_path) or not inventory_path.is_file():
        raise ReleaseValidationError("seed inventory missing or symlinked")
    raw = inventory_path.read_bytes()
    if (
        len(raw) > _INVENTORY_LIMIT
        or raw.startswith(b"\xef\xbb\xbf")
        or b"\r" in raw
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
    ):
        raise ReleaseValidationError("seed inventory bytes invalid")
    try:
        decoded = raw.decode("utf-8")
        data = json.loads(decoded, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseValidationError("seed inventory json invalid") from exc
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "releases"}
        or data.get("schema_version") != "company_public_h2_seed_inventory_v1"
        or not isinstance(data.get("releases"), list)
        or len(data["releases"]) != 3
    ):
        raise ReleaseValidationError("seed inventory schema invalid")
    canonical = (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if raw != canonical:
        raise ReleaseValidationError("seed inventory is not canonical json")

    base = inventory_path.parent.resolve(strict=True)
    releases: list[SeedRelease] = []
    observed: list[tuple[str, str]] = []
    for item in data["releases"]:
        if not isinstance(item, dict) or set(item) != {"commit", "manifest_sha256", "source_dir"}:
            raise ReleaseValidationError("seed release entry invalid")
        commit = item["commit"]
        digest = item["manifest_sha256"]
        if not isinstance(commit, str) or _COMMIT.fullmatch(commit) is None:
            raise ReleaseValidationError("seed release commit invalid")
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise ReleaseValidationError("seed release manifest digest invalid")
        relative = _safe_relative_directory(item["source_dir"])
        source = inventory_path.parent / relative
        try:
            resolved_source = source.resolve(strict=True)
            resolved_source.relative_to(base)
        except (OSError, ValueError) as exc:
            raise ReleaseValidationError("seed source escapes bundle root") from exc
        manifest, _assets = _validate_source_graph(
            resolved_source,
            resolved_source / "public_h2_asset_manifest.json",
        )
        if manifest.digest != digest:
            raise ReleaseValidationError("seed release manifest identity mismatch")
        observed.append((commit, digest))
        releases.append(SeedRelease(commit, digest, resolved_source, manifest))
    if tuple(observed) != approved_releases:
        raise ReleaseValidationError("seed release set/order is not approved")
    return releases[0], releases[1], releases[2]


def verify_bundle(
    inventory_path: Path,
    *,
    approved_releases: tuple[tuple[str, str], ...] = APPROVED_RELEASES,
) -> tuple[SeedRelease, SeedRelease, SeedRelease]:
    """Verify the closed checksum inventory and then the three source graphs."""
    checksum_path = inventory_path.parent / "seed-bundle-checksums.txt"
    if _is_link(checksum_path) or not checksum_path.is_file():
        raise ReleaseValidationError("seed bundle checksum inventory missing")
    raw = checksum_path.read_bytes()
    if (
        len(raw) > _CHECKSUM_LIMIT
        or raw.startswith(b"\xef\xbb\xbf")
        or b"\r" in raw
        or not raw.endswith(b"\n")
    ):
        raise ReleaseValidationError("seed bundle checksum inventory bytes invalid")
    expected: dict[str, str] = {}
    order: list[str] = []
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ReleaseValidationError("seed bundle checksum inventory is not ASCII") from exc
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise ReleaseValidationError("seed bundle checksum inventory malformed")
        relative = _safe_relative_directory(match.group(2)).as_posix()
        if relative == "seed-bundle-checksums.txt" or relative in expected:
            raise ReleaseValidationError("seed bundle checksum inventory malformed")
        expected[relative] = match.group(1)
        order.append(relative)
    if not expected or order != sorted(order) or len(expected) > _BUNDLE_FILE_LIMIT:
        raise ReleaseValidationError("seed bundle checksum inventory graph invalid")

    base = inventory_path.parent.resolve(strict=True)
    actual: dict[str, str] = {}
    total_bytes = 0
    for current_root, directory_names, file_names in os.walk(base, followlinks=False):
        current = Path(current_root)
        for name in directory_names:
            if _is_link(current / name):
                raise ReleaseValidationError("seed bundle contains a linked directory")
        for name in file_names:
            path = current / name
            if _is_link(path) or not path.is_file():
                raise ReleaseValidationError("seed bundle contains a non-file")
            relative = path.relative_to(base).as_posix()
            if relative == "seed-bundle-checksums.txt":
                continue
            size = path.stat().st_size
            total_bytes += size
            if total_bytes > _BUNDLE_BYTE_LIMIT:
                raise ReleaseValidationError("seed bundle expanded bytes exceed limit")
            digest = sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            actual[relative] = digest.hexdigest()
    if actual != expected:
        raise ReleaseValidationError("seed bundle checksum inventory mismatch")
    return parse_inventory(inventory_path, approved_releases=approved_releases)


def _require_empty_seed_root(root: Path, approved_root: Path) -> Path:
    if not root.is_absolute() or not approved_root.is_absolute():
        raise ReleaseValidationError("seed root must be an approved absolute path")
    if _is_link(root) or _is_link(approved_root):
        raise ReleaseValidationError("seed root must not be a symlink")
    try:
        resolved = root.resolve(strict=True)
        approved = approved_root.resolve(strict=True)
    except OSError as exc:
        raise ReleaseValidationError("seed root must already exist") from exc
    if resolved != approved or not resolved.is_dir():
        raise ReleaseValidationError("seed root is not approved")
    if any(resolved.iterdir()):
        raise ReleaseValidationError("seed root must be empty")
    if os.name != "nt":
        stat = resolved.stat()
        if stat.st_uid != os.geteuid() or stat.st_mode & 0o777 != 0o750:
            raise ReleaseValidationError("seed root ownership or permissions invalid")
    return resolved


def _fail(phase: str, configured: str | None) -> None:
    if configured == phase:
        raise ReleaseValidationError(f"injected seed {phase} failure")


def seed_store(
    root: Path,
    approved_root: Path,
    releases: Iterable[SeedRelease],
    *,
    fail_phase: str | None = None,
) -> tuple[str, str, str]:
    """Initialize one empty approved root; publish the pointer as the last write."""
    if fail_phase is not None and fail_phase not in _SEED_PHASES:
        raise ReleaseValidationError("unknown seed failure phase")
    stable_root = _require_empty_seed_root(root, approved_root)
    ordered = tuple(releases)
    if len(ordered) != 3 or len({release.manifest_sha256 for release in ordered}) != 3:
        raise ReleaseValidationError("seed requires exactly three distinct releases")

    assets_root = stable_root / "assets"
    manifests_root = stable_root / "manifests"
    identities_root = manifests_root / "sha256"
    assets_root.mkdir(mode=0o750)
    manifests_root.mkdir(mode=0o750)
    identities_root.mkdir(mode=0o750)

    for release in ordered:
        for asset in release.manifest.assets:
            name = asset.path.removeprefix("/assets/")
            _copy_immutable(release.source / "assets" / name, assets_root / name)
    _fsync_dir(assets_root)
    _fail("assets", fail_phase)

    for release in ordered:
        _copy_immutable(
            release.source / "public_h2_asset_manifest.json",
            identities_root / f"{release.manifest_sha256}.json",
        )
    _fsync_dir(identities_root)
    _fsync_dir(manifests_root)
    _fail("manifests", fail_phase)

    # Current is newest; the two predecessors remain in newest-to-oldest order.
    retained = tuple(release.manifest_sha256 for release in reversed(ordered))
    assert len(retained) == 3
    validate_store(stable_root, retained)
    _fail("before_pointer", fail_phase)
    _replace_pointer(stable_root / "manifest-set.json", manifest_set_bytes(retained))
    validate_store(stable_root, parse_manifest_set(stable_root / "manifest-set.json"))
    return retained  # type: ignore[return-value]


def verify_store(root: Path, approved_root: Path) -> tuple[str, str, str]:
    stable_root = _require_approved_root(root, approved_root)
    pointer = stable_root / "manifest-set.json"
    if _is_link(pointer) or not pointer.is_file():
        raise ReleaseValidationError("seed manifest set missing")
    retained = parse_manifest_set(pointer)
    validate_store(stable_root, retained)
    return retained


def select_manifest(root: Path, approved_root: Path, digest: str) -> Path:
    if _DIGEST.fullmatch(digest) is None:
        raise ReleaseValidationError("selected manifest digest invalid")
    retained = verify_store(root, approved_root)
    if digest not in retained:
        raise ReleaseValidationError("selected manifest is not retained")
    path = root.resolve(strict=True) / "manifests" / "sha256" / f"{digest}.json"
    if _is_link(path) or not path.is_file():
        raise ReleaseValidationError("selected manifest is unavailable")
    return path


def main(argv: list[str]) -> int:
    usage = (
        "usage: company_public_h2_seed.py seed ROOT APPROVED_ROOT INVENTORY | "
        "verify-bundle INVENTORY | verify ROOT APPROVED_ROOT | "
        "select ROOT APPROVED_ROOT MANIFEST_SHA256"
    )
    try:
        if len(argv) == 3 and argv[1] == "verify-bundle":
            releases = verify_bundle(Path(argv[2]))
            print(releases[-1].manifest_sha256)
            return 0
        if len(argv) == 5 and argv[1] == "seed":
            releases = verify_bundle(Path(argv[4]))
            retained = seed_store(Path(argv[2]), Path(argv[3]), releases)
            print(retained[0])
            return 0
        if len(argv) == 4 and argv[1] == "verify":
            retained = verify_store(Path(argv[2]), Path(argv[3]))
            print(retained[0])
            return 0
        if len(argv) == 5 and argv[1] == "select":
            selected = select_manifest(Path(argv[2]), Path(argv[3]), argv[4])
            print(selected)
            return 0
    except (OSError, ReleaseValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(usage, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
