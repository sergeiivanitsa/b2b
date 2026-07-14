from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import TypeVar

from pydantic import BaseModel


_T = TypeVar("_T")


def canonical_representation(value: BaseModel | object) -> str:
    """Return the single canonical JSON representation used by signals."""

    dumped = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        dumped,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def stable_sorted(
    values: Iterable[_T],
    *,
    primary_key: Callable[[_T], object] | None = None,
) -> list[_T]:
    key = primary_key or (lambda _value: ())
    return sorted(values, key=lambda value: (key(value), canonical_representation(value)))


def stable_unique_sorted(
    values: Iterable[_T],
    *,
    primary_key: Callable[[_T], object] | None = None,
) -> list[_T]:
    ordered = stable_sorted(values, primary_key=primary_key)
    unique: list[_T] = []
    seen: set[str] = set()
    for value in ordered:
        canonical = canonical_representation(value)
        if canonical not in seen:
            seen.add(canonical)
            unique.append(value)
    return unique
