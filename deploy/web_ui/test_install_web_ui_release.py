"""Cross-platform functional tests for the immutable Web release installer."""
from __future__ import annotations

from hashlib import sha256
import importlib.machinery
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "deploy/web_ui/install_web_ui_release.sh"
LOADER = importlib.machinery.SourceFileLoader("web_release", str(MODULE))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC
release = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release
LOADER.exec_module(release)


def _archive(tmp_path: Path, marker: int) -> tuple[Path, str, dict[str, bytes]]:
    release_sha = f"{marker:040x}"
    bodies = {
        "site/index.html": f"<!doctype html><html>{marker}</html>\n".encode(),
        f"site/assets/app.{marker:08x}.js": f"console.log({marker})\n".encode(),
        f"site/assets/app.{marker:08x}.css": f"body{{--marker:{marker}}}\n".encode(),
    }
    files = [
        {"path": path, "sha256": sha256(body).hexdigest(), "size": len(body)}
        for path, body in sorted(bodies.items())
    ]
    manifest = (json.dumps({
        "schema_version": "web_ui_release_v1",
        "release_sha": release_sha,
        "files": files,
    }, separators=(",", ":")) + "\n").encode()
    archive = tmp_path / f"web-{marker}.tgz"
    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as bundle:
        # GNU tar includes explicit directory entries for this archive shape.
        # Keep the fixture representative of the release-build command rather
        # than exercising only Python tarfile's file-only subset.
        for name in ("site", "site/assets"):
            info = tarfile.TarInfo(name)
            info.type = tarfile.DIRTYPE
            info.mtime = 0
            info.mode = 0o755
            bundle.addfile(info)
        for name, body in {"web-ui-release.json": manifest, **bodies}.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mtime = 0
            info.mode = 0o644
            bundle.addfile(info, BytesIO(body))
    return archive, release_sha, bodies


@pytest.fixture
def portable_pointer(monkeypatch: pytest.MonkeyPatch):
    def read(root: Path):
        pointer = root / ".test-current"
        return pointer.read_text(encoding="ascii") if pointer.exists() else None

    def replace(root: Path, value: str | None):
        pointer = root / ".test-current"
        if value is None:
            if pointer.exists():
                pointer.unlink()
        else:
            pointer.write_text(value, encoding="ascii")

    monkeypatch.setattr(release, "_read_current_sha", read)
    monkeypatch.setattr(release, "_replace_current", replace)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "approved-web-root"
    root.mkdir(mode=0o750)
    if os.name != "nt":
        root.chmod(0o750)
    return root.resolve()


def _install(archive: Path, release_sha: str, root: Path, **kwargs):
    return release.install_release(
        archive,
        release_sha,
        root,
        root,
        sha256(archive.read_bytes()).hexdigest(),
        "127.0.0.1:8080",
        "http://pork.su",
        smoke=kwargs.pop("smoke", lambda *_args: None),
        **kwargs,
    )


def test_atomic_install_idempotency_and_current_plus_two_history(tmp_path: Path, portable_pointer) -> None:
    root = _root(tmp_path)
    installed = []
    for marker in (1, 2, 3, 4):
        archive, release_sha, bodies = _archive(tmp_path, marker)
        retained = _install(archive, release_sha, root)
        installed.append(release_sha)
        assert retained == tuple(reversed(installed[-3:]))
        target = root / "releases" / release_sha
        assert (target / "site/index.html").read_bytes() == bodies["site/index.html"]
        assert (root / ".test-current").read_text(encoding="ascii") == release_sha
    assert release._parse_release_set(root / "release-set.json") == tuple(reversed(installed[-3:]))

    archive, release_sha, _bodies = _archive(tmp_path, 4)
    before = (root / "release-set.json").read_bytes()
    assert _install(archive, release_sha, root) == tuple(reversed(installed[-3:]))
    assert (root / "release-set.json").read_bytes() == before


@pytest.mark.skipif(os.name == "nt", reason="POSIX nginx group/mode contract")
def test_new_web_release_files_bind_to_effective_nginx_group(tmp_path: Path, portable_pointer) -> None:
    root = _root(tmp_path)
    archive, release_sha, _bodies = _archive(tmp_path, 1)
    _install(archive, release_sha, root)
    target = root / "releases" / release_sha
    for path in (target, *target.rglob("*")):
        if path.is_symlink():
            continue
        metadata = path.stat(follow_symlinks=False)
        assert metadata.st_uid == os.geteuid()
        assert metadata.st_gid == os.getegid()
        assert metadata.st_mode & 0o777 == (0o750 if path.is_dir() else 0o640)


