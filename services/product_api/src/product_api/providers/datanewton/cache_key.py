from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .models import BatchCardsRequest

CACHE_KEY_SCHEMA_VERSION = "v1"
_SECRET_QUERY_NAMES = {"key", "api_key", "apikey"}


def build_cache_key(
    *,
    provider: str,
    dataset: str,
    base_url: str,
    method: str,
    endpoint: str,
    query_params: Mapping[str, str | int | float | bool | Sequence[str]] | None = None,
    body: Mapping[str, Any] | None = None,
    schema_version: str = CACHE_KEY_SCHEMA_VERSION,
) -> str:
    """Build a stable key without retaining secret query parameters."""
    normalized_provider = provider.strip().lower()
    normalized_dataset = dataset.strip().lower()
    normalized_request = {
        "schema_version": schema_version,
        "provider": normalized_provider,
        "dataset": normalized_dataset,
        "base_url": base_url.strip().rstrip("/"),
        "method": method.strip().upper(),
        "endpoint": _normalize_endpoint(endpoint),
        "query_params": _normalize_query_params(query_params or {}),
        "body": _normalize_body(body or {}),
    }
    canonical_request = json.dumps(
        normalized_request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical_request).hexdigest()
    return f"{normalized_provider}:{normalized_dataset}:{schema_version}:{digest}"


def build_datanewton_cache_key(
    *,
    dataset: str,
    base_url: str,
    method: str,
    endpoint: str,
    query_params: Mapping[str, str | int | float | bool | Sequence[str]] | None = None,
    body: Mapping[str, Any] | None = None,
) -> str:
    return build_cache_key(
        provider="datanewton",
        dataset=dataset,
        base_url=base_url,
        method=method,
        endpoint=endpoint,
        query_params=query_params,
        body=body,
    )


def _normalize_endpoint(endpoint: str) -> str:
    normalized = endpoint.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def _normalize_query_params(
    query_params: Mapping[str, str | int | float | bool | Sequence[str]],
) -> list[tuple[str, str]]:
    normalized: list[tuple[str, str]] = []
    for name, value in query_params.items():
        normalized_name = str(name).strip().lower()
        if normalized_name in _SECRET_QUERY_NAMES:
            continue
        if isinstance(value, Sequence) and not isinstance(value, str):
            normalized.extend((normalized_name, str(item).strip()) for item in value)
        else:
            normalized.append((normalized_name, str(value).strip()))
    return sorted(normalized)


def _normalize_body(body: Mapping[str, Any]) -> dict[str, Any]:
    if "source_inns_or_ogrns" not in body:
        return dict(body)
    request = BatchCardsRequest.model_validate(dict(body))
    return request.model_dump(mode="json")

