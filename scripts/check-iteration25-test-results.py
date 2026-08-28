"""Fail-closed CLI for one iteration-25 pytest JUnit phase."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests_support.junit_guard import JUnitEvidenceError, validate_junit_evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True)
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--not-before-ns", required=True, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        summary = validate_junit_evidence(
            arguments.junit,
            phase=arguments.phase,
            not_before_ns=arguments.not_before_ns,
        )
    except (JUnitEvidenceError, ValueError) as exc:
        print(f"JUnit validation failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "errors": summary.errors,
                "failures": summary.failures,
                "phase": summary.phase,
                "skipped": summary.skipped,
                "tests": summary.tests,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
