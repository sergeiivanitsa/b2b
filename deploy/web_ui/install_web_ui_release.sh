#!/usr/bin/env python3
"""Atomic immutable Web UI release installer (Python, despite the runbook suffix)."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from http.client import HTTPResponse
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import ssl
import sys
import tarfile
from urllib.parse import urlsplit

_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_FILES = 10_000
_MAX_TOTAL_BYTES = 256 * 1024 * 1024
_PHASES = frozenset({"archive", "extract", "release", "history", "pointer", "smoke"})


class WebReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebFile:
    path: str
    sha256_hex: str
    size: int


@dataclass(frozen=True)
class WebManifest:
    release_sha: str
    files: tuple[WebFile, ...]
    raw_bytes: bytes


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _relative_file(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise WebReleaseError("web release path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise WebReleaseError("web release path is invalid")
    normalized = path.as_posix()
    if not normalized.startswith("site/") or normalized == "site/":
        raise WebReleaseError("web release path is outside site root")
    return normalized


def _duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WebReleaseError("web release manifest has duplicate keys")
        result[key] = value
    return result


def parse_manifest(raw: bytes, expected_sha: str) -> WebManifest:
    if (
        len(raw) > 2 * 1024 * 1024
        or raw.startswith(b"\xef\xbb\xbf")
        or b"\r" in raw
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
    ):
        raise WebReleaseError("web release manifest bytes invalid")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebReleaseError("web release manifest json invalid") from exc
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "release_sha", "files"}
        or data.get("schema_version") != "web_ui_release_v1"
        or data.get("release_sha") != expected_sha
        or not isinstance(data.get("files"), list)
        or not data["files"]
        or len(data["files"]) > _MAX_FILES
    ):
        raise WebReleaseError("web release manifest schema invalid")
    files: list[WebFile] = []
    for item in data["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
            raise WebReleaseError("web release file entry invalid")
        path = _relative_file(item["path"])
        digest = item["sha256"]
        size = item["size"]
        if (
            not isinstance(digest, str)
            or _DIGEST.fullmatch(digest) is None
            or type(size) is not int
            or size < 0
            or size > _MAX_TOTAL_BYTES
        ):
            raise WebReleaseError("web release file identity invalid")
        files.append(WebFile(path, digest, size))
    paths = tuple(item.path for item in files)
    if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
        raise WebReleaseError("web release file order invalid")
    if "site/index.html" not in paths or sum(item.size for item in files) > _MAX_TOTAL_BYTES:
        raise WebReleaseError("web release required file or size invalid")
    canonical = (json.dumps(data, separators=(",", ":")) + "\n").encode("utf-8")
    if canonical != raw:
        raise WebReleaseError("web release manifest is not canonical json")
    return WebManifest(expected_sha, tuple(files), raw)


def _archive_members(archive: Path, expected_sha: str) -> tuple[WebManifest, dict[str, tarfile.TarInfo]]:
    if _is_link(archive) or not archive.is_file():
        raise WebReleaseError("web release archive missing or symlinked")
    try:
        with tarfile.open(archive, mode="r:gz") as bundle:
            members = bundle.getmembers()
            if len(members) > (_MAX_FILES * 2) + 2:
                raise WebReleaseError("web release archive has too many members")
            by_name: dict[str, tarfile.TarInfo] = {}
            directory_names: set[str] = set()
            observed_names: set[str] = set()
            for member in members:
                name = member.name.rstrip("/")
                if not name or name in observed_names or member.issym() or member.islnk():
                    raise WebReleaseError("web release archive member invalid")
                observed_names.add(name)
                if member.isdir():
                    if name != "site":
                        _relative_file(name)
                    directory_names.add(name)
                    continue
                if not member.isfile():
                    raise WebReleaseError("web release archive member invalid")
                if name != "web-ui-release.json":
                    _relative_file(name)
                by_name[name] = member
            manifest_member = by_name.get("web-ui-release.json")
            if manifest_member is None:
                raise WebReleaseError("web release manifest missing")
            extracted = bundle.extractfile(manifest_member)
            if extracted is None:
                raise WebReleaseError("web release manifest missing")
            manifest = parse_manifest(extracted.read(), expected_sha)
            if set(by_name) != {"web-ui-release.json", *(item.path for item in manifest.files)}:
                raise WebReleaseError("web release archive graph mismatch")
            expected_directories = {"site"}
            for item in manifest.files:
                for parent in PurePosixPath(item.path).parents:
                    value = parent.as_posix()
                    if value == ".":
                        continue
                    expected_directories.add(value)
            if not directory_names.issubset(expected_directories):
                raise WebReleaseError("web release archive directory graph mismatch")
            for item in manifest.files:
                if by_name[item.path].size != item.size:
                    raise WebReleaseError("web release archive size mismatch")
            return manifest, by_name
    except (tarfile.TarError, OSError) as exc:
        raise WebReleaseError("web release archive invalid") from exc


def verify_archive(archive: Path, release_sha: str, archive_sha256: str) -> WebManifest:
    """Verify the complete immutable archive graph without touching a release root."""
    if _SHA.fullmatch(release_sha) is None or _DIGEST.fullmatch(archive_sha256) is None:
        raise WebReleaseError("Web release identity invalid")
    if _is_link(archive) or not archive.is_file():
        raise WebReleaseError("web release archive missing or symlinked")
    if sha256(archive.read_bytes()).hexdigest() != archive_sha256:
        raise WebReleaseError("Web release archive digest mismatch")
    manifest, members = _archive_members(archive, release_sha)
    try:
        with tarfile.open(archive, mode="r:gz") as bundle:
            for item in manifest.files:
                source = bundle.extractfile(members[item.path])
                if source is None:
                    raise WebReleaseError("web release archive member missing")
                digest = sha256()
                remaining = item.size
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise WebReleaseError("web release archive member truncated")
                    digest.update(chunk)
                    remaining -= len(chunk)
                if source.read(1) or digest.hexdigest() != item.sha256_hex:
                    raise WebReleaseError("web release archive member hash mismatch")
    except (tarfile.TarError, OSError) as exc:
        raise WebReleaseError("web release archive invalid") from exc
    return manifest


def _fsync_dir(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _write_atomic(path: Path, data: bytes) -> None:
    if _is_link(path):
        raise WebReleaseError("web release metadata must not be symlinked")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        if temporary.exists() and not _is_link(temporary):
            temporary.unlink()


def _remove_staging(path: Path, releases: Path) -> None:
    """Remove only an invocation-owned staging tree inside the approved root."""
    try:
        if path.parent.resolve(strict=True) != releases.resolve(strict=True) or not path.name.startswith(".staging-"):
            raise WebReleaseError("refusing unsafe Web staging cleanup")
    except OSError as exc:
        raise WebReleaseError("refusing unsafe Web staging cleanup") from exc
    if not path.exists() or _is_link(path):
        return
    for current_root, directory_names, file_names in os.walk(path, topdown=False, followlinks=False):
        current = Path(current_root)
        for name in file_names:
            candidate = current / name
            if _is_link(candidate):
                raise WebReleaseError("staging tree contains a link")
            candidate.unlink()
        for name in directory_names:
            candidate = current / name
            if _is_link(candidate):
                raise WebReleaseError("staging tree contains a link")
            candidate.rmdir()
    path.rmdir()


def _validate_release(directory: Path, manifest: WebManifest) -> None:
    if _is_link(directory) or not directory.is_dir():
        raise WebReleaseError("immutable Web release directory invalid")
    expected = {item.path.removeprefix("site/"): item for item in manifest.files}
    actual: set[str] = set()
    site = directory / "site"
    if _is_link(site) or not site.is_dir():
        raise WebReleaseError("immutable Web site directory invalid")
    for current_root, directory_names, file_names in os.walk(site, followlinks=False):
        current = Path(current_root)
        for name in directory_names:
            if _is_link(current / name):
                raise WebReleaseError("immutable Web release contains a link")
        for name in file_names:
            path = current / name
            if _is_link(path) or not path.is_file():
                raise WebReleaseError("immutable Web release contains a non-file")
            relative = path.relative_to(site).as_posix()
            actual.add(relative)
            item = expected.get(relative)
            if item is None:
                raise WebReleaseError("immutable Web release has an unknown file")
            data = path.read_bytes()
            if len(data) != item.size or sha256(data).hexdigest() != item.sha256_hex:
                raise WebReleaseError("immutable Web release file mismatch")
    if actual != set(expected):
        raise WebReleaseError("immutable Web release graph mismatch")
    stored_manifest = directory / "web-ui-release.json"
    if _is_link(stored_manifest) or not stored_manifest.is_file() or stored_manifest.read_bytes() != manifest.raw_bytes:
        raise WebReleaseError("immutable Web release manifest mismatch")


def _extract_release(archive: Path, stage: Path, manifest: WebManifest) -> None:
    stage.mkdir(mode=0o750)
    (stage / "site").mkdir(mode=0o750)
    with tarfile.open(archive, mode="r:gz") as bundle:
        for item in manifest.files:
            member = bundle.getmember(item.path)
            source = bundle.extractfile(member)
            if source is None:
                raise WebReleaseError("web release archive member missing")
            destination = stage / Path(*PurePosixPath(item.path).parts)
            destination.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
            with destination.open("xb") as handle:
                remaining = item.size
                digest = sha256()
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise WebReleaseError("web release archive member truncated")
                    handle.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
                if source.read(1):
                    raise WebReleaseError("web release archive member grew")
                handle.flush()
                os.fsync(handle.fileno())
                if digest.hexdigest() != item.sha256_hex:
                    raise WebReleaseError("web release archive member hash mismatch")
    _write_atomic(stage / "web-ui-release.json", manifest.raw_bytes)
    for current_root, directory_names, _file_names in os.walk(stage, topdown=False):
        for name in directory_names:
            _fsync_dir(Path(current_root) / name)
        _fsync_dir(Path(current_root))


def _read_current_sha(root: Path) -> str | None:
    pointer = root / "current"
    if not pointer.exists() and not pointer.is_symlink():
        return None
    if not pointer.is_symlink():
        raise WebReleaseError("Web current pointer is not a symlink")
    target = os.readlink(pointer)
    expected_prefix = "releases/"
    if not target.startswith(expected_prefix) or _SHA.fullmatch(target.removeprefix(expected_prefix)) is None:
        raise WebReleaseError("Web current pointer target invalid")
    return target.removeprefix(expected_prefix)


def _replace_current(root: Path, release_sha: str | None) -> None:
    pointer = root / "current"
    temporary = root / f".current.{os.getpid()}.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise WebReleaseError("Web pointer temporary path collision")
    if release_sha is None:
        if pointer.is_symlink():
            pointer.unlink()
            _fsync_dir(root)
        elif pointer.exists():
            raise WebReleaseError("Web current pointer is not a symlink")
        return
    os.symlink(f"releases/{release_sha}", temporary, target_is_directory=True)
    try:
        os.replace(temporary, pointer)
        _fsync_dir(root)
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def _release_set_bytes(releases: tuple[str, ...]) -> bytes:
    return (json.dumps({
        "schema_version": "web_ui_release_set_v1",
        "current_release_sha": releases[0],
        "retained_release_sha": list(releases),
    }, separators=(",", ":")) + "\n").encode()


def _parse_release_set(path: Path) -> tuple[str, ...]:
    if _is_link(path) or not path.is_file():
        raise WebReleaseError("Web release set missing or symlinked")
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebReleaseError("Web release set invalid") from exc
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "current_release_sha", "retained_release_sha"}
        or data.get("schema_version") != "web_ui_release_set_v1"
        or not isinstance(data.get("retained_release_sha"), list)
        or not 1 <= len(data["retained_release_sha"]) <= 3
        or data["current_release_sha"] != data["retained_release_sha"][0]
        or len(set(data["retained_release_sha"])) != len(data["retained_release_sha"])
        or not all(isinstance(value, str) and _SHA.fullmatch(value) for value in data["retained_release_sha"])
        or raw != _release_set_bytes(tuple(data["retained_release_sha"]))
    ):
        raise WebReleaseError("Web release set invalid")
    return tuple(data["retained_release_sha"])


def _connect(value: str) -> tuple[str, int]:
    if value.count(":") != 1:
        raise WebReleaseError("Web smoke connect target invalid")
    host, port_text = value.rsplit(":", 1)
    try:
        address = ipaddress.ip_address(host)
        port = int(port_text)
    except ValueError as exc:
        raise WebReleaseError("Web smoke connect target invalid") from exc
    if not address.is_loopback or not 1 <= port <= 65535:
        raise WebReleaseError("Web smoke connect target invalid")
    return host, port


def _origin(value: str) -> tuple[str, str]:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise WebReleaseError("Web smoke public origin invalid")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    host = parsed.hostname if port in {80, 443} else f"{parsed.hostname}:{port}"
    return parsed.scheme, host


def _smoke_release(connect_target: str, public_origin: str, expected_index_digest: str) -> None:
    connect = _connect(connect_target)
    scheme, host = _origin(public_origin)
    server_name = urlsplit(public_origin).hostname
    assert server_name is not None
    raw_socket = socket.create_connection(connect, timeout=5)
    connection = raw_socket
    try:
        if scheme == "https":
            connection = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=server_name)
        connection.sendall((
            "GET / HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Accept: text/html\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii"))
        response = HTTPResponse(connection)
        response.begin()
        if response.status != 200 or sha256(response.read()).hexdigest() != expected_index_digest:
            raise WebReleaseError("Web post-switch smoke identity mismatch")
    except (OSError, ssl.SSLError) as exc:
        raise WebReleaseError("Web post-switch smoke failed") from exc
    finally:
        connection.close()


def _fail(phase: str, configured: str | None) -> None:
    if configured == phase:
        raise WebReleaseError(f"injected Web {phase} failure")


def install_release(
    archive: Path,
    release_sha: str,
    root: Path,
    approved_root: Path,
    archive_sha256: str,
    connect_target: str,
    public_origin: str,
    *,
    smoke=_smoke_release,
    fail_phase: str | None = None,
) -> tuple[str, ...]:
    if fail_phase is not None and fail_phase not in _PHASES:
        raise WebReleaseError("unknown Web failure phase")
    _connect(connect_target)
    _origin(public_origin)
    manifest = verify_archive(archive, release_sha, archive_sha256)
    _fail("archive", fail_phase)

    if not root.is_absolute() or not approved_root.is_absolute() or _is_link(root) or _is_link(approved_root):
        raise WebReleaseError("Web release root must be an approved absolute directory")
    try:
        stable_root = root.resolve(strict=True)
        approved = approved_root.resolve(strict=True)
    except OSError as exc:
        raise WebReleaseError("Web release root missing") from exc
    if stable_root != approved or not stable_root.is_dir():
        raise WebReleaseError("Web release root is not approved")
    releases = stable_root / "releases"
    if releases.exists():
        if _is_link(releases) or not releases.is_dir():
            raise WebReleaseError("Web releases root invalid")
    else:
        releases.mkdir(mode=0o750)
        _fsync_dir(stable_root)

    previous_sha = _read_current_sha(stable_root)
    history_path = stable_root / "release-set.json"
    previous_history_bytes: bytes | None = None
    if previous_sha is None:
        if history_path.exists() or _is_link(history_path):
            raise WebReleaseError("Web current/release-set state is inconsistent")
        previous: tuple[str, ...] = ()
    else:
        previous = _parse_release_set(history_path)
        if previous[0] != previous_sha:
            raise WebReleaseError("Web current/release-set identity mismatch")
        previous_history_bytes = history_path.read_bytes()

    target = releases / release_sha
    stage = releases / f".staging-{release_sha}-{os.getpid()}"
    if stage.exists() or _is_link(stage):
        raise WebReleaseError("Web staging path collision")
    if target.exists() or _is_link(target):
        _validate_release(target, manifest)
    else:
        try:
            _extract_release(archive, stage, manifest)
            _fail("extract", fail_phase)
            _validate_release(stage, manifest)
            os.rename(stage, target)
            _fsync_dir(releases)
        finally:
            if stage.exists() and not _is_link(stage):
                _remove_staging(stage, releases)
    _validate_release(target, manifest)
    _fail("release", fail_phase)

    retained = tuple(dict.fromkeys((release_sha, *previous)))[:3]
    history_bytes = _release_set_bytes(retained)
    index = next(item for item in manifest.files if item.path == "site/index.html")
    try:
        _write_atomic(history_path, history_bytes)
        _fail("history", fail_phase)
        _replace_current(stable_root, release_sha)
        _fail("pointer", fail_phase)
        smoke(connect_target, public_origin, index.sha256_hex)
        _fail("smoke", fail_phase)
    except Exception:
        try:
            _replace_current(stable_root, previous_sha)
            if previous_history_bytes is None:
                if history_path.exists() and not _is_link(history_path):
                    history_path.unlink()
                    _fsync_dir(stable_root)
            else:
                _write_atomic(history_path, previous_history_bytes)
        except Exception as rollback_error:
            raise WebReleaseError("Web pointer rollback failed") from rollback_error
        raise
    return retained


def main(argv: list[str]) -> int:
    if len(argv) == 5 and argv[1] == "verify":
        try:
            manifest = verify_archive(Path(argv[2]), argv[3], argv[4])
        except (OSError, WebReleaseError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(manifest.release_sha)
        return 0
    if len(argv) != 7:
        print(
            "usage: install_web_ui_release.sh verify ARCHIVE RELEASE_SHA ARCHIVE_SHA256\n"
            "   or: install_web_ui_release.sh ARCHIVE RELEASE_SHA APPROVED_ROOT ARCHIVE_SHA256 LOOPBACK_CONNECT PUBLIC_ORIGIN",
            file=sys.stderr,
        )
        return 2
    try:
        retained = install_release(
            Path(argv[1]), argv[2], Path(argv[3]), Path(argv[3]), argv[4], argv[5], argv[6]
        )
    except (OSError, WebReleaseError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(retained[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
