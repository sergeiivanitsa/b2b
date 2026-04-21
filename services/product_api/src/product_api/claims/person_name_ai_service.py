from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, replace
from typing import Literal

import httpx

from product_api.gateway_client import GatewayError, send_chat
from product_api.settings import Settings
from shared.schemas import ChatMetadata, ChatRequest

from .person_name_ai_prompts import (
    EntityKind,
    TargetCase,
    build_person_name_ai_messages,
)

PersonNameAIStatus = Literal["ok", "empty_input", "invalid_response", "gateway_error", "timeout"]

_ALLOWED_FIO_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁё'.’\-]+(?: [A-Za-zА-Яа-яЁё'.’\-]+)*$")
_MIN_FIO_LENGTH = 2
_MAX_FIO_LENGTH = 120
_CACHE_NAMESPACE = "person_name_ai_v1"
_IP_PREFIXES = (
    "ип ",
    "ип. ",
    "индивидуальный предприниматель ",
    "индивидуального предпринимателя ",
    "индивидуальному предпринимателю ",
)


@dataclass(frozen=True, slots=True)
class PersonNameAIResult:
    status: PersonNameAIStatus
    fio: str | None
    preprocessed_fio: str | None
    error_code: str | None
    cache_hit: bool


_cache: dict[str, tuple[float, PersonNameAIResult]] = {}


def clear_person_name_ai_cache() -> None:
    _cache.clear()


async def transform_person_name_with_ai(
    settings: Settings,
    *,
    raw_fio: str | None,
    target_case: TargetCase,
    entity_kind: EntityKind,
    strip_ip_prefix: bool,
) -> PersonNameAIResult:
    normalized_input_fio = _normalize_fio(raw_fio)
    if normalized_input_fio is None:
        return PersonNameAIResult(
            status="empty_input",
            fio=None,
            preprocessed_fio=None,
            error_code=None,
            cache_hit=False,
        )

    preprocessed_fio = _preprocess_fio(
        normalized_input_fio,
        strip_ip_prefix=strip_ip_prefix,
    )
    if preprocessed_fio is None:
        return PersonNameAIResult(
            status="empty_input",
            fio=None,
            preprocessed_fio=None,
            error_code=None,
            cache_hit=False,
        )

    prompt_version = settings.claims_fio_ai_prompt_version
    cache_key = _build_cache_key(
        raw_fio=normalized_input_fio,
        target_case=target_case,
        entity_kind=entity_kind,
        strip_ip_prefix=strip_ip_prefix,
        model=settings.claims_fio_ai_model,
        prompt_version=prompt_version,
    )

    cached_result = _read_cache(cache_key)
    if cached_result is not None:
        return replace(cached_result, cache_hit=True)

    input_token_count = len(preprocessed_fio.split(" "))

    try:
        raw_response = await _request_person_name_transform(
            settings,
            fio=preprocessed_fio,
            target_case=target_case,
            entity_kind=entity_kind,
            strip_ip_prefix=strip_ip_prefix,
            prompt_version=prompt_version,
        )
    except httpx.TimeoutException:
        timeout_result = PersonNameAIResult(
            status="timeout",
            fio=None,
            preprocessed_fio=preprocessed_fio,
            error_code="timeout",
            cache_hit=False,
        )
        _write_negative_cache(settings, cache_key, timeout_result)
        return timeout_result
    except (GatewayError, httpx.HTTPError):
        gateway_error_result = PersonNameAIResult(
            status="gateway_error",
            fio=None,
            preprocessed_fio=preprocessed_fio,
            error_code="gateway_error",
            cache_hit=False,
        )
        _write_negative_cache(settings, cache_key, gateway_error_result)
        return gateway_error_result

    try:
        transformed_fio = _parse_and_validate_ai_response(
            raw_response,
            input_token_count=input_token_count,
        )
    except ValueError:
        invalid_result = PersonNameAIResult(
            status="invalid_response",
            fio=None,
            preprocessed_fio=preprocessed_fio,
            error_code="invalid_response",
            cache_hit=False,
        )
        _write_negative_cache(settings, cache_key, invalid_result)
        return invalid_result

    success_result = PersonNameAIResult(
        status="ok",
        fio=transformed_fio,
        preprocessed_fio=preprocessed_fio,
        error_code=None,
        cache_hit=False,
    )
    _write_positive_cache(settings, cache_key, success_result)
    return success_result


