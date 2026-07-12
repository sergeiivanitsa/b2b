from __future__ import annotations

import json
from typing import Any

DEFAULT_MAX_DEPTH = 20
DEFAULT_MAX_UNIQUE_ITEM_SHAPES = 20


def build_json_shape(
    value: Any,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_unique_item_shapes: int = DEFAULT_MAX_UNIQUE_ITEM_SHAPES,
) -> dict[str, Any]:
    """Return a deterministic JSON structure map without scalar values."""
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    if max_unique_item_shapes < 1:
        raise ValueError("max_unique_item_shapes must be positive")

    builder = _ShapeBuilder(
        max_depth=max_depth,
        max_unique_item_shapes=max_unique_item_shapes,
    )
    shape = builder.visit(value, depth=0)
    if isinstance(value, dict):
        shape["top_level_keys"] = sorted(str(key) for key in value)
    else:
        shape["top_level_keys"] = []
    shape["approximate_node_count"] = builder.node_count
    shape["max_depth_reached"] = builder.max_depth_reached
    shape["warnings"] = sorted(builder.warnings)
    return shape


class _ShapeBuilder:
    def __init__(self, *, max_depth: int, max_unique_item_shapes: int) -> None:
        self.max_depth = max_depth
        self.max_unique_item_shapes = max_unique_item_shapes
        self.node_count = 0
        self.max_depth_reached = 0
        self.warnings: set[str] = set()

    def visit(self, value: Any, *, depth: int) -> dict[str, Any]:
        self.node_count += 1
        self.max_depth_reached = max(self.max_depth_reached, depth)

        if value is None:
            return {"type": "null"}
        if isinstance(value, bool):
            return {"type": "boolean"}
        if isinstance(value, int):
            return {"type": "integer"}
        if isinstance(value, float):
            return {"type": "number"}
        if isinstance(value, str):
            return {"type": "string"}
        if isinstance(value, dict):
            return self._visit_object(value, depth=depth)
        if isinstance(value, list):
            return self._visit_array(value, depth=depth)
        raise TypeError(f"unsupported JSON value type: {type(value).__name__}")

    def _visit_object(self, value: dict[Any, Any], *, depth: int) -> dict[str, Any]:
        if value and depth >= self.max_depth:
            self.warnings.add("maximum JSON shape depth reached")
            return {"type": "object", "truncated": True}
        keys = {
            str(key): self.visit(item, depth=depth + 1)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
        return {"type": "object", "keys": keys}

    def _visit_array(self, value: list[Any], *, depth: int) -> dict[str, Any]:
        shape: dict[str, Any] = {"type": "array", "length": len(value)}
        if value and depth >= self.max_depth:
            self.warnings.add("maximum JSON shape depth reached")
            shape["truncated"] = True
            shape["item_shapes"] = []
            return shape

        shape_groups: dict[str, list[dict[str, Any]]] = {}
        for item in value:
            item_shape = self.visit(item, depth=depth + 1)
            fingerprint = _structural_fingerprint(item_shape)
            shape_groups.setdefault(fingerprint, []).append(item_shape)

        sorted_shapes = [
            _merge_structurally_equal_shapes(shape_groups[key])
            for key in sorted(shape_groups)
        ]
        if len(sorted_shapes) > self.max_unique_item_shapes:
            self.warnings.add("unique array item shape limit reached")
            shape["truncated"] = True
            sorted_shapes = sorted_shapes[: self.max_unique_item_shapes]
        shape["item_shapes"] = sorted_shapes
        return shape


def _structural_fingerprint(shape: dict[str, Any]) -> str:
    return json.dumps(
        _structural_projection(shape),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _structural_projection(value: Any) -> Any:
    if isinstance(value, dict):
        ignored_keys = (
            {"length", "observed_lengths"}
            if value.get("type") == "array"
            else set()
        )
        return {
            key: _structural_projection(item)
            for key, item in sorted(value.items())
            if key not in ignored_keys
        }
    if isinstance(value, list):
        return [_structural_projection(item) for item in value]
    return value


def _merge_structurally_equal_shapes(
    shapes: list[dict[str, Any]],
) -> dict[str, Any]:
    first = shapes[0]
    shape_type = first["type"]
    if shape_type == "object" and "keys" in first:
        return {
            "type": "object",
            "keys": {
                key: _merge_structurally_equal_shapes(
                    [shape["keys"][key] for shape in shapes]
                )
                for key in sorted(first["keys"])
            },
        }
    if shape_type == "array":
        lengths = sorted(
            {
                observed
                for shape in shapes
                for observed in shape.get("observed_lengths", [shape.get("length", 0)])
            }
        )
        item_shape_groups: dict[str, list[dict[str, Any]]] = {}
        for shape in shapes:
            for item_shape in shape.get("item_shapes", []):
                fingerprint = _structural_fingerprint(item_shape)
                item_shape_groups.setdefault(fingerprint, []).append(item_shape)
        merged: dict[str, Any] = {
            "type": "array",
            "length": max(lengths, default=0),
            "item_shapes": [
                _merge_structurally_equal_shapes(item_shape_groups[key])
                for key in sorted(item_shape_groups)
            ],
        }
        if len(lengths) > 1:
            merged["observed_lengths"] = lengths
        if any(shape.get("truncated") is True for shape in shapes):
            merged["truncated"] = True
        return merged
    return dict(first)
