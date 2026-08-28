"""Strict, dependency-free validation for pytest JUnit evidence."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import xml.etree.ElementTree as ET


class JUnitEvidenceError(RuntimeError):
    """Raised when a test phase did not leave trustworthy JUnit evidence."""


@dataclass(frozen=True, slots=True)
class JUnitSummary:
    phase: str
    tests: int
    failures: int
    errors: int
    skipped: int
    path: Path


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def validate_junit_evidence(
    path: str | os.PathLike[str],
    *,
    phase: str,
    not_before_ns: int,
) -> JUnitSummary:
    """Validate one newly-created, nonempty and completely clean JUnit file.

    ``not_before_ns`` is captured immediately before the owning pytest phase.
    It prevents a successful exit or a missing output from accidentally
    accepting stale evidence left by an earlier run.
    """

    evidence_path = Path(path)
    if type(not_before_ns) is not int or not_before_ns < 0:
        raise ValueError("not_before_ns must be a non-negative integer")
    if not phase or any(character in phase for character in "\r\n\x00"):
        raise ValueError("phase must be a nonempty single-line value")

    try:
        metadata = evidence_path.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise JUnitEvidenceError(f"{phase}: JUnit evidence is missing") from exc
    except OSError as exc:
        raise JUnitEvidenceError(f"{phase}: JUnit evidence cannot be inspected") from exc

    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise JUnitEvidenceError(f"{phase}: JUnit evidence is not a plain file")
    if metadata.st_mtime_ns < not_before_ns:
        raise JUnitEvidenceError(f"{phase}: JUnit evidence is stale")
    if metadata.st_size <= 0:
        raise JUnitEvidenceError(f"{phase}: JUnit evidence is empty")

    tests = failures = errors = skipped = 0
    try:
        for _event, element in ET.iterparse(evidence_path, events=("end",)):
            name = _local_name(element.tag)
            if name == "testcase":
                tests += 1
            elif name == "failure":
                failures += 1
            elif name == "error":
                errors += 1
            elif name == "skipped":
                skipped += 1
            element.clear()
    except (ET.ParseError, OSError, UnicodeError) as exc:
        raise JUnitEvidenceError(f"{phase}: JUnit evidence is malformed") from exc

    if tests == 0:
        raise JUnitEvidenceError(f"{phase}: JUnit evidence contains zero tests")
    if failures or errors or skipped:
        raise JUnitEvidenceError(
            f"{phase}: JUnit evidence is not clean: "
            f"tests={tests} failures={failures} errors={errors} skipped={skipped}"
        )
    return JUnitSummary(
        phase=phase,
        tests=tests,
        failures=failures,
        errors=errors,
        skipped=skipped,
        path=evidence_path.resolve(),
    )