@pytest.mark.parametrize("phase", ("history", "pointer", "smoke"))
def test_post_history_failure_restores_exact_previous_pointers(tmp_path: Path, portable_pointer, phase: str) -> None:
    root = _root(tmp_path)
    first_archive, first_sha, _ = _archive(tmp_path, 1)
    _install(first_archive, first_sha, root)
    before_history = (root / "release-set.json").read_bytes()

    second_archive, second_sha, _ = _archive(tmp_path, 2)
    with pytest.raises(release.WebReleaseError, match=f"injected Web {phase}"):
        _install(second_archive, second_sha, root, fail_phase=phase)
    assert (root / ".test-current").read_text(encoding="ascii") == first_sha
    assert (root / "release-set.json").read_bytes() == before_history
    assert (root / "releases" / second_sha).is_dir()  # immutable orphan, never deleted


def test_failed_real_smoke_restores_previous_pointer(tmp_path: Path, portable_pointer) -> None:
    root = _root(tmp_path)
    first_archive, first_sha, _ = _archive(tmp_path, 1)
    _install(first_archive, first_sha, root)
    before_history = (root / "release-set.json").read_bytes()

    second_archive, second_sha, _ = _archive(tmp_path, 2)
    def fail_smoke(*_args):
        raise release.WebReleaseError("closed smoke failure")
    with pytest.raises(release.WebReleaseError, match="closed smoke"):
        _install(second_archive, second_sha, root, smoke=fail_smoke)
    assert (root / ".test-current").read_text(encoding="ascii") == first_sha
    assert (root / "release-set.json").read_bytes() == before_history


def test_rollback_uninitialized_removes_only_first_pointer_metadata_and_is_idempotent(
    tmp_path: Path, portable_pointer
) -> None:
    root = _root(tmp_path)
    archive, release_sha, _ = _archive(tmp_path, 1)
    _install(archive, release_sha, root)
    immutable_release = root / "releases" / release_sha

    release.rollback_uninitialized(root, root, release_sha)
    assert not (root / ".test-current").exists()
    assert not (root / "release-set.json").exists()
    assert immutable_release.is_dir()
    release.rollback_uninitialized(root, root, release_sha)
    assert immutable_release.is_dir()


def test_rollback_uninitialized_completes_exact_interrupted_pointer_first_state(
    tmp_path: Path, portable_pointer
) -> None:
    root = _root(tmp_path)
    archive, release_sha, _ = _archive(tmp_path, 1)
    _install(archive, release_sha, root)
    (root / ".test-current").unlink()
    release.rollback_uninitialized(root, root, release_sha)
    assert not (root / "release-set.json").exists()


def test_rollback_uninitialized_refuses_prior_or_different_release_state(
    tmp_path: Path, portable_pointer
) -> None:
    root = _root(tmp_path)
    first_archive, first_sha, _ = _archive(tmp_path, 1)
    second_archive, second_sha, _ = _archive(tmp_path, 2)
    _install(first_archive, first_sha, root)
    _install(second_archive, second_sha, root)
    before_pointer = (root / ".test-current").read_bytes()
    before_history = (root / "release-set.json").read_bytes()
    with pytest.raises(release.WebReleaseError, match="exact first release"):
        release.rollback_uninitialized(root, root, second_sha)
    assert (root / ".test-current").read_bytes() == before_pointer
    assert (root / "release-set.json").read_bytes() == before_history


def test_rollback_uninitialized_cli_contract(tmp_path: Path, portable_pointer, capsys) -> None:
    root = _root(tmp_path)
    archive, release_sha, _ = _archive(tmp_path, 1)
    _install(archive, release_sha, root)
    assert release.main(
        [str(MODULE), "rollback-uninitialized", release_sha, str(root), str(root)]
    ) == 0
    assert capsys.readouterr().out == f"{release_sha}\n"


