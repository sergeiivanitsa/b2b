"""Disposable-store tests for the separately authorized H2 seed path."""
from __future__ import annotations

import importlib.util
import json
import os
from hashlib import sha256
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "deploy/nginx/company_public_h2_seed.py"
sys.path.insert(0, str(MODULE.parent))
SPEC = importlib.util.spec_from_file_location("h2seed", MODULE)
assert SPEC and SPEC.loader
seed = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = seed
SPEC.loader.exec_module(seed)


def _release(bundle: Path, ordinal: int, *, basename_seed: str | None = None) -> tuple[Path, str, str]:
    commit = f"{ordinal:040x}"
    release_root = bundle / "releases" / commit
    assets_root = release_root / "assets"
    assets_root.mkdir(parents=True)
    marker = basename_seed or f"r{ordinal}"
    bodies = {
        f"company-public-h2.{marker}abcdefgh.css": f"css-{ordinal}".encode(),
        f"company-public-h2.{marker}abcdefgh.js": f"js-{ordinal}".encode(),
    }
    for name, body in bodies.items():
        (assets_root / name).write_bytes(body)
    paths = sorted(f"/assets/{name}" for name in bodies)
    manifest = {
        "schema_version": "company_public_h2_asset_manifest_v1",
        "public_contract_version": "company_public_h2_v1",
        "canonical_json_profile": "company_public_h2_cjson_v1",
        "entry_js_path": next(path for path in paths if path.endswith(".js")),
        "entry_css_path": next(path for path in paths if path.endswith(".css")),
        "optional_chunk_paths": [],
        "assets": [
            {
                "path": path,
                "sha256_hex": sha256(bodies[path.removeprefix("/assets/")]).hexdigest(),
                "media_type": "text/javascript" if path.endswith(".js") else "text/css",
            }
            for path in paths
        ],
    }
    raw = (json.dumps(manifest, separators=(",", ":")) + "\n").encode()
    (release_root / "public_h2_asset_manifest.json").write_bytes(raw)
    return release_root, commit, sha256(raw).hexdigest()


def _bundle(tmp_path: Path, *, shared_basename: bool = False):
    bundle = tmp_path / "bundle"
    releases = [
        _release(bundle, ordinal, basename_seed="same" if shared_basename else None)
        for ordinal in (1, 2, 3)
    ]
    entries = [
        {
            "commit": commit,
            "manifest_sha256": digest,
            "source_dir": source.relative_to(bundle).as_posix(),
        }
        for source, commit, digest in releases
    ]
    inventory = bundle / "seed-inventory.json"
    inventory.write_bytes((json.dumps({
        "schema_version": "company_public_h2_seed_inventory_v1",
        "releases": entries,
    }, separators=(",", ":")) + "\n").encode())
    checksum_rows = []
    for path in sorted(
        (path for path in bundle.rglob("*") if path.is_file()),
        key=lambda value: value.relative_to(bundle).as_posix(),
    ):
        checksum_rows.append(
            f"{sha256(path.read_bytes()).hexdigest()}  {path.relative_to(bundle).as_posix()}\n"
        )
    (bundle / "seed-bundle-checksums.txt").write_text(
        "".join(checksum_rows), encoding="ascii", newline="\n"
    )
    approved = tuple((commit, digest) for _source, commit, digest in releases)
    parsed = seed.parse_inventory(inventory, approved_releases=approved)
    return inventory, approved, parsed


def _empty_root(tmp_path: Path, name: str = "store") -> Path:
    root = tmp_path / name
    root.mkdir(mode=0o750)
    if os.name != "nt":
        root.chmod(0o750)
    return root.resolve()


def test_seed_verify_select_and_dr_restore_are_exact(tmp_path: Path) -> None:
    inventory, approved, releases = _bundle(tmp_path)
    assert seed.verify_bundle(inventory, approved_releases=approved) == releases
    store = _empty_root(tmp_path)
    retained = seed.seed_store(store, store, releases)
    assert retained == tuple(digest for _commit, digest in reversed(approved))
    assert seed.verify_store(store, store) == retained
    for digest in retained:
        assert seed.select_manifest(store, store, digest).name == f"{digest}.json"

    # Verify is idempotent; an accidental second seed is not.
    assert seed.verify_store(store, store) == retained
    with pytest.raises(seed.ReleaseValidationError, match="empty"):
        seed.seed_store(store, store, releases)

    dr = _empty_root(tmp_path, "dr-store")
    assert seed.seed_store(dr, dr, releases) == retained
    assert (dr / "manifest-set.json").read_bytes() == (store / "manifest-set.json").read_bytes()


