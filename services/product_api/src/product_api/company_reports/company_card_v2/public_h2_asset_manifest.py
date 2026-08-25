"""Strict product-owned manifest for the isolated public H2 bundle."""
from __future__ import annotations

import base64
import hashlib
import importlib.resources
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

_PATH = re.compile(r"^/assets/company-public-h2\.[A-Za-z0-9_-]{8,}\.(?:js|css)$")
_HEX = re.compile(r"^[a-f0-9]{64}$")


class PublicH2AssetManifestError(ValueError):
    pass


@dataclass(frozen=True)
class PublicH2Asset:
    path: str
    media_type: str
    sha256_hex: str


@dataclass(frozen=True)
class PublicH2AssetManifest:
    schema_version: str
    public_contract_version: str
    canonical_json_profile: str
    entry_js_path: str
    entry_css_path: str
    optional_chunk_paths: tuple[str, ...]
    assets: tuple[PublicH2Asset, ...]
    raw_bytes: bytes
    manifest_sha256: str


def _path(value: object) -> str:
    if not isinstance(value, str) or _PATH.fullmatch(value) is None:
        raise PublicH2AssetManifestError("invalid asset path")
    return value


def validate_public_h2_asset_manifest(raw: bytes) -> PublicH2AssetManifest:
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n") or b"\r" in raw:
        raise PublicH2AssetManifestError("manifest must be exact UTF-8 LF")
    try:
        decoded = raw.decode("utf-8")
        data = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicH2AssetManifestError("invalid manifest JSON") from exc
    allowed = {"schema_version", "public_contract_version", "canonical_json_profile", "entry_js_path", "entry_css_path", "optional_chunk_paths", "assets"}
    if not isinstance(data, dict) or set(data) != allowed:
        raise PublicH2AssetManifestError("manifest fields are invalid")
    if data["schema_version"] != "company_public_h2_asset_manifest_v1" or data["public_contract_version"] != "company_public_h2_v1" or data["canonical_json_profile"] != "company_public_h2_cjson_v1":
        raise PublicH2AssetManifestError("manifest version is invalid")
    js, css = _path(data["entry_js_path"]), _path(data["entry_css_path"])
    if not js.endswith(".js") or not css.endswith(".css"):
        raise PublicH2AssetManifestError("entry type is invalid")
    chunks = data["optional_chunk_paths"]
    if not isinstance(chunks, list) or tuple(chunks) != tuple(sorted(chunks)):
        raise PublicH2AssetManifestError("chunk order is invalid")
    chunk_paths = tuple(_path(item) for item in chunks)
    asset_data = data["assets"]
    if not isinstance(asset_data, list) or not asset_data:
        raise PublicH2AssetManifestError("assets are missing")
    assets: list[PublicH2Asset] = []
    for item in asset_data:
        if not isinstance(item, dict) or set(item) != {"path", "media_type", "sha256_hex"}:
            raise PublicH2AssetManifestError("asset fields are invalid")
        path = _path(item["path"])
        media_type = item["media_type"]
        digest = item["sha256_hex"]
        if media_type not in {"text/javascript", "text/css"} or not isinstance(digest, str) or _HEX.fullmatch(digest) is None:
            raise PublicH2AssetManifestError("asset metadata is invalid")
        if (path.endswith(".js") and media_type != "text/javascript") or (path.endswith(".css") and media_type != "text/css"):
            raise PublicH2AssetManifestError("asset media type mismatches path")
        assets.append(PublicH2Asset(path, media_type, digest))
    paths = tuple(asset.path for asset in assets)
    if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
        raise PublicH2AssetManifestError("asset order is invalid")
    expected = {js, css, *chunk_paths}
    if set(paths) != expected or len(expected) != len(paths):
        raise PublicH2AssetManifestError("asset graph is invalid")
    return PublicH2AssetManifest(
        schema_version=data["schema_version"], public_contract_version=data["public_contract_version"],
        canonical_json_profile=data["canonical_json_profile"], entry_js_path=js, entry_css_path=css,
        optional_chunk_paths=chunk_paths, assets=tuple(assets), raw_bytes=raw,
        manifest_sha256=hashlib.sha256(raw).hexdigest(),
    )


def load_public_h2_asset_manifest() -> PublicH2AssetManifest:
    raw = importlib.resources.files(__package__).joinpath("public_h2_asset_manifest.json").read_bytes()
    return validate_public_h2_asset_manifest(raw)


def public_h2_asset_manifest_sha256(manifest: PublicH2AssetManifest) -> str:
    return manifest.manifest_sha256


def asset_integrity_attribute(asset: PublicH2Asset) -> str:
    return "sha256-" + base64.b64encode(bytes.fromhex(asset.sha256_hex)).decode("ascii")


__all__ = [name for name in globals() if name.startswith("PublicH2") or name in {"load_public_h2_asset_manifest", "validate_public_h2_asset_manifest", "public_h2_asset_manifest_sha256", "asset_integrity_attribute"}]
