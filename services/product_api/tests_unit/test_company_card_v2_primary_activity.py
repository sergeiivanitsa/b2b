from __future__ import annotations

import pytest

from product_api.company_reports.company_card_v2.canonical_json import canonical_json_bytes
from product_api.company_reports.company_card_v2.primary_activity import parse_primary_activity


INN = "7736207543"


def _row(
    code: object = "62.01",
    value: object = "Разработка программного обеспечения",
    main: object = True,
    mode: object = "new",
) -> dict[str, object]:
    return {"code": code, "value": value, "main": main, "mode": mode}


def _payload(rows: list[object]) -> dict[str, object]:
    return {"company": {"okveds": rows}}


def _parse(rows: list[object], **overrides: object):
    arguments = {
        "expected_inn": INN,
        "target_inn": INN,
        "requested_okved_block": True,
        "dataset_success": True,
    }
    arguments.update(overrides)
    return parse_primary_activity(_payload(rows), **arguments)


def _additional_row_with_exact_cjson_size(size: int) -> dict[str, object]:
    row = _row(code="10.1", value="", main=False, mode="legacy")
    overhead = len(canonical_json_bytes(row))
    row["value"] = "x" * (size - overhead)
    assert len(canonical_json_bytes(row)) == size
    return row


def _block_with_exact_cjson_size(size: int) -> list[dict[str, object]]:
    rows = [_row(value="p")]
    rows.extend(_additional_row_with_exact_cjson_size(2048) for _ in range(31))
    final_size = size - len(canonical_json_bytes(rows)) - 1
    rows.append(_additional_row_with_exact_cjson_size(final_size))
    assert len(canonical_json_bytes(rows)) == size
    return rows


def test_primary_activity_admits_only_exact_observed_shape() -> None:
    admitted = _parse([_row()])

    assert admitted is not None
    assert admitted.code == "62.01"
    assert admitted.label == "Разработка программного обеспечения"
    assert admitted.is_primary is True


@pytest.mark.parametrize("count", [1, 45, 100])
def test_row_count_boundaries_and_observed_45_row_duplicate_cohort_are_admitted(count: int) -> None:
    rows = [_row()]
    rows.extend(
        _row(
            code=f"{10 + (index % 43):02d}.1",
            value=f"Дополнительная деятельность {index % 43}",
            main=False,
            mode="legacy",
        )
        for index in range(count - 1)
    )

    assert _parse(rows) is not None


@pytest.mark.parametrize("count", [0, 101])
def test_row_count_outside_closed_1_to_100_boundary_is_rejected(count: int) -> None:
    rows = [_row()]
    rows.extend(_row(code="10.1", value="Дополнительная", main=False, mode="legacy") for _ in range(max(count - 1, 0)))
    if count == 0:
        rows = []

    assert len(rows) == count
    assert _parse(rows) is None


def test_exact_row_and_aggregate_byte_boundaries() -> None:
    primary = _row(value="p")
    assert _parse([primary, _additional_row_with_exact_cjson_size(2048)]) is not None
    assert _parse([primary, _additional_row_with_exact_cjson_size(2049)]) is None

    assert _parse(_block_with_exact_cjson_size(65536)) is not None
    assert _parse(_block_with_exact_cjson_size(65537)) is None


@pytest.mark.parametrize(
    "label, admitted",
    [("x", True), ("😀" * 128, True), ("x" * 129, False)],
)
def test_selected_label_scalar_and_utf8_boundaries(label: str, admitted: bool) -> None:
    assert (_parse([_row(value=label)]) is not None) is admitted


@pytest.mark.parametrize(
    "rows",
    [
        [_row(main=False)],
        [_row(), _row(code="63.1", value="Вторая основная", main=True)],
        [_row(mode="old")],
        [_row(main="true")],
        [_row(code=6201)],
        [_row(mode=1)],
        [{**_row(), "percentage": 100}],
        [_row(code="6")],
        [_row(code="62..1")],
        [_row(value="bad\x00label")],
    ],
)
def test_strict_shape_types_code_grammar_and_two_primary_are_fail_closed(rows: list[object]) -> None:
    assert _parse(rows) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_inn": "7701234567"},
        {"target_inn": None},
        {"requested_okved_block": False},
        {"dataset_success": False},
    ],
)
def test_exact_target_request_and_success_binding_is_required(overrides: dict[str, object]) -> None:
    assert _parse([_row()], **overrides) is None


def test_identical_selected_duplicate_is_allowed_but_conflicts_are_rejected() -> None:
    primary = _row()
    assert _parse([primary, _row(main=False)]) is not None
    assert _parse([primary, _row(value="Другая деятельность", main=False)]) is None
    assert _parse([primary, _row(main=False, mode="legacy")]) is None
    assert _parse([primary, _row(code="63.11", main=False)]) is None


def test_conflicts_exclusively_between_additional_rows_do_not_affect_selected_activity() -> None:
    rows = [
        _row(),
        _row(code="10.1", value="Дополнительная", main=False, mode="legacy"),
        _row(code="10.1", value="Конфликт между дополнительными", main=False, mode="other"),
    ]

    admitted = _parse(rows)
    assert admitted is not None
    assert admitted.code == "62.01"


def test_normalization_is_deterministic_and_only_selected_row_is_returned() -> None:
    admitted = _parse(
        [
            _row(value="  Разработка\r\n  программного  обеспечения  "),
            _row(code="10.1", value="Никогда не сохранять", main=False, mode="legacy"),
        ]
    )

    assert admitted is not None
    assert admitted.label == "Разработка программного обеспечения"
    assert not hasattr(admitted, "additional_activities")
    assert set(admitted.__dict__) == {"code", "label", "is_primary"}
