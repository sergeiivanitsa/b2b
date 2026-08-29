"""Single strict installer/CLI for immutable public-H2 release assets."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from http.client import HTTPResponse
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import sys
from urllib.parse import urlsplit

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ASSET = re.compile(r"^/assets/(company-public-h2\.[A-Za-z0-9_-]{8,}\.(?:js|css))$")
_REQUIRED = {
    "schema_version", "public_contract_version", "canonical_json_profile",
    "entry_js_path", "entry_css_path", "optional_chunk_paths", "assets",
}
_PHASES = {
    "candidate", "history", "assets", "manifest", "store", "loopback",
    "pointer", "post_store", "post_loopback",
}


class ReleaseValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Asset:
    path: str
    sha256_hex: str
    media_type: str


@dataclass(frozen=True)
class Manifest:
    digest: str
    entry_js_path: str
    entry_css_path: str
    optional_chunk_paths: tuple[str, ...]
    assets: tuple[Asset, ...]
    raw_bytes: bytes


def sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _strict_json_bytes(path: Path, *, label: str) -> tuple[bytes, object]:
    if _is_link(path) or not path.is_file():
        raise ReleaseValidationError(f"{label} missing or symlinked")
    raw = path.read_bytes()
    if (
        raw.startswith(b"\xef\xbb\xbf")
        or b"\r" in raw
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
    ):
        raise ReleaseValidationError(f"{label} bytes invalid")
    try:
        decoded = raw.decode("utf-8")
        return raw, json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseValidationError(f"{label} json invalid") from exc


def _asset_path(value: object) -> str:
    if not isinstance(value, str) or _ASSET.fullmatch(value) is None:
        raise ReleaseValidationError("manifest asset path invalid")
    return value


def parse_manifest(path: Path) -> Manifest:
    raw, data = _strict_json_bytes(path, label="manifest")
    if not isinstance(data, dict) or set(data) != _REQUIRED:
        raise ReleaseValidationError("manifest schema invalid")
    if (
        data["schema_version"],
        data["public_contract_version"],
        data["canonical_json_profile"],
    ) != (
        "company_public_h2_asset_manifest_v1",
        "company_public_h2_v1",
        "company_public_h2_cjson_v1",
    ):
        raise ReleaseValidationError("manifest schema invalid")

    entry_js = _asset_path(data["entry_js_path"])
    entry_css = _asset_path(data["entry_css_path"])
    if not entry_js.endswith(".js") or not entry_css.endswith(".css"):
        raise ReleaseValidationError("manifest entry type invalid")
    chunks = data["optional_chunk_paths"]
    if not isinstance(chunks, list) or tuple(chunks) != tuple(sorted(chunks)):
        raise ReleaseValidationError("manifest chunk order invalid")
    chunk_paths = tuple(_asset_path(item) for item in chunks)

    asset_data = data["assets"]
    if not isinstance(asset_data, list) or not asset_data:
        raise ReleaseValidationError("manifest assets missing")
    assets: list[Asset] = []
    for item in asset_data:
        if not isinstance(item, dict) or set(item) != {"path", "sha256_hex", "media_type"}:
            raise ReleaseValidationError("manifest asset invalid")
        asset_path = _asset_path(item["path"])
        digest = item["sha256_hex"]
        media_type = item["media_type"]
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise ReleaseValidationError("manifest asset digest invalid")
        expected_media = "text/javascript" if asset_path.endswith(".js") else "text/css"
        if media_type != expected_media:
            raise ReleaseValidationError("manifest asset media type invalid")
        assets.append(Asset(asset_path, digest, media_type))
    paths = tuple(asset.path for asset in assets)
    if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
        raise ReleaseValidationError("manifest asset order invalid")
    graph = {entry_js, entry_css, *chunk_paths}
    if len(graph) != 2 + len(chunk_paths) or set(paths) != graph:
        raise ReleaseValidationError("manifest graph invalid")
    return Manifest(
        digest=sha256(raw).hexdigest(),
        entry_js_path=entry_js,
        entry_css_path=entry_css,
        optional_chunk_paths=chunk_paths,
        assets=tuple(assets),
        raw_bytes=raw,
    )


def parse_manifest_set(path: Path) -> tuple[str, str, str]:
    try:
        _raw, data = _strict_json_bytes(path, label="manifest set")
    except OSError as exc:
        raise ReleaseValidationError("manifest set invalid") from exc
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "current_manifest_sha256", "retained_manifest_sha256"}
        or data.get("schema_version") != "company_public_h2_manifest_set_v1"
    ):
        raise ReleaseValidationError("manifest set invalid")
    current = data.get("current_manifest_sha256")
    values = data.get("retained_manifest_sha256")
    if (
        not isinstance(values, list)
        or len(values) != 3
        or len(set(values)) != 3
        or current != values[0]
        or not all(isinstance(value, str) and _DIGEST.fullmatch(value) for value in values)
    ):
        raise ReleaseValidationError("manifest set invalid")
    return values[0], values[1], values[2]


def retained_digests(candidate: str, previous: tuple[str, str, str]) -> tuple[str, str, str]:
    if _DIGEST.fullmatch(candidate) is None:
        raise ReleaseValidationError("candidate digest invalid")
    return previous if candidate == previous[0] else (candidate, previous[0], previous[1])


def manifest_set_bytes(digests: tuple[str, str, str]) -> bytes:
    return (
        json.dumps(
            {
                "schema_version": "company_public_h2_manifest_set_v1",
                "current_manifest_sha256": digests[0],
                "retained_manifest_sha256": list(digests),
            },
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _stored_asset_path(root: Path, asset: Asset) -> Path:
    match = _ASSET.fullmatch(asset.path)
    assert match is not None
    return root / "assets" / match.group(1)


def _require_plain_directory(path: Path, *, label: str) -> None:
    if _is_link(path) or not path.is_dir():
        raise ReleaseValidationError(f"{label} missing or symlinked")


def _require_approved_root(root: Path, approved_root: Path) -> Path:
    if _is_link(root) or _is_link(approved_root):
        raise ReleaseValidationError("stable root must not be a symlink")
    try:
        resolved = root.resolve(strict=True)
        approved = approved_root.resolve(strict=True)
    except OSError as exc:
        raise ReleaseValidationError("stable root missing; authorized seed runbook required") from exc
    if resolved != approved:
        raise ReleaseValidationError("stable root is not approved")
    _require_plain_directory(resolved, label="stable root")
    _require_plain_directory(resolved / "assets", label="stable assets")
    _require_plain_directory(resolved / "manifests", label="stable manifests")
    _require_plain_directory(resolved / "manifests" / "sha256", label="stable manifest identities")
    return resolved


def validate_store(root: Path, digests: tuple[str, str, str]) -> tuple[Manifest, ...]:
    manifests: list[Manifest] = []
    for digest in digests:
        manifest = parse_manifest(root / "manifests" / "sha256" / f"{digest}.json")
        if manifest.digest != digest:
            raise ReleaseValidationError("manifest identity collision")
        for asset in manifest.assets:
            actual = _stored_asset_path(root, asset)
            if _is_link(actual) or not actual.is_file() or sha256_file(actual) != asset.sha256_hex:
                raise ReleaseValidationError("asset missing or mismatched")
        manifests.append(manifest)
    return tuple(manifests)


def _validate_source_graph(source: Path, product_manifest_path: Path) -> tuple[Manifest, Path]:
    _require_plain_directory(source, label="release source")
    entries = {item.name for item in source.iterdir()}
    if entries != {"assets", "public_h2_asset_manifest.json"}:
        raise ReleaseValidationError("candidate source graph invalid")
    source_manifest_path = source / "public_h2_asset_manifest.json"
    source_assets = source / "assets"
    _require_plain_directory(source_assets, label="candidate assets")
    candidate = parse_manifest(source_manifest_path)
    product = parse_manifest(product_manifest_path)
    if candidate.raw_bytes != product.raw_bytes or candidate.digest != product.digest:
        raise ReleaseValidationError("candidate Product manifest identity mismatch")
    expected_names = {asset.path.removeprefix("/assets/") for asset in candidate.assets}
    actual_names: set[str] = set()
    for item in source_assets.iterdir():
        if _is_link(item) or not item.is_file():
            raise ReleaseValidationError("candidate source asset symlink or non-file")
        actual_names.add(item.name)
    if actual_names != expected_names:
        raise ReleaseValidationError("candidate source graph invalid")
    for asset in candidate.assets:
        path = source_assets / asset.path.removeprefix("/assets/")
        if sha256_file(path) != asset.sha256_hex:
            raise ReleaseValidationError("candidate source asset missing or mismatched")
    return candidate, source_assets


def _fsync_dir(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _copy_immutable(source: Path, destination: Path) -> None:
    if _is_link(source) or not source.is_file():
        raise ReleaseValidationError("immutable source missing or symlinked")
    data = source.read_bytes()
    if _is_link(destination.parent):
        raise ReleaseValidationError("immutable destination directory is symlinked")
    if destination.exists() or _is_link(destination):
        if _is_link(destination) or not destination.is_file() or destination.read_bytes() != data:
            raise ReleaseValidationError("immutable basename collision")
        return
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            if os.name != "nt":
                os.fchmod(handle.fileno(), 0o640)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if _is_link(destination) or not destination.is_file() or destination.read_bytes() != data:
                raise ReleaseValidationError("immutable basename collision")
        else:
            _fsync_dir(destination.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _replace_pointer(path: Path, data: bytes) -> None:
    if _is_link(path):
        raise ReleaseValidationError("manifest pointer must not be a symlink")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            if os.name != "nt":
                os.fchmod(handle.fileno(), 0o640)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _connect_target(value: str) -> tuple[str, int]:
    if value.startswith("["):
        end = value.find("]")
        if end < 0 or end + 1 >= len(value) or value[end + 1] != ":":
            raise ReleaseValidationError("loopback connect target invalid")
        host, port_text = value[1:end], value[end + 2 :]
    else:
        if value.count(":") != 1:
            raise ReleaseValidationError("loopback connect target invalid")
        host, port_text = value.rsplit(":", 1)
    try:
        address = ipaddress.ip_address(host)
        port = int(port_text)
    except ValueError as exc:
        raise ReleaseValidationError("loopback connect target invalid") from exc
    if not address.is_loopback or not 1 <= port <= 65535:
        raise ReleaseValidationError("loopback connect target invalid")
    return host, port


def _origin(value: str) -> tuple[str, str, int]:
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
        raise ReleaseValidationError("public origin invalid")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ReleaseValidationError("public origin invalid") from exc
    host_header = parsed.hostname if port in {80, 443} else f"{parsed.hostname}:{port}"
    return parsed.scheme, host_header, port


def _loopback_fetch(connect_target: str, public_origin: str, asset_path: str) -> bytes:
    """Fetch with loopback TCP, exact public Host/SNI and no redirects."""
    connect_host, connect_port = _connect_target(connect_target)
    scheme, host_header, _origin_port = _origin(public_origin)
    server_name = urlsplit(public_origin).hostname
    assert server_name is not None
    raw_socket = socket.create_connection((connect_host, connect_port), timeout=5)
    connection = raw_socket
    try:
        if scheme == "https":
            connection = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=server_name)
        request = (
            f"GET {asset_path} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "Accept: */*\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        connection.sendall(request)
        response = HTTPResponse(connection)
        response.begin()
        if response.status != 200:
            raise ReleaseValidationError(f"loopback asset HTTP status {response.status}")
        return response.read()
    except (OSError, ssl.SSLError) as exc:
        raise ReleaseValidationError("loopback asset connection failed") from exc
    finally:
        connection.close()


def _fail(phase: str, configured: str | None) -> None:
    if configured == phase:
        raise ReleaseValidationError(f"injected {phase} failure")


def _verify_reachable(
    manifests: tuple[Manifest, ...], connect_target: str, public_origin: str, fetcher,
) -> None:
    for manifest in manifests:
        for asset in manifest.assets:
            try:
                returned = fetcher(connect_target, public_origin, asset.path)
            except ReleaseValidationError:
                raise
            except Exception as exc:
                raise ReleaseValidationError("loopback asset connection failed") from exc
            if sha256(returned).hexdigest() != asset.sha256_hex:
                raise ReleaseValidationError("loopback asset hash mismatch")


def install_release(
    source: Path,
    root: Path,
    connect_target: str,
    public_origin: str,
    product_manifest_path: Path,
    *,
    approved_root: Path,
    fetcher=_loopback_fetch,
    fail_phase: str | None = None,
) -> tuple[str, str, str]:
    """Validate, rotate and atomically publish one exact Product asset set."""
    if fail_phase is not None and fail_phase not in _PHASES:
        raise ReleaseValidationError("unknown failure phase")
    _connect_target(connect_target)
    _origin(public_origin)
    stable_root = _require_approved_root(root, approved_root)
    candidate, source_assets = _validate_source_graph(source, product_manifest_path)
    _fail("candidate", fail_phase)

    pointer = stable_root / "manifest-set.json"
    if _is_link(pointer) or not pointer.is_file():
        raise ReleaseValidationError("manifest set missing; authorized seed runbook required")
    prior_pointer = pointer.read_bytes()
    previous = parse_manifest_set(pointer)
    validate_store(stable_root, previous)
    _fail("history", fail_phase)

    for asset in candidate.assets:
        source_asset = source_assets / asset.path.removeprefix("/assets/")
        _copy_immutable(source_asset, _stored_asset_path(stable_root, asset))
    _fail("assets", fail_phase)
    _copy_immutable(
        source / "public_h2_asset_manifest.json",
        stable_root / "manifests" / "sha256" / f"{candidate.digest}.json",
    )
    _fail("manifest", fail_phase)

    retained = retained_digests(candidate.digest, previous)
    manifests = validate_store(stable_root, retained)
    _fail("store", fail_phase)
    _verify_reachable(manifests, connect_target, public_origin, fetcher)
    _fail("loopback", fail_phase)

    try:
        _replace_pointer(pointer, manifest_set_bytes(retained))
        _fail("pointer", fail_phase)
        committed = validate_store(stable_root, parse_manifest_set(pointer))
        _fail("post_store", fail_phase)
        _verify_reachable(committed, connect_target, public_origin, fetcher)
        _fail("post_loopback", fail_phase)
    except Exception:
        # _replace_pointer may raise from the directory fsync after os.replace
        # has already changed the bytes. Inspect the durable name rather than
        # relying on successful helper return, and restore the exact old bytes.
        try:
            current_pointer = pointer.read_bytes() if pointer.is_file() and not _is_link(pointer) else None
            if current_pointer != prior_pointer:
                _replace_pointer(pointer, prior_pointer)
        except Exception as rollback_error:
            raise ReleaseValidationError("manifest pointer rollback failed") from rollback_error
        raise
    return retained


def main(argv: list[str]) -> int:
    if len(argv) != 8 or argv[1] != "install":
        print(
            "usage: company_public_h2_release.py install SOURCE ROOT LOOPBACK_CONNECT PUBLIC_ORIGIN PRODUCT_MANIFEST APPROVED_ROOT",
            file=sys.stderr,
        )
        return 2
    try:
        retained = install_release(
            Path(argv[2]), Path(argv[3]), argv[4], argv[5], Path(argv[6]),
            approved_root=Path(argv[7]),
        )
    except (OSError, ReleaseValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(retained[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
