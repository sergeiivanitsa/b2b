"""Executable temporary-store contract for the production H2 installer CLI."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "deploy/nginx/company_public_h2_release.py"
SPEC = importlib.util.spec_from_file_location("h2release", MODULE)
assert SPEC and SPEC.loader
release = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release
SPEC.loader.exec_module(release)


def _manifest_data(seed: str) -> tuple[dict[str, object], dict[str, bytes]]:
    bodies = {
        f"company-public-h2.{seed}abcdefgh.css": f"{seed}-css".encode(),
        f"company-public-h2.{seed}abcdefgh.js": f"{seed}-js".encode(),
    }
    paths = sorted(f"/assets/{name}" for name in bodies)
    data: dict[str, object] = {
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
    return data, bodies


def _manifest(seed: str) -> tuple[bytes, dict[str, bytes]]:
    data, bodies = _manifest_data(seed)
    return (json.dumps(data, separators=(",", ":")) + "\n").encode(), bodies


def _release(source: Path, seed: str) -> tuple[Path, str]:
    raw, bodies = _manifest(seed)
    candidate = source / seed
    (candidate / "assets").mkdir(parents=True)
    (candidate / "public_h2_asset_manifest.json").write_bytes(raw)
    for name, body in bodies.items():
        (candidate / "assets" / name).write_bytes(body)
    return candidate, sha256(raw).hexdigest()


def _seed(store: Path, source: Path) -> tuple[str, str, str]:
    values: list[str] = []
    (store / "assets").mkdir(parents=True)
    (store / "manifests/sha256").mkdir(parents=True)
    for seed in ("one", "two", "three"):
        candidate, digest = _release(source, seed)
        for asset in (candidate / "assets").iterdir():
            (store / "assets" / asset.name).write_bytes(asset.read_bytes())
        (store / "manifests/sha256" / f"{digest}.json").write_bytes(
            (candidate / "public_h2_asset_manifest.json").read_bytes()
        )
        values.append(digest)
    retained = values[0], values[1], values[2]
    (store / "manifest-set.json").write_bytes(release.manifest_set_bytes(retained))
    return retained


class _Server(SimpleHTTPRequestHandler):
    directory: str

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=self.directory, **kwargs)

    def log_message(self, *_args):
        pass


def _loopback(store: Path):
    _Server.directory = str(store)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Server)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, f"127.0.0.1:{server.server_port}", "http://pork.su"


def _install(candidate: Path, store: Path, connect: str, origin: str, **kwargs):
    return release.install_release(
        candidate,
        store,
        connect,
        origin,
        kwargs.pop("product_manifest", candidate / "public_h2_asset_manifest.json"),
        approved_root=kwargs.pop("approved_root", store),
        **kwargs,
    )


def _pointer(store: Path) -> bytes:
    return (store / "manifest-set.json").read_bytes()


def _assert_store_and_responses(store: Path, retained: tuple[str, str, str], connect: str, origin: str) -> None:
    manifests = release.validate_store(store, retained)
    for manifest in manifests:
        for asset in manifest.assets:
            returned = release._loopback_fetch(connect, origin, asset.path)
            assert sha256(returned).hexdigest() == asset.sha256_hex


def _directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout
    else:
        link.symlink_to(target, target_is_directory=True)


def test_four_rotations_idempotency_and_every_stored_response_hash(tmp_path: Path) -> None:
    store, source = tmp_path / "store", tmp_path / "source"
    prior = _seed(store, source)
    server, connect, origin = _loopback(store)
    try:
        for seed in ("four", "five", "six", "seven"):
            candidate, digest = _release(source, seed)
            retained = _install(candidate, store, connect, origin)
            assert retained == (digest, prior[0], prior[1])
            assert release.parse_manifest_set(store / "manifest-set.json") == retained
            _assert_store_and_responses(store, retained, connect, origin)
            prior = retained
        before = _pointer(store)
        assert _install(source / "seven", store, connect, origin) == prior
        assert _pointer(store) == before
    finally:
        server.shutdown()


@pytest.mark.parametrize("phase", sorted(release._PHASES))
def test_every_injected_phase_preserves_exact_pointer_bytes(tmp_path: Path, phase: str) -> None:
    store, source = tmp_path / "store", tmp_path / "source"
    _seed(store, source)
    candidate, _ = _release(source, "four")
    before = _pointer(store)
    server, connect, origin = _loopback(store)
    try:
        with pytest.raises(release.ReleaseValidationError, match=f"injected {phase} failure"):
            _install(candidate, store, connect, origin, fail_phase=phase)
        assert _pointer(store) == before
    finally:
        server.shutdown()


def test_directory_fsync_failure_after_pointer_rename_restores_prior_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, source = tmp_path / "store", tmp_path / "source"
    _seed(store, source)
    candidate, _ = _release(source, "four")
    before = _pointer(store)
    original_fsync = release._fsync_dir
    failed = False

    def fail_once_after_pointer_change(path: Path) -> None:
        nonlocal failed
        if path == store and _pointer(store) != before and not failed:
            failed = True
            raise OSError("injected pointer directory fsync failure")
        original_fsync(path)

    monkeypatch.setattr(release, "_fsync_dir", fail_once_after_pointer_change)
    server, connect, origin = _loopback(store)
    try:
        with pytest.raises(OSError, match="pointer directory fsync"):
            _install(candidate, store, connect, origin)
        assert failed
        assert _pointer(store) == before
    finally:
        server.shutdown()


@pytest.mark.parametrize("failure", ("fresh", "one_predecessor", "malformed"))
def test_invalid_history_fails_before_pointer_creation_or_change(tmp_path: Path, failure: str) -> None:
    store, source = tmp_path / "store", tmp_path / "source"
    candidate, _ = _release(source, "four")
    if failure == "fresh":
        (store / "assets").mkdir(parents=True)
        (store / "manifests/sha256").mkdir(parents=True)
        before = None
    else:
        _seed(store, source)
        if failure == "one_predecessor":
            current = release.parse_manifest_set(store / "manifest-set.json")[0]
            (store / "manifest-set.json").write_bytes((json.dumps({
                "schema_version": "company_public_h2_manifest_set_v1",
                "current_manifest_sha256": current,
                "retained_manifest_sha256": [current],
            }, separators=(",", ":")) + "\n").encode())
        else:
            (store / "manifest-set.json").write_bytes(b"{malformed}\n")
        before = _pointer(store)
    server, connect, origin = _loopback(store)
    try:
        with pytest.raises(release.ReleaseValidationError, match="manifest set"):
            _install(candidate, store, connect, origin)
        if before is None:
            assert not (store / "manifest-set.json").exists()
        else:
            assert _pointer(store) == before
    finally:
        server.shutdown()


@pytest.mark.parametrize(
    "failure",
    (
        "missing_manifest", "wrong_manifest", "missing_asset", "wrong_asset",
        "candidate_asset", "immutable_collision", "altered_response", "connection",
    ),
)
def test_history_source_collision_and_network_failures_preserve_pointer(tmp_path: Path, failure: str) -> None:
    store, source = tmp_path / "store", tmp_path / "source"
    retained = _seed(store, source)
    candidate, _ = _release(source, "four")
    before = _pointer(store)
    first_manifest = store / "manifests/sha256" / f"{retained[0]}.json"
    first_asset_name = json.loads(first_manifest.read_text(encoding="utf-8"))["assets"][0]["path"].removeprefix("/assets/")
    if failure == "missing_manifest":
        first_manifest.unlink()
    elif failure == "wrong_manifest":
        first_manifest.write_bytes((source / "two" / "public_h2_asset_manifest.json").read_bytes())
    elif failure == "missing_asset":
        (store / "assets" / first_asset_name).unlink()
    elif failure == "wrong_asset":
        (store / "assets" / first_asset_name).write_bytes(b"wrong")
    elif failure == "candidate_asset":
        next((candidate / "assets").iterdir()).write_bytes(b"wrong")
    elif failure == "immutable_collision":
        candidate_asset = next((candidate / "assets").iterdir())
        (store / "assets" / candidate_asset.name).write_bytes(b"collision")
    server, connect, origin = _loopback(store)
    try:
        kwargs = {}
        if failure == "altered_response":
            kwargs["fetcher"] = lambda *_args: b"altered"
        elif failure == "connection":
            def unavailable(*_args):
                raise ConnectionError("unreachable")
            kwargs["fetcher"] = unavailable
        with pytest.raises((release.ReleaseValidationError, OSError)):
            _install(candidate, store, connect, origin, **kwargs)
        assert _pointer(store) == before
    finally:
        server.shutdown()


@pytest.mark.parametrize("failure", ("product_identity", "extra_source", "symlink_source"))
def test_product_identity_and_exact_source_graph_fail_closed(tmp_path: Path, failure: str) -> None:
    store, source = tmp_path / "store", tmp_path / "source"
    _seed(store, source)
    candidate, _ = _release(source, "four")
    other, _ = _release(source, "other")
    before = _pointer(store)
    product_manifest = candidate / "public_h2_asset_manifest.json"
    if failure == "product_identity":
        product_manifest = other / "public_h2_asset_manifest.json"
    elif failure == "extra_source":
        (candidate / "assets" / "extra.js").write_bytes(b"extra")
    else:
        real_assets = candidate / "real-assets"
        (candidate / "assets").rename(real_assets)
        _directory_link(candidate / "assets", real_assets)
    server, connect, origin = _loopback(store)
    try:
        with pytest.raises(release.ReleaseValidationError):
            _install(candidate, store, connect, origin, product_manifest=product_manifest)
        assert _pointer(store) == before
    finally:
        server.shutdown()


def test_symlink_or_junction_stable_root_is_rejected(tmp_path: Path) -> None:
    real_store, source = tmp_path / "real-store", tmp_path / "source"
    _seed(real_store, source)
    candidate, _ = _release(source, "four")
    linked_store = tmp_path / "linked-store"
    _directory_link(linked_store, real_store)
    before = _pointer(real_store)
    server, connect, origin = _loopback(real_store)
    try:
        with pytest.raises(release.ReleaseValidationError, match="symlink"):
            _install(candidate, linked_store, connect, origin, approved_root=linked_store)
        assert _pointer(real_store) == before
    finally:
        server.shutdown()


@pytest.mark.parametrize("mutation", ("swapped_entries", "wrong_media", "unsorted_chunks"))
def test_manifest_parser_mirrors_product_entry_media_and_order_rules(tmp_path: Path, mutation: str) -> None:
    data, _bodies = _manifest_data("strict")
    if mutation == "swapped_entries":
        data["entry_js_path"], data["entry_css_path"] = data["entry_css_path"], data["entry_js_path"]
    elif mutation == "wrong_media":
        data["assets"][0]["media_type"] = "text/javascript" if data["assets"][0]["path"].endswith(".css") else "text/css"
    else:
        chunk_a = "/assets/company-public-h2.zzzzzzzz.js"
        chunk_b = "/assets/company-public-h2.aaaaaaaa.js"
        data["optional_chunk_paths"] = [chunk_a, chunk_b]
        for path in sorted((chunk_a, chunk_b)):
            data["assets"].append({"path": path, "sha256_hex": "a" * 64, "media_type": "text/javascript"})
        data["assets"] = sorted(data["assets"], key=lambda item: item["path"])
    path = tmp_path / "manifest.json"
    path.write_bytes((json.dumps(data, separators=(",", ":")) + "\n").encode())
    with pytest.raises(release.ReleaseValidationError):
        release.parse_manifest(path)


def test_https_fetch_uses_loopback_tcp_public_host_and_sni_without_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class FakeSocket:
        def sendall(self, data): calls["request"] = data
        def close(self): calls["closed"] = True

    class FakeContext:
        def wrap_socket(self, sock, *, server_hostname):
            calls["sni"] = server_hostname
            return sock

    class FakeResponse:
        status = 200
        def __init__(self, sock): calls["response_socket"] = sock
        def begin(self): pass
        def read(self): return b"asset"

    fake_socket = FakeSocket()
    monkeypatch.setattr(release.socket, "create_connection", lambda target, timeout: calls.update(target=target, timeout=timeout) or fake_socket)
    monkeypatch.setattr(release.ssl, "create_default_context", lambda: FakeContext())
    monkeypatch.setattr(release, "HTTPResponse", FakeResponse)
    assert release._loopback_fetch("127.0.0.1:443", "https://pork.su", "/assets/company-public-h2.abcdefgh.js") == b"asset"
    assert calls["target"] == ("127.0.0.1", 443)
    assert calls["sni"] == "pork.su"
    assert b"Host: pork.su\r\n" in calls["request"]

    FakeResponse.status = 302
    with pytest.raises(release.ReleaseValidationError, match="HTTP status 302"):
        release._loopback_fetch("127.0.0.1:443", "https://pork.su", "/assets/company-public-h2.abcdefgh.js")


def test_actual_cli_path_installs_exact_product_identity(tmp_path: Path) -> None:
    store, source = tmp_path / "store", tmp_path / "source"
    prior = _seed(store, source)
    candidate, digest = _release(source, "four")
    server, connect, origin = _loopback(store)
    try:
        completed = subprocess.run(
            [
                sys.executable, str(MODULE), "install", str(candidate), str(store),
                connect, origin, str(candidate / "public_h2_asset_manifest.json"), str(store),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == digest
        assert release.parse_manifest_set(store / "manifest-set.json") == (digest, prior[0], prior[1])
    finally:
        server.shutdown()


def test_workflow_consumes_qa_artifacts_and_installs_h2_before_runtime_mutation() -> None:
    workflow = (ROOT / ".github/workflows/deploy_prod.yml").read_text(encoding="utf-8")
    sentinels = [
        "Download sole build-once release",
        "Reverify one SHA through attestation, manifests and artifacts",
        "Read-only RU/US preflight",
        "Install and loopback-verify H2 assets",
        "Drain both exact old workers",
        "python -m alembic -c /app/alembic.ini upgrade head",
        "Recreate and verify exact Gateway",
        "Atomically switch Web",
    ]
    positions = [workflow.index(value) for value in sentinels]
    assert positions == sorted(positions)
    assert "qa-attestation-{release_sha}.json" in workflow
    assert "127.0.0.1:443 https://pork.su" in workflow
    assert "npm run build" not in workflow
    assert "docker build" not in workflow
    assert "rm -rf /var/lib/pork/company-public-h2" not in workflow

    shell = (ROOT / "deploy/nginx/install_company_public_h2_assets.sh").read_text(encoding="utf-8")
    assert "approved_root=/var/lib/pork/company-public-h2/v1" in shell
    assert "approved_parent=/var/lib/pork/company-public-h2" in shell
    assert "realpath -e" in shell and "flock -x" in shell
    assert 'exec 9<"$approved_parent"' in shell
    assert '$target_root/.install.lock' not in shell
    assert '"$script_dir/company_public_h2_release.py" install' in shell
    assert shell.count("stat -c '%u:%g:%a' -- \"$target_root\"") == 2
    assert "mv -n" not in shell and "rm -rf" not in shell


def test_root_manual_runbook_delegates_to_default_off_exact_sha_runbook() -> None:
    readme = re.sub(r"\s+", " ", (ROOT / "README.md").read_text(encoding="utf-8"))
    assert "docs/development/runbooks/company-card-v2-rollout.md" in readme
    assert ".github/workflows/deploy_prod_fresh_install.yml" in readme
    assert "deletes only PostgreSQL schema `public`" in readme
    assert "Claims upload files are outside that destructive scope" in readme
    assert "persistent host bind" in readme
    assert "backup/bootstrap workflow is superseded" in readme
    assert "retained H1 anchor for `7707079463`" in readme
    assert "exact lowercase 40-hex" in readme


def test_actual_product_manifest_and_artifacts_install(tmp_path: Path) -> None:
    product = ROOT / "services/product_api/src/product_api/company_reports/company_card_v2/public_h2_asset_manifest.json"
    dist = ROOT / "services/web_ui/dist-company-public-h2/assets"
    parsed = release.parse_manifest(product)
    assert {item.media_type for item in parsed.assets} == {"text/css", "text/javascript"}
    store, source = tmp_path / "store", tmp_path / "source"
    _seed(store, source)
    candidate = source / "actual"
    (candidate / "assets").mkdir(parents=True)
    shutil.copy2(product, candidate / "public_h2_asset_manifest.json")
    for item in parsed.assets:
        name = item.path.removeprefix("/assets/")
        shutil.copy2(dist / name, candidate / "assets" / name)
    server, connect, origin = _loopback(store)
    try:
        assert _install(candidate, store, connect, origin, product_manifest=product)[0] == parsed.digest
    finally:
        server.shutdown()
