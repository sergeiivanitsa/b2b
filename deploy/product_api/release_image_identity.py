#!/usr/bin/env python3
"""Verify a loaded Docker image against the exact signed release identities."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys


_RELEASE_SHA = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ReleaseImageIdentityError(ValueError):
    """Raised when a release image identity is missing, malformed, or different."""


def signed_image_identities(
    manifest_path: Path,
    release_sha: str,
    archive_name: str,
) -> frozenset[str]:
    if _RELEASE_SHA.fullmatch(release_sha) is None:
        raise ReleaseImageIdentityError("release SHA is invalid; STOP")
    try:
        raw = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseImageIdentityError("release manifest cannot be read; STOP") from exc
    if manifest.get("release_sha") != release_sha:
        raise ReleaseImageIdentityError("release manifest SHA mismatch; STOP")
    record = manifest.get("images", {}).get(archive_name)
    if not isinstance(record, dict) or set(record) != {
        "oci_digest",
        "config_digest",
    }:
        raise ReleaseImageIdentityError("signed image identity pair is invalid; STOP")
    identities = frozenset(record.values())
    if len(identities) != 2 or any(
        not isinstance(value, str) or _IMAGE_DIGEST.fullmatch(value) is None
        for value in identities
    ):
        raise ReleaseImageIdentityError("signed image identity pair is invalid; STOP")
    return identities


def verify_observed_image_identity(
    manifest_path: Path,
    release_sha: str,
    archive_name: str,
    observed_image_id: str,
) -> str:
    if _IMAGE_DIGEST.fullmatch(observed_image_id) is None:
        raise ReleaseImageIdentityError("loaded image identity is invalid; STOP")
    if observed_image_id not in signed_image_identities(
        manifest_path, release_sha, archive_name
    ):
        raise ReleaseImageIdentityError(
            "loaded image is outside the signed OCI/config identity pair; STOP"
        )
    return observed_image_id


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print(
            "usage: release_image_identity.py MANIFEST RELEASE_SHA ARCHIVE OBSERVED_IMAGE_ID",
            file=sys.stderr,
        )
        return 2
    try:
        verified = verify_observed_image_identity(
            Path(argv[1]), argv[2], argv[3], argv[4]
        )
    except ReleaseImageIdentityError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(verified)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
