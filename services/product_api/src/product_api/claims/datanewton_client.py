from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import Any

import httpx

from product_api.settings import Settings

from .normalization import normalize_inn
from .preview_header_formatter import infer_kind_from_inn

logger = logging.getLogger(__name__)


class DataNewtonError(Exception):
    pass


class DataNewtonClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[str, tuple[float, dict[str, Any] | None]] = {}

    async def fetch_party_by_inn(self, inn: str) -> dict[str, Any] | None:
        normalized_inn = normalize_inn(inn, field_name="inn", strict=False)
        if not normalized_inn:
            return None

        cached = self._read_cache(normalized_inn)
        if cached is not None:
            return cached

        if not self._settings.datanewton_enabled:
            result = None
            self._write_cache(normalized_inn, result)
            return result

        if not self._settings.datanewton_api_key:
            logger.warning("datanewton_enabled_but_missing_api_key")
            result = None
            self._write_cache(normalized_inn, result)
            return result

        result = await self._request_counterparty(normalized_inn)
        self._write_cache(normalized_inn, result)
        return result

    async def _request_counterparty(self, inn: str) -> dict[str, Any] | None:
        retry_count = max(self._settings.datanewton_retry_count, 0)
        last_error: Exception | None = None
        for attempt in range(retry_count + 1):
            try:
                return await self._request_counterparty_once(inn)
            except DataNewtonError as exc:
                last_error = exc
                if attempt >= retry_count:
                    break
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt >= retry_count:
                    break
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= retry_count:
                    break
        if last_error is not None:
            logger.warning("datanewton_request_failed inn=%s err=%s", inn, str(last_error))
        return None

    async def _request_counterparty_once(self, inn: str) -> dict[str, Any] | None:
        timeout_seconds = max(self._settings.datanewton_timeout_seconds, 1)
        params = {
            "key": self._settings.datanewton_api_key or "",
            "inn": inn,
        }
        for path in _candidate_paths():
            url = _build_url(self._settings.datanewton_base_url, path)
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.get(url, params=params)
            if response.status_code in {404, 405}:
                continue
            if response.status_code == 429:
                raise DataNewtonError("rate_limited")
            if response.status_code >= 500:
                raise DataNewtonError(f"status_{response.status_code}")
            if response.status_code >= 400:
                logger.warning(
                    "datanewton_non_success_status status=%s inn=%s body=%s",
                    response.status_code,
                    inn,
                    response.text[:300],
                )
                return None

            payload = response.json()
            parsed = parse_datanewton_counterparty_payload(payload, fallback_inn=inn)
            if parsed is None:
                return None
            return parsed
        return None

    def _read_cache(self, inn: str) -> dict[str, Any] | None | None:
        ttl_seconds = self._settings.datanewton_cache_ttl_seconds
        if ttl_seconds <= 0:
            return None
        cached = self._cache.get(inn)
        if not cached:
            return None
        expires_at, payload = cached
        if expires_at <= time.time():
            self._cache.pop(inn, None)
            return None
        return payload

    def _write_cache(self, inn: str, payload: dict[str, Any] | None) -> None:
        ttl_seconds = self._settings.datanewton_cache_ttl_seconds
        if ttl_seconds <= 0:
            return
        self._cache[inn] = (time.time() + ttl_seconds, payload)


_client_singleton: DataNewtonClient | None = None


def get_datanewton_client(settings: Settings) -> DataNewtonClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = DataNewtonClient(settings)
    return _client_singleton


async def fetch_datanewton_party_by_inn(settings: Settings, inn: str) -> dict[str, Any] | None:
    client = get_datanewton_client(settings)
    return await client.fetch_party_by_inn(inn)


def parse_datanewton_counterparty_payload(
    payload: Any,
    *,
    fallback_inn: str | None = None,
) -> dict[str, Any] | None:
    record = _extract_primary_record(payload)
    if not isinstance(record, dict):
        return None

    subject_kind = _extract_subject_kind(record, fallback_inn=fallback_inn)
    company_name = _extract_company_name(record)
    manager_block = _extract_manager_block(record)
    individual_block = _extract_individual_block(record)
    person_name = _extract_person_name(
        manager_block=manager_block,
        individual_block=individual_block,
        record=record,
    )
    position_raw = _extract_position_raw(
        manager_block=manager_block,
        record=record,
    )
    address = _extract_address(record)

    return {
        "kind": subject_kind,
        "company_name": company_name,
        "position_raw": position_raw,
        "person_name": person_name,
        "address": address,
    }


def _candidate_paths() -> tuple[str, str]:
    return ("/v1/counterparty", "/api_ext/v1/counterparty")


