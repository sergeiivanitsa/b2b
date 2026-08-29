"""Fail-closed extraction for iteration-25 build-once browser artifacts."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile


class ReviewedArchiveError(RuntimeError):
    """Raised when a downloaded archive is not the closed expected graph."""


_MAX_MEMBERS = 200_000
_MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024


def _safe_member_path(name: str, *, root: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or not path.parts
        or path.parts[0] != root
    ):
        raise ReviewedArchiveError("archive member escapes the closed root")
    return path


def _safe_relative_link(member: PurePosixPath, target: str, *, root: str) -> None:
    link = PurePosixPath(target)
    if not target or "\\" in target or link.is_absolute():
        raise ReviewedArchiveError("archive symlink target is not relative")
    parts: list[str] = list(member.parent.parts)
    for part in link.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if len(parts) <= 1:
                raise ReviewedArchiveError("archive symlink escapes the closed root")
            parts.pop()
        else:
            parts.append(part)
    if not parts or parts[0] != root:
        raise ReviewedArchiveError("archive symlink escapes the closed root")


def _validate_members(
    members: list[tarfile.TarInfo], *, kind: str
) -> None:
    if not members or len(members) > _MAX_MEMBERS:
        raise ReviewedArchiveError("archive member count is outside the closed bound")
    expected_root = "node_modules" if kind == "playwright-runtime" else "company-public-h2"
    total = 0
    names: set[str] = set()
    h2_manifest = False
    h2_asset = False
    for member in members:
        path = _safe_member_path(member.name.rstrip("/"), root=expected_root)
        normalized = path.as_posix()
        if normalized in names:
            raise ReviewedArchiveError("archive contains a duplicate member")
        names.add(normalized)
        total += member.size
        if total > _MAX_EXPANDED_BYTES:
            raise ReviewedArchiveError("archive expanded size exceeds the closed bound")
        if member.islnk():
            raise ReviewedArchiveError("archive hard links are forbidden")
        if member.issym():
            if kind != "playwright-runtime":
                raise ReviewedArchiveError("H2 release archive may not contain symlinks")
            _safe_relative_link(path, member.linkname, root=expected_root)
        elif not (member.isfile() or member.isdir()):
            raise ReviewedArchiveError("archive contains a special member")
        if kind == "h2-release" and member.isfile():
            if normalized == "company-public-h2/public_h2_asset_manifest.json":
                h2_manifest = True
            elif normalized.startswith("company-public-h2/assets/"):
                h2_asset = True
            else:
                raise ReviewedArchiveError("H2 release archive contains an unknown file")
    if kind == "h2-release" and (not h2_manifest or not h2_asset):
        raise ReviewedArchiveError("H2 release archive graph is incomplete")


def extract_reviewed_archive(archive: Path, destination: Path, *, kind: str) -> Path:
    """Validate and extract into a new runner-owned directory."""

    if kind not in {"h2-release", "playwright-runtime"}:
        raise ValueError("unknown archive kind")
    if not archive.is_absolute() or not destination.is_absolute():
        raise ReviewedArchiveError("archive and destination must be absolute")
    archive_info = archive.lstat()
    if not stat.S_ISREG(archive_info.st_mode) or archive.is_symlink():
        raise ReviewedArchiveError("archive must be a plain file")
    if destination.exists():
        raise ReviewedArchiveError("archive destination must be new")
    destination.mkdir(parents=False)
    try:
        with tarfile.open(archive, mode="r:gz") as source:
            members = source.getmembers()
            _validate_members(members, kind=kind)
            source.extractall(destination, members=members, filter="data")
        expected = destination / (
            "node_modules" if kind == "playwright-runtime" else "company-public-h2"
        )
        if not expected.is_dir() or expected.is_symlink():
            raise ReviewedArchiveError("archive root was not extracted as a plain directory")
        return expected
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("h2-release", "playwright-runtime"), required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        root = extract_reviewed_archive(
            arguments.archive,
            arguments.destination,
            kind=arguments.kind,
        )
    except (OSError, tarfile.TarError, ReviewedArchiveError, ValueError) as exc:
        print(f"reviewed archive extraction failed: {exc}", file=os.sys.stderr)
        return 2
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