def _normalize_fio(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    return normalized or None


def _preprocess_fio(value: str, *, strip_ip_prefix: bool) -> str | None:
    normalized = value
    if strip_ip_prefix:
        normalized = _strip_ip_prefix_from_start(normalized)
    normalized = " ".join(normalized.strip().split())
    return normalized or None


def _strip_ip_prefix_from_start(value: str) -> str:
    lowered = value.lower()
    for prefix in _IP_PREFIXES:
        if lowered.startswith(prefix):
            return value[len(prefix) :].strip()
    return value


def _build_cache_key(
    *,
    raw_fio: str,
    target_case: TargetCase,
    entity_kind: EntityKind,
    strip_ip_prefix: bool,
    model: str,
    prompt_version: str,
) -> str:
    key_material = (
        f"{_CACHE_NAMESPACE}|{raw_fio}|{target_case}|{entity_kind}|"
        f"{int(strip_ip_prefix)}|{model}|{prompt_version}"
    )
    return hashlib.sha256(key_material.encode("utf-8")).hexdigest()


def _read_cache(cache_key: str) -> PersonNameAIResult | None:
    cached = _cache.get(cache_key)
    if cached is None:
        return None
    expires_at, value = cached
    if expires_at <= time.time():
        _cache.pop(cache_key, None)
        return None
    return value


def _write_positive_cache(settings: Settings, cache_key: str, result: PersonNameAIResult) -> None:
    ttl_seconds = settings.claims_fio_ai_cache_ttl_seconds
    if ttl_seconds <= 0:
        return
    _cache[cache_key] = (time.time() + ttl_seconds, result)


def _write_negative_cache(settings: Settings, cache_key: str, result: PersonNameAIResult) -> None:
    ttl_seconds = settings.claims_fio_ai_negative_cache_ttl_seconds
    if ttl_seconds <= 0:
        return
    _cache[cache_key] = (time.time() + ttl_seconds, result)


async def _request_person_name_transform(
    settings: Settings,
    *,
    fio: str,
    target_case: TargetCase,
    entity_kind: EntityKind,
    strip_ip_prefix: bool,
    prompt_version: str,
) -> str:
    messages = build_person_name_ai_messages(
        fio=fio,
        target_case=target_case,
        entity_kind=entity_kind,
        strip_ip_prefix=strip_ip_prefix,
        prompt_version=prompt_version,
    )
    payload = ChatRequest(
        messages=messages,
        model=settings.claims_fio_ai_model,
        stream=False,
        timeout=settings.claims_fio_ai_timeout_seconds,
        metadata=ChatMetadata(
            company_id=0,
            user_id=0,
            conversation_id=0,
            message_id=0,
        ),
    )
    response = await send_chat(settings, payload)
    return response.text


def _parse_and_validate_ai_response(raw_response: str, *, input_token_count: int) -> str:
    payload = json.loads(raw_response.strip())
    if not isinstance(payload, dict):
        raise ValueError("ai payload must be a json object")
    if set(payload.keys()) != {"fio"}:
        raise ValueError("ai payload keys mismatch")
    fio_value = payload.get("fio")
    if not isinstance(fio_value, str):
        raise ValueError("fio must be a string")
    if "\n" in fio_value or "\r" in fio_value:
        raise ValueError("fio must be single-line")
    normalized_fio = " ".join(fio_value.strip().split())
    if not normalized_fio:
        raise ValueError("fio must not be empty")
    if len(normalized_fio) < _MIN_FIO_LENGTH or len(normalized_fio) > _MAX_FIO_LENGTH:
        raise ValueError("fio length is out of bounds")
    if not _ALLOWED_FIO_PATTERN.fullmatch(normalized_fio):
        raise ValueError("fio contains unsupported symbols")
    output_token_count = len(normalized_fio.split(" "))
    if output_token_count != input_token_count:
        raise ValueError("fio token count mismatch")
    return normalized_fio

