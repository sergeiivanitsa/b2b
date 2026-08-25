from pathlib import Path

import pytest

from product_api.company_reports.company_card_v2.public_h2_asset_manifest import (
    PublicH2AssetManifestError, load_public_h2_asset_manifest,
    public_h2_asset_manifest_sha256, validate_public_h2_asset_manifest,
)


def test_tracked_h2_asset_manifest_is_exact_and_deterministic() -> None:
    manifest = load_public_h2_asset_manifest()
    assert manifest.entry_js_path.startswith("/assets/company-public-h2.")
    assert manifest.entry_css_path.startswith("/assets/company-public-h2.")
    assert public_h2_asset_manifest_sha256(manifest) == manifest.manifest_sha256


@pytest.mark.parametrize("raw", [
    b'{}\n',
    b'\xef\xbb\xbf{}\n',
    b'{"assets":[]}\r\n',
])
def test_h2_asset_manifest_rejects_noncanonical_or_unknown_bytes(raw: bytes) -> None:
    with pytest.raises(PublicH2AssetManifestError):
        validate_public_h2_asset_manifest(raw)
