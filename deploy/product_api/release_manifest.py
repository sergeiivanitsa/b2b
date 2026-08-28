"""Validate the canonical exact-SHA iteration-25 release artifact graph."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import sys

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OCI_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_MANIFEST_BYTES = 1024 * 1024

POSTGRES_IMAGE = "postgres:16.9-alpine@sha256:b441677c946de564fe88ae4245ba80fe84a69485b22bf560e9c7c3710cd5e21d"
PLAYWRIGHT_IMAGE = "mcr.microsoft.com/playwright:v1.62.1-noble@sha256:c091b21d9fae78c76e85cd4356431e9b018402f172a214fc7d7a5e9a7e29d8ac"
PLAYWRIGHT_INDEX = "sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e"
PYTHON_BASE = "python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49"
BUILDKIT_IMAGE = "moby/buildkit:v0.23.2@sha256:e39f6119f134b4811af19fd5c20f495a6a264a85c1b6920daf569b23009dd42c"
FONT_INVENTORY = "705c330e71882ba9b680add251004054dcdc680b5c646e814b5b5ea2b6b341b3"


class ReleaseManifestError(RuntimeError):
    pass


def _plain_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ReleaseManifestError(f"release artifact is missing or not a plain file: {path.name}")
    return path.read_bytes()


def _canonical_json(path: Path) -> tuple[dict[str, object], bytes]:
    raw = _plain_file(path)
    if (
        len(raw) > _MAX_MANIFEST_BYTES
        or raw.startswith(b"\xef\xbb\xbf")
        or b"\r" in raw
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
    ):
        raise ReleaseManifestError("release manifest bytes are invalid")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseManifestError("release manifest JSON is invalid") from exc
    if not isinstance(value, dict):
        raise ReleaseManifestError("release manifest root is invalid")
    canonical = (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    if canonical != raw:
        raise ReleaseManifestError("release manifest is not canonical JSON")
    return value, raw


def _required_artifact_names(release_sha: str) -> tuple[str, ...]:
    return tuple(sorted((
        f"company-public-h2-{release_sha}.tgz",
        f"gateway-api-{release_sha}.oci.tar",
        f"product-api-{release_sha}.oci.tar",
        f"web-ui-{release_sha}.tgz",
        f"web-ui-playwright-runtime-{release_sha}.tgz",
    )))


def _validate_checksums(root: Path, release_sha: str, expected: dict[str, str]) -> None:
    path = root / f"checksums-{release_sha}.txt"
    raw = _plain_file(path)
    if b"\r" in raw or not raw.endswith(b"\n") or raw.startswith(b"\xef\xbb\xbf"):
        raise ReleaseManifestError("release checksum inventory bytes are invalid")
    observed: dict[str, str] = {}
    names: list[str] = []
    for line in raw.decode("ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if match is None or match.group(2) in observed:
            raise ReleaseManifestError("release checksum inventory is malformed")
        observed[match.group(2)] = match.group(1)
        names.append(match.group(2))
    if names != sorted(names) or observed != expected:
        raise ReleaseManifestError("release checksum inventory graph differs from manifest")
    for name, digest in observed.items():
        if sha256(_plain_file(root / name)).hexdigest() != digest:
            raise ReleaseManifestError(f"release checksum mismatch: {name}")


def validate_release(root: Path, release_sha: str) -> str:
    if _SHA40.fullmatch(release_sha) is None or not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ReleaseManifestError("release root/SHA is invalid")
    resolved = root.resolve(strict=True)
    repository_root = Path(__file__).resolve().parents[2]
    manifest_name = f"release-manifest-{release_sha}.json"
    manifest, raw = _canonical_json(resolved / manifest_name)
    if set(manifest) != {"schema_version", "release_sha", "artifacts", "build_inputs", "frontend", "images", "locks", "pins"}:
        raise ReleaseManifestError("release manifest keys are invalid")
    if manifest["schema_version"] != "company_card_v2_release_manifest_v1" or manifest["release_sha"] != release_sha:
        raise ReleaseManifestError("release manifest identity is invalid")

    expected_root_names = {
        *_required_artifact_names(release_sha),
        manifest_name,
        f"checksums-{release_sha}.txt",
    }
    actual_root_names: set[str] = set()
    for entry in resolved.iterdir():
        if entry.name in actual_root_names or entry.is_symlink() or not entry.is_file():
            raise ReleaseManifestError("release root contains a non-plain or duplicate entry")
        actual_root_names.add(entry.name)
    if actual_root_names != expected_root_names:
        raise ReleaseManifestError("release root is not the exact closed artifact graph")

    records = manifest["artifacts"]
    if not isinstance(records, list):
        raise ReleaseManifestError("release artifact records are invalid")
    expected_names = _required_artifact_names(release_sha)
    names: list[str] = []
    artifact_digests: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {"name", "sha256", "size"}:
            raise ReleaseManifestError("release artifact record is invalid")
        name, digest, size = record["name"], record["sha256"], record["size"]
        if (
            not isinstance(name, str)
            or name not in expected_names
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or type(size) is not int
            or size < 0
        ):
            raise ReleaseManifestError("release artifact identity is invalid")
        data = _plain_file(resolved / name)
        if len(data) != size or sha256(data).hexdigest() != digest:
            raise ReleaseManifestError(f"release artifact differs from manifest: {name}")
        names.append(name)
        artifact_digests[name] = digest
    if tuple(names) != expected_names or len(set(names)) != len(names):
        raise ReleaseManifestError("release artifact graph is not the exact closed set")

    pins = manifest["pins"]
    expected_pins = {
        "buildkit_image": BUILDKIT_IMAGE,
        "playwright_image": PLAYWRIGHT_IMAGE,
        "playwright_image_index_digest": PLAYWRIGHT_INDEX,
        "postgres_image": POSTGRES_IMAGE,
        "python_base": PYTHON_BASE,
    }
    if pins != expected_pins:
        raise ReleaseManifestError("release runtime pins are invalid")
    frontend = manifest["frontend"]
    if not isinstance(frontend, dict) or set(frontend) != {
        "chromium_revision", "chromium_version", "font_inventory_sha256", "node_version",
        "npm_lock_sha256", "playwright_container_node_version", "playwright_package_version",
        "product_h2_manifest_sha256",
    }:
        raise ReleaseManifestError("release frontend identity is invalid")
    if (
        frontend["chromium_revision"] != 1234
        or frontend["chromium_version"] != "151.0.7922.34"
        or frontend["font_inventory_sha256"] != FONT_INVENTORY
        or frontend["node_version"] != "22.17.1"
        or frontend["playwright_container_node_version"] != "24.18.1"
        or frontend["playwright_package_version"] != "1.62.1"
        or not isinstance(frontend["npm_lock_sha256"], str)
        or _SHA256.fullmatch(frontend["npm_lock_sha256"]) is None
        or not isinstance(frontend["product_h2_manifest_sha256"], str)
        or _SHA256.fullmatch(frontend["product_h2_manifest_sha256"]) is None
    ):
        raise ReleaseManifestError("release frontend values are invalid")

    locks = manifest["locks"]
    expected_locks = {
        path.name: sha256(_plain_file(path)).hexdigest()
        for path in sorted((repository_root / ".github/ci").glob("python-*.lock"))
    }
    if set(expected_locks) != {
        "python-bootstrap.lock", "python-gateway-runtime.lock", "python-product-runtime.lock", "python-test.lock"
    } or locks != expected_locks:
        raise ReleaseManifestError("release lock identities are invalid")
    if (
        frontend["npm_lock_sha256"]
        != sha256(_plain_file(repository_root / "services/web_ui/package-lock.json")).hexdigest()
        or frontend["product_h2_manifest_sha256"]
        != sha256(_plain_file(
            repository_root / "services/product_api/src/product_api/company_reports/company_card_v2/public_h2_asset_manifest.json"
        )).hexdigest()
        or _plain_file(repository_root / ".github/ci/playwright-font-inventory.sha256").decode("ascii").strip()
        != FONT_INVENTORY
    ):
        raise ReleaseManifestError("release checkout inputs differ from manifest")
    build_inputs = manifest["build_inputs"]
    if not isinstance(build_inputs, dict) or set(build_inputs) != {"product", "gateway"}:
        raise ReleaseManifestError("release build inputs are invalid")
    for value in build_inputs.values():
        if not isinstance(value, dict) or set(value) != {
            "installed_manifest_sha256", "local_wheel_sha256", "wheelhouse_inventory_sha256"
        } or any(not isinstance(item, str) or _SHA256.fullmatch(item) is None for item in value.values()):
            raise ReleaseManifestError("release build input identity is invalid")
    images = manifest["images"]
    expected_images = {f"product-api-{release_sha}.oci.tar", f"gateway-api-{release_sha}.oci.tar"}
    if not isinstance(images, dict) or set(images) != expected_images:
        raise ReleaseManifestError("release OCI identities are invalid")
    for value in images.values():
        if not isinstance(value, dict) or set(value) != {"oci_digest", "config_digest"} or any(
            not isinstance(item, str) or _OCI_DIGEST.fullmatch(item) is None for item in value.values()
        ):
            raise ReleaseManifestError("release OCI identity is invalid")

    manifest_digest = sha256(raw).hexdigest()
    checksum_expected = {**artifact_digests, manifest_name: manifest_digest}
    _validate_checksums(resolved, release_sha, checksum_expected)
    return manifest_digest


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: release_manifest.py ABSOLUTE_RELEASE_ROOT RELEASE_SHA", file=sys.stderr)
        return 2
    try:
        digest = validate_release(Path(argv[1]), argv[2])
    except (OSError, UnicodeDecodeError, ReleaseManifestError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