def test_bundle_checksum_inventory_rejects_extra_or_changed_bytes(tmp_path: Path) -> None:
    inventory, approved, _releases = _bundle(tmp_path)
    extra = inventory.parent / "unexpected.txt"
    extra.write_text("unexpected", encoding="utf-8")
    with pytest.raises(seed.ReleaseValidationError, match="checksum inventory mismatch"):
        seed.verify_bundle(inventory, approved_releases=approved)
    extra.unlink()
    asset = next((inventory.parent / "releases").rglob("*.js"))
    asset.write_bytes(b"changed")
    with pytest.raises(seed.ReleaseValidationError, match="checksum inventory mismatch"):
        seed.verify_bundle(inventory, approved_releases=approved)


@pytest.mark.parametrize("phase", sorted(seed._SEED_PHASES))
def test_interruption_before_pointer_never_exposes_partial_store(tmp_path: Path, phase: str) -> None:
    _inventory, _approved, releases = _bundle(tmp_path)
    store = _empty_root(tmp_path)
    with pytest.raises(seed.ReleaseValidationError, match=f"injected seed {phase}"):
        seed.seed_store(store, store, releases, fail_phase=phase)
    assert not (store / "manifest-set.json").exists()
    with pytest.raises(seed.ReleaseValidationError, match="manifest set"):
        seed.verify_store(store, store)


def test_inventory_rejects_order_digest_escape_duplicates_and_noncanonical_json(tmp_path: Path) -> None:
    inventory, approved, _releases = _bundle(tmp_path)
    data = json.loads(inventory.read_text(encoding="utf-8"))

    data["releases"].reverse()
    inventory.write_bytes((json.dumps(data, separators=(",", ":")) + "\n").encode())
    with pytest.raises(seed.ReleaseValidationError, match="set/order"):
        seed.parse_inventory(inventory, approved_releases=approved)

    data["releases"].reverse()
    data["releases"][0]["manifest_sha256"] = "f" * 64
    inventory.write_bytes((json.dumps(data, separators=(",", ":")) + "\n").encode())
    with pytest.raises(seed.ReleaseValidationError, match="identity"):
        seed.parse_inventory(inventory, approved_releases=approved)

    data["releases"][0]["manifest_sha256"] = approved[0][1]
    data["releases"][0]["source_dir"] = "../escape"
    inventory.write_bytes((json.dumps(data, separators=(",", ":")) + "\n").encode())
    with pytest.raises(seed.ReleaseValidationError, match="source_dir"):
        seed.parse_inventory(inventory, approved_releases=approved)

    inventory.write_bytes(b'{"schema_version":"company_public_h2_seed_inventory_v1","schema_version":"duplicate","releases":[]}\n')
    with pytest.raises(seed.ReleaseValidationError, match="duplicate"):
        seed.parse_inventory(inventory, approved_releases=approved)


def test_seed_rejects_unapproved_nonempty_symlink_and_content_collision(tmp_path: Path) -> None:
    _inventory, _approved, releases = _bundle(tmp_path, shared_basename=True)
    unapproved = _empty_root(tmp_path, "unapproved")
    approved = _empty_root(tmp_path, "approved")
    with pytest.raises(seed.ReleaseValidationError, match="not approved"):
        seed.seed_store(unapproved, approved, releases)

    (approved / "unexpected").write_text("x", encoding="utf-8")
    with pytest.raises(seed.ReleaseValidationError, match="empty"):
        seed.seed_store(approved, approved, releases)

    collision = _empty_root(tmp_path, "collision")
    with pytest.raises(seed.ReleaseValidationError, match="collision"):
        seed.seed_store(collision, collision, releases)
    assert not (collision / "manifest-set.json").exists()


def test_select_rejects_unretained_digest_and_wrapper_is_separate_from_normal_install() -> None:
    wrapper = (ROOT / "deploy/nginx/seed_company_public_h2_assets.sh").read_text(encoding="utf-8")
    normal = (ROOT / "deploy/nginx/install_company_public_h2_assets.sh").read_text(encoding="utf-8")
    assert "company_public_h2_seed.py\" seed" in wrapper
    assert "flock -n" in wrapper
    assert 'exec 9<"$approved_root"' in wrapper
    assert ".seed.lock" not in wrapper
    assert "company_public_h2_seed" not in normal
    assert "rm -rf" not in wrapper
