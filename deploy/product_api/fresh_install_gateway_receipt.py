"""Create or verify the immutable prior-Gateway identity for a fresh install."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any


SCHEMA_VERSION = "production_fresh_install_prior_gateway_v1"
_SHA = re.compile(r"[0-9a-f]{40}")
_IMAGE = re.compile(r"sha256:[0-9a-f]{64}")
_PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]*")


class PriorGatewayReceiptError(RuntimeError):
    pass


def _canonical(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()


def _payload(
    release_sha: str,
    project: str,
    image_id: str,
    prior_release_commit: str,
) -> dict[str, Any]:
    if _SHA.fullmatch(release_sha) is None:
        raise PriorGatewayReceiptError("fresh-install release SHA is invalid; STOP")
    if _PROJECT.fullmatch(project) is None:
        raise PriorGatewayReceiptError("prior Gateway compose project is invalid; STOP")
    if _IMAGE.fullmatch(image_id) is None:
        raise PriorGatewayReceiptError("prior Gateway image identity is invalid; STOP")
    if prior_release_commit != "-" and _SHA.fullmatch(prior_release_commit) is None:
        raise PriorGatewayReceiptError("prior Gateway release identity is invalid; STOP")
    return {
        "gateway_image_id": image_id,
        "gateway_release_commit": None if prior_release_commit == "-" else prior_release_commit,
        "project": project,
        "release_sha": release_sha,
        "schema_version": SCHEMA_VERSION,
    }


def _validate_path(path: Path) -> None:
    if not path.is_absolute() or path.name != "prior-gateway.json":
        raise PriorGatewayReceiptError("prior Gateway receipt path is invalid; STOP")
    parent = path.parent
    parent_metadata = parent.stat(follow_symlinks=False)
    if parent.is_symlink() or not stat.S_ISDIR(parent_metadata.st_mode):
        raise PriorGatewayReceiptError("prior Gateway receipt parent is invalid; STOP")


def _read(path: Path, release_sha: str) -> dict[str, Any]:
    _validate_path(path)
    metadata = path.stat(follow_symlinks=False)
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise PriorGatewayReceiptError("prior Gateway receipt is not a regular file; STOP")
    if metadata.st_uid != 0 or metadata.st_gid != 0 or stat.S_IMODE(metadata.st_mode) != 0o640:
        raise PriorGatewayReceiptError("prior Gateway receipt ownership/mode mismatch; STOP")
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PriorGatewayReceiptError("prior Gateway receipt is invalid JSON; STOP") from error
    if not isinstance(value, dict) or raw != _canonical(value):
        raise PriorGatewayReceiptError("prior Gateway receipt is not canonical; STOP")
    expected = _payload(
        release_sha,
        value.get("project", ""),
        value.get("gateway_image_id", ""),
        value.get("gateway_release_commit") or "-",
    )
    if value != expected:
        raise PriorGatewayReceiptError("prior Gateway receipt identity mismatch; STOP")
    return value


def _write(
    path: Path,
    release_sha: str,
    project: str,
    image_id: str,
    prior_release_commit: str,
) -> dict[str, Any]:
    _validate_path(path)
    expected = _payload(release_sha, project, image_id, prior_release_commit)
    if path.exists() or path.is_symlink():
        value = _read(path, release_sha)
        if value != expected:
            raise PriorGatewayReceiptError("prior Gateway receipt is immutable; STOP")
        return value
    temporary = path.with_name(f".prior-gateway.{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PriorGatewayReceiptError("prior Gateway receipt temporary exists; STOP")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o640)
    try:
        os.fchmod(descriptor, 0o640)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(_canonical(expected))
            handle.flush()
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return _read(path, release_sha)


def _print(value: dict[str, Any]) -> None:
    prior_commit = value["gateway_release_commit"] or "-"
    print(value["project"])
    print(value["gateway_image_id"])
    print(prior_commit)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    read = subparsers.add_parser("read")
    read.add_argument("path", type=Path)
    read.add_argument("release_sha")
    write = subparsers.add_parser("write")
    write.add_argument("path", type=Path)
    write.add_argument("release_sha")
    write.add_argument("project")
    write.add_argument("image_id")
    write.add_argument("prior_release_commit")
    args = parser.parse_args(argv[1:])
    try:
        if args.command == "read":
            value = _read(args.path, args.release_sha)
        else:
            value = _write(
                args.path,
                args.release_sha,
                args.project,
                args.image_id,
                args.prior_release_commit,
            )
        _print(value)
    except (OSError, PriorGatewayReceiptError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