@pytest.mark.parametrize("member_name", ("../escape", "/absolute", "site/../escape", "site\\escape"))
def test_archive_path_escape_is_rejected_before_root_mutation(tmp_path: Path, portable_pointer, member_name: str) -> None:
    archive, release_sha, _ = _archive(tmp_path, 1)
    with tarfile.open(archive, "a:gz") if False else tarfile.open(tmp_path / "bad.tgz", "w:gz") as bundle:
        body = b"bad"
        info = tarfile.TarInfo(member_name)
        info.size = len(body)
        bundle.addfile(info, BytesIO(body))
    bad = tmp_path / "bad.tgz"
    root = _root(tmp_path)
    with pytest.raises(release.WebReleaseError):
        release.install_release(
            bad, release_sha, root, root, sha256(bad.read_bytes()).hexdigest(),
            "127.0.0.1:8080", "http://pork.su", smoke=lambda *_args: None,
        )
    assert list(root.iterdir()) == []


def test_archive_symlink_member_digest_and_unapproved_root_fail_closed(tmp_path: Path, portable_pointer) -> None:
    archive, release_sha, _ = _archive(tmp_path, 1)
    root = _root(tmp_path)
    with pytest.raises(release.WebReleaseError, match="digest"):
        release.install_release(
            archive, release_sha, root, root, "f" * 64,
            "127.0.0.1:8080", "http://pork.su", smoke=lambda *_args: None,
        )
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(release.WebReleaseError, match="not approved"):
        release.install_release(
            archive, release_sha, root, other.resolve(), sha256(archive.read_bytes()).hexdigest(),
            "127.0.0.1:8080", "http://pork.su", smoke=lambda *_args: None,
        )
    assert list(root.iterdir()) == []


def test_archive_rejects_directory_outside_manifest_parent_graph(tmp_path: Path, portable_pointer) -> None:
    archive, release_sha, _ = _archive(tmp_path, 1)
    bad = tmp_path / "bad-directory.tgz"
    with tarfile.open(archive, "r:gz") as source, tarfile.open(bad, "w:gz", format=tarfile.PAX_FORMAT) as target:
        for member in source.getmembers():
            extracted = source.extractfile(member) if member.isfile() else None
            target.addfile(member, extracted)
        unknown = tarfile.TarInfo("site/not-in-manifest")
        unknown.type = tarfile.DIRTYPE
        unknown.mtime = 0
        unknown.mode = 0o755
        target.addfile(unknown)

    root = _root(tmp_path)
    with pytest.raises(release.WebReleaseError, match="directory graph mismatch"):
        _install(bad, release_sha, root)
    assert list(root.iterdir()) == []


def test_read_only_archive_verifier_hashes_every_payload_and_cli(tmp_path: Path, capsys) -> None:
    archive, release_sha, _ = _archive(tmp_path, 1)
    archive_digest = sha256(archive.read_bytes()).hexdigest()
    assert release.verify_archive(archive, release_sha, archive_digest).release_sha == release_sha
    assert release.main([str(MODULE), "verify", str(archive), release_sha, archive_digest]) == 0
    assert capsys.readouterr().out == f"{release_sha}\n"

    corrupt = tmp_path / "corrupt-payload.tgz"
    with tarfile.open(archive, "r:gz") as source, tarfile.open(corrupt, "w:gz", format=tarfile.PAX_FORMAT) as target:
        for member in source.getmembers():
            if member.name == "site/index.html":
                target.addfile(member, BytesIO(b"x" * member.size))
            else:
                extracted = source.extractfile(member) if member.isfile() else None
                target.addfile(member, extracted)
    with pytest.raises(release.WebReleaseError, match="member hash mismatch"):
        release.verify_archive(corrupt, release_sha, sha256(corrupt.read_bytes()).hexdigest())


def test_corrupt_existing_sha_directory_is_never_overwritten(tmp_path: Path, portable_pointer) -> None:
    root = _root(tmp_path)
    archive, release_sha, _ = _archive(tmp_path, 1)
    _install(archive, release_sha, root)
    (root / "releases" / release_sha / "site/index.html").write_bytes(b"corrupt")
    with pytest.raises(release.WebReleaseError, match="mismatch"):
        _install(archive, release_sha, root)


def test_installer_has_exact_identity_loopback_and_no_broad_delete_contract() -> None:
    source = MODULE.read_text(encoding="utf-8")
    assert "approved absolute directory" in source
    assert "ipaddress.ip_address" in source and "is_loopback" in source
    assert "os.replace" in source
    assert "rmtree" not in source and "rm -rf" not in source
    assert "release-set.json" in source and "[:3]" in source
