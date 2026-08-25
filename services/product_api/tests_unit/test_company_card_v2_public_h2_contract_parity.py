"""Shared strict-H2 DTO mutation corpus for the Python/browser boundary."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from product_api.company_reports.company_card_v2.canonical_json import canonical_digest, canonical_json_bytes
from product_api.company_reports.company_card_v2.public_h2_models import (
    parse_public_h2_json,
)

_ROOT = Path(__file__).parents[3]
_FIXTURE = _ROOT / "shared" / "fixtures" / "company_public_h2_contract_v1.json"
_CASES = _ROOT / "shared" / "fixtures" / "company_public_h2_contract_v1_cases.json"
def _strict_json_value(raw: str) -> object:
    def reject_float(value: str) -> object:
        raise ValueError(f"float forbidden in mutation: {value}")

    def strict_integer(value: str) -> int:
        if re.fullmatch(r"(?:0|-?[1-9][0-9]*)", value) is None:
            raise ValueError(f"invalid integer mutation: {value}")
        return int(value)

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate mutation key: {key}")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_int=strict_integer,
        parse_float=reject_float,
        parse_constant=reject_float,
    )


def _payload() -> dict[str, object]:
    value = _strict_json_value(_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _at(payload: object, pointer: str) -> tuple[object, str | int]:
    if not pointer.startswith("/"):
        raise AssertionError(f"invalid JSON pointer: {pointer}")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]
    parent: object = payload
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]  # type: ignore[index]
    return parent, int(parts[-1]) if isinstance(parent, list) else parts[-1]


def _apply(payload: dict[str, object], mutation: dict[str, object]) -> None:
    op = mutation["op"]
    parent, key = _at(payload, str(mutation["path"]))
    if op == "replace":
        parent[key] = copy.deepcopy(_strict_json_value(str(mutation["raw"])))  # type: ignore[index]
    elif op == "add":
        value = copy.deepcopy(_strict_json_value(str(mutation["raw"])))
        if isinstance(parent, list):
            parent.insert(key, value)
        else:
            parent[key] = value  # type: ignore[index]
    elif op == "remove":
        del parent[key]  # type: ignore[index]
    elif op == "swap":
        other_parent, other_key = _at(payload, str(mutation["from"]))
        parent[key], other_parent[other_key] = other_parent[other_key], parent[key]  # type: ignore[index]
    else:
        raise AssertionError(f"unknown operation: {op}")


def _case_payload(case: dict[str, object]) -> dict[str, object]:
    payload = copy.deepcopy(_payload())
    for mutation in case["mutations"]:
        _apply(payload, mutation)
    if case["recompute_digest"]:
        payload["projection_digest"] = canonical_digest({
            key: value for key, value in payload.items() if key != "projection_digest"
        })
    return payload


def _validate(payload: dict[str, object]) -> None:
    parse_public_h2_json(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def test_public_h2_fixture_is_valid_at_the_closed_python_boundary() -> None:
    dto = parse_public_h2_json(_FIXTURE.read_bytes())
    assert dto.identity.inn == "7701234567"


def test_raw_wire_boundary_rejects_negative_zero_before_model_coercion() -> None:
    with pytest.raises(ValueError, match="invalid public H2 JSON"):
        parse_public_h2_json('{"n":-0}')


def test_canonical_path_must_bind_exact_identity_inn() -> None:
    payload = _payload()
    payload["canonical_path"] = "/company/5001000000-company"
    with pytest.raises(ValueError, match="canonical path does not bind identity INN"):
        _validate(payload)


@pytest.mark.parametrize(
    "raw",
    (
        b'{"contract_version":"company_public_h2_v1","contract_version":"company_public_h2_v1"}',
        b'{"number":1.5}',
        b'[]',
    ),
)
def test_raw_public_h2_boundary_rejects_duplicate_float_and_nonobject(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_public_h2_json(raw)


def test_full_canonical_projection_boundary_counts_projection_digest() -> None:
    seed = {"pad": "", "projection_digest": "0" * 64}
    padding = 524_288 - len(canonical_json_bytes(seed))
    exact = {"pad": "x" * padding, "projection_digest": "0" * 64}
    plus_one = {"pad": "x" * (padding + 1), "projection_digest": "0" * 64}
    assert len(canonical_json_bytes(exact)) == 524_288
    assert len(canonical_json_bytes(plus_one)) == 524_289


def test_dense_shared_corpus_has_closed_ids_and_python_outcomes() -> None:
    corpus = json.loads(_CASES.read_text(encoding="utf-8"))
    cases = corpus["cases"]
    constraint_ids = tuple(corpus["constraint_ids"])
    assert len(constraint_ids) >= 80
    assert len(set(constraint_ids)) == len(constraint_ids)
    assert tuple(case["id"] for case in cases) == constraint_ids
    for case in cases:
        payload = _case_payload(case)
        if case["expect"] == "accept":
            try:
                _validate(payload)
            except ValueError as exc:
                raise AssertionError(f"Python rejected shared accept case: {case['id']}") from exc
        else:
            try:
                _validate(payload)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Python accepted shared reject case: {case['id']}")