def _build_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def _extract_primary_record(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        for key in ("data", "result", "counterparty", "item"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return nested
            if isinstance(nested, list):
                first = _first_dict(nested)
                if first is not None:
                    return first
        for key in ("rows", "items", "results", "suggestions", "list"):
            nested_list = payload.get(key)
            if isinstance(nested_list, list):
                first = _first_dict(nested_list)
                if first is not None:
                    return first
        return payload
    if isinstance(payload, list):
        return _first_dict(payload)
    return None


def _first_dict(values: Iterable[Any]) -> dict[str, Any] | None:
    for item in values:
        if isinstance(item, dict):
            return item
    return None


def _extract_subject_kind(record: dict[str, Any], *, fallback_inn: str | None) -> str:
    if _is_individual_entrepreneur(record):
        return "individual_entrepreneur"
    if _is_legal_entity(record):
        return "legal_entity"
    fallback = infer_kind_from_inn(fallback_inn)
    return fallback


def _is_individual_entrepreneur(record: dict[str, Any]) -> bool:
    individual_block = _extract_individual_block(record)
    if isinstance(individual_block, dict):
        return True
    kind_values = _collect_text_values(
        record,
        {
            "type",
            "subject_type",
            "subjectType",
            "entity_type",
            "entityType",
            "organization_type",
        },
    )
    for value in kind_values:
        lowered = value.lower()
        if "ип" in lowered or "индивидуал" in lowered:
            return True
    bool_flags = _collect_bool_values(
        record,
        {
            "is_ip",
            "isIp",
            "is_individual_entrepreneur",
            "isIndividualEntrepreneur",
        },
    )
    return any(bool_flags)


def _is_legal_entity(record: dict[str, Any]) -> bool:
    kind_values = _collect_text_values(
        record,
        {
            "type",
            "subject_type",
            "subjectType",
            "entity_type",
            "entityType",
            "organization_type",
        },
    )
    for value in kind_values:
        lowered = value.lower()
        if "юл" in lowered or "юр" in lowered or "legal" in lowered:
            return True
    bool_flags = _collect_bool_values(
        record,
        {
            "is_organization",
            "isOrganization",
            "is_legal_entity",
            "isLegalEntity",
        },
    )
    return any(bool_flags)


def _extract_company_name(record: dict[str, Any]) -> str | None:
    name = _find_first_text(
        record,
        {
            "short_name",
            "shortName",
            "full_name",
            "fullName",
            "company_name",
            "companyName",
            "name",
            "title",
        },
    )
    if name:
        return name
    company_block = _find_first_dict(
        record,
        {
            "organization",
            "company",
            "legal",
            "counterparty",
        },
    )
    if company_block:
        return _find_first_text(
            company_block,
            {
                "short_name",
                "shortName",
                "full_name",
                "fullName",
                "name",
                "title",
            },
        )
    return None


def _extract_manager_block(record: dict[str, Any]) -> dict[str, Any] | None:
    return _find_first_dict(
        record,
        {
            "manager",
            "head",
            "director",
            "ceo",
            "manager_block",
            "managerBlock",
        },
    )


def _extract_individual_block(record: dict[str, Any]) -> dict[str, Any] | None:
    return _find_first_dict(
        record,
        {
            "individual",
            "ip",
            "entrepreneur",
            "individual_block",
            "individualBlock",
        },
    )


def _extract_person_name(
    *,
    manager_block: dict[str, Any] | None,
    individual_block: dict[str, Any] | None,
    record: dict[str, Any],
) -> str | None:
    if manager_block:
        name = _find_first_text(
            manager_block,
            {
                "fio",
                "name",
                "full_name",
                "fullName",
                "manager_name",
                "managerName",
                "director_name",
                "directorName",
            },
        )
        if name:
            return name
    if individual_block:
        name = _find_first_text(
            individual_block,
            {
                "fio",
                "name",
                "full_name",
                "fullName",
                "person_name",
                "personName",
            },
        )
        if name:
            return name
    return _find_first_text(
        record,
        {
            "manager_fio",
            "managerFio",
            "director_fio",
            "directorFio",
            "fio",
            "person_name",
            "personName",
        },
    )


def _extract_position_raw(
    *,
    manager_block: dict[str, Any] | None,
    record: dict[str, Any],
) -> str | None:
    if manager_block:
        position = _find_first_text(
            manager_block,
            {
                "position",
                "post",
                "title",
                "manager_position",
                "managerPosition",
                "director_position",
                "directorPosition",
            },
        )
        if position:
            return position
    return _find_first_text(
        record,
        {
            "manager_position",
            "managerPosition",
            "director_position",
            "directorPosition",
            "position",
            "post",
            "title",
        },
    )


def _extract_address(record: dict[str, Any]) -> str | None:
    return _find_first_text(
        record,
        {
            "address",
            "full_address",
            "fullAddress",
            "legal_address",
            "legalAddress",
            "registration_address",
            "registrationAddress",
        },
    )


def _find_first_dict(payload: Any, candidate_keys: set[str]) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in candidate_keys and isinstance(value, dict):
                return value
            nested = _find_first_dict(value, candidate_keys)
            if nested is not None:
                return nested
        return None
    if isinstance(payload, list):
        for item in payload:
            nested = _find_first_dict(item, candidate_keys)
            if nested is not None:
                return nested
    return None


def _find_first_text(payload: Any, candidate_keys: set[str]) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in candidate_keys:
                normalized = _normalize_text(value)
                if normalized:
                    return normalized
            nested = _find_first_text(value, candidate_keys)
            if nested:
                return nested
        return None
    if isinstance(payload, list):
        for item in payload:
            nested = _find_first_text(item, candidate_keys)
            if nested:
                return nested
    return None


def _collect_text_values(payload: Any, candidate_keys: set[str]) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in candidate_keys:
                normalized = _normalize_text(value)
                if normalized:
                    values.append(normalized)
            values.extend(_collect_text_values(value, candidate_keys))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_collect_text_values(item, candidate_keys))
    return values


def _collect_bool_values(payload: Any, candidate_keys: set[str]) -> list[bool]:
    values: list[bool] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in candidate_keys and isinstance(value, bool):
                values.append(value)
            values.extend(_collect_bool_values(value, candidate_keys))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_collect_bool_values(item, candidate_keys))
    return values


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    normalized = value.strip()
    return normalized or None
