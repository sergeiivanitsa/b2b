"""Contracts for portable Docker runtime identity verification."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deploy.product_api import release_image_identity as identity


RELEASE_SHA = "1" * 40
ARCHIVE = f"product-api-{RELEASE_SHA}.oci.tar"
OCI_DIGEST = f"sha256:{'a' * 64}"
CONFIG_DIGEST = f"sha256:{'b' * 64}"


def _manifest(tmp_path: Path, record: object | None = None) -> Path:
    path = tmp_path / f"release-manifest-{RELEASE_SHA}.json"
    value = {
        "release_sha": RELEASE_SHA,
        "images": {
            ARCHIVE: record
            if record is not None
            else {
                "oci_digest": OCI_DIGEST,
                "config_digest": CONFIG_DIGEST,
            }
        },
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.mark.parametrize("observed", [OCI_DIGEST, CONFIG_DIGEST])
def test_verifier_accepts_both_exact_signed_docker_identity_semantics(
    tmp_path: Path,
    observed: str,
) -> None:
    assert identity.verify_observed_image_identity(
        _manifest(tmp_path), RELEASE_SHA, ARCHIVE, observed
    ) == observed


def test_verifier_rejects_unlisted_loaded_identity(tmp_path: Path) -> None:
    with pytest.raises(
        identity.ReleaseImageIdentityError,
        match="outside the signed OCI/config identity pair",
    ):
        identity.verify_observed_image_identity(
            _manifest(tmp_path),
            RELEASE_SHA,
            ARCHIVE,
            f"sha256:{'c' * 64}",
        )


@pytest.mark.parametrize(
    "record",
    [
        {"config_digest": CONFIG_DIGEST},
        {"oci_digest": OCI_DIGEST, "config_digest": "invalid"},
        {"oci_digest": OCI_DIGEST, "config_digest": OCI_DIGEST},
        {
            "oci_digest": OCI_DIGEST,
            "config_digest": CONFIG_DIGEST,
            "unexpected": CONFIG_DIGEST,
        },
    ],
)
def test_verifier_rejects_missing_malformed_or_ambiguous_signed_pair(
    tmp_path: Path,
    record: object,
) -> None:
    with pytest.raises(
        identity.ReleaseImageIdentityError,
        match="signed image identity pair is invalid",
    ):
        identity.signed_image_identities(
            _manifest(tmp_path, record), RELEASE_SHA, ARCHIVE
        )


def test_cli_is_fail_closed_and_prints_only_verified_identity(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = _manifest(tmp_path)
    assert identity.main(
        ["release_image_identity.py", str(manifest), RELEASE_SHA, ARCHIVE, OCI_DIGEST]
    ) == 0
    assert capsys.readouterr().out == f"{OCI_DIGEST}\n"

    assert identity.main(
        [
            "release_image_identity.py",
            str(manifest),
            RELEASE_SHA,
            ARCHIVE,
            f"sha256:{'c' * 64}",
        ]
    ) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "outside the signed OCI/config identity pair" in captured.err
