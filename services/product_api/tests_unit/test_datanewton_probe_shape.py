import json

import pytest

from product_api.tools.json_shape import build_json_shape


def test_object_shape_sorts_keys_and_removes_values():
    shape = build_json_shape(
        {
            "company": {
                "name": "ООО Секрет",
                "active": True,
                "employees": 15,
            },
            "amount": 10.5,
        }
    )

    assert shape["type"] == "object"
    assert list(shape["keys"]) == ["amount", "company"]
    assert shape["keys"]["company"] == {
        "type": "object",
        "keys": {
            "active": {"type": "boolean"},
            "employees": {"type": "integer"},
            "name": {"type": "string"},
        },
    }
    assert shape["keys"]["amount"] == {"type": "number"}
    assert shape["top_level_keys"] == ["amount", "company"]
    assert "ООО Секрет" not in json.dumps(shape, ensure_ascii=False)


def test_array_shape_merges_identical_item_shapes():
    shape = build_json_shape(
        [
            {"number": "A00-1", "sum": 1000},
            {"number": "A00-2", "sum": 2000},
        ]
    )

    assert shape["type"] == "array"
    assert shape["length"] == 2
    assert shape["item_shapes"] == [
        {
            "type": "object",
            "keys": {
                "number": {"type": "string"},
                "sum": {"type": "integer"},
            },
        }
    ]


def test_empty_object_and_array_shapes():
    assert build_json_shape({})["keys"] == {}
    empty_array = build_json_shape([])
    assert empty_array["length"] == 0
    assert empty_array["item_shapes"] == []


@pytest.mark.parametrize(
    ("value", "expected_type"),
    [
        (None, "null"),
        (True, "boolean"),
        (17, "integer"),
        (17.5, "number"),
        ("secret scalar", "string"),
    ],
)
def test_scalar_types(value, expected_type):
    shape = build_json_shape(value)

    assert shape["type"] == expected_type
    assert value != "secret scalar" or "secret scalar" not in json.dumps(shape)


def test_different_array_shapes_are_sorted_and_limited():
    value = ["secret", 10, True, None, {"field": "value"}]
    shape = build_json_shape(value, max_unique_item_shapes=3)

    assert len(shape["item_shapes"]) == 3
    assert shape["truncated"] is True
    assert "unique array item shape limit reached" in shape["warnings"]


def test_depth_limit_marks_shape_as_truncated():
    shape = build_json_shape(
        {"level1": {"level2": {"level3": "hidden"}}},
        max_depth=1,
    )

    nested = shape["keys"]["level1"]
    assert nested == {"type": "object", "truncated": True}
    assert "maximum JSON shape depth reached" in shape["warnings"]
    assert "hidden" not in json.dumps(shape)


def test_shape_is_deterministic_for_equivalent_object_order():
    first = build_json_shape({"z": [1, "a"], "a": {"b": False}})
    second = build_json_shape({"a": {"b": True}, "z": ["b", 2]})

    assert first == second


def test_serialized_shape_contains_no_original_scalar_values():
    shape = build_json_shape(
        {
            "text": "UNIQUE_PRIVATE_VALUE_9f7a",
            "number": 987654321,
            "nested": ["SECOND_PRIVATE_VALUE_3c1d"],
        }
    )
    serialized = json.dumps(shape, ensure_ascii=False, sort_keys=True)

    assert "UNIQUE_PRIVATE_VALUE_9f7a" not in serialized
    assert "SECOND_PRIVATE_VALUE_3c1d" not in serialized
    assert "987654321" not in serialized

