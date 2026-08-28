"""Closed-graph tests for the exact-SHA release manifest validator."""
from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "deploy/product_api/release_manifest.py"
SPEC = importlib.util.spec_from_file_location("release_manifest", MODULE)
assert SPEC and SPEC.loader
release = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release
SPEC.loader.exec_module(release)


def _write_graph(tmp_path: Path) -> tuple[Path, str, dict[str, object]]:
    root = (tmp_path / "release").resolve()
    root.mkdir()
    release_sha = "a" * 40
    names = release._required_artifact_names(release_sha)
    records = []
    for index, name in enumerate(names):
        data = f"artifact-{index}\n".encode()
        (root / name).write_bytes(data)
        records.append({"name": name, "sha256": sha256(data).hexdigest(), "size": len(data)})
    digest = "b" * 64
    manifest: dict[str, object] = {
        "schema_version": "company_card_v2_release_manifest_v1",
        "release_sha": release_sha,
        "artifacts": records,
        "build_inputs": {
            service: {
                "installed_manifest_sha256": digest,
                "local_wheel_sha256": digest,
                "wheelhouse_inventory_sha256": digest,
            }
            for service in ("product", "gateway")
        },
        "frontend": {
            "chromium_revision": 1234,
            "chromium_version": "151.0.7922.34",
            "font_inventory_sha256": release.FONT_INVENTORY,
            "node_version": "22.17.1",
            "npm_lock_sha256": sha256((ROOT / "services/web_ui/package-lock.json").read_bytes()).hexdigest(),
            "playwright_container_node_version": "24.18.1",
            "playwright_package_version": "1.62.1",
            "product_h2_manifest_sha256": sha256((
                ROOT / "services/product_api/src/product_api/company_reports/company_card_v2/public_h2_asset_manifest.json"
            ).read_bytes()).hexdigest(),
        },
        "images": {
            f"{service}-api-{release_sha}.oci.tar": {
                "oci_digest": f"sha256:{digest}",
                "config_digest": f"sha256:{digest}",
            }
            for service in ("product", "gateway")
        },
        "locks": {
            path.name: sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT / ".github/ci").glob("python-*.lock"))
        },
        "pins": {
            "buildkit_image": release.BUILDKIT_IMAGE,
            "playwright_image": release.PLAYWRIGHT_IMAGE,
            "playwright_image_index_digest": release.PLAYWRIGHT_INDEX,
            "postgres_image": release.POSTGRES_IMAGE,
            "python_base": release.PYTHON_BASE,
        },
    }
    _rewrite_manifest(root, release_sha, manifest)
    return root, release_sha, manifest


def _rewrite_manifest(root: Path, release_sha: str, manifest: dict[str, object]) -> None:
    manifest_path = root / f"release-manifest-{release_sha}.json"
    manifest_path.write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    checksum_rows = []
    for path in sorted(
        [*(root / item["name"] for item in manifest["artifacts"]), manifest_path],
        key=lambda value: value.name,
    ):
        checksum_rows.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    (root / f"checksums-{release_sha}.txt").write_text(
        "".join(checksum_rows), encoding="ascii", newline="\n"
    )


def test_exact_release_graph_and_self_checksum_are_accepted(tmp_path: Path) -> None:
    root, release_sha, _manifest = _write_graph(tmp_path)
    assert release.validate_release(root, release_sha) == sha256(
        (root / f"release-manifest-{release_sha}.json").read_bytes()
    ).hexdigest()


def test_artifact_cannot_be_replaced_with_a_matching_self_signed_checksum(tmp_path: Path) -> None:
    root, release_sha, manifest = _write_graph(tmp_path)
    artifact = root / manifest["artifacts"][0]["name"]
    artifact.write_bytes(b"tampered\n")
    manifest_path = root / f"release-manifest-{release_sha}.json"
    rows = []
    for path in sorted([*(root / item["name"] for item in manifest["artifacts"]), manifest_path], key=lambda value: value.name):
        rows.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    (root / f"checksums-{release_sha}.txt").write_text("".join(rows), encoding="ascii", newline="\n")
    with pytest.raises(release.ReleaseManifestError, match="differs from manifest"):
        release.validate_release(root, release_sha)


def test_pin_or_artifact_graph_change_is_rejected_even_when_rechecksummed(tmp_path: Path) -> None:
    root, release_sha, manifest = _write_graph(tmp_path)
    manifest["pins"]["playwright_image"] = "mcr.microsoft.com/playwright:floating"
    _rewrite_manifest(root, release_sha, manifest)
    with pytest.raises(release.ReleaseManifestError, match="pins"):
        release.validate_release(root, release_sha)


@pytest.mark.parametrize("entry_kind", ("file", "directory"))
def test_release_root_rejects_every_unmanifested_entry(tmp_path: Path, entry_kind: str) -> None:
    root, release_sha, _manifest = _write_graph(tmp_path)
    extra = root / "unmanifested-local-input"
    if entry_kind == "file":
        extra.write_bytes(b"not part of release\n")
    else:
        extra.mkdir()
    with pytest.raises(release.ReleaseManifestError, match="closed artifact graph|non-plain"):
        release.validate_release(root, release_sha)
