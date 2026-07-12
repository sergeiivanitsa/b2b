from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from product_api.providers.datanewton import DataNewtonResult, calculate_response_hash

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "datanewton"


def load_fixture(name: str) -> dict[str, Any]:
    payload = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    return deepcopy(payload)


def build_result(
    *,
    dataset: str,
    endpoint: str,
    payload: dict[str, Any],
    request_parameters: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> DataNewtonResult:
    return DataNewtonResult(
        dataset=dataset,
        endpoint=endpoint,
        requested_identifier="0000000000",
        request_parameters=request_parameters or {},
        status_code=200,
        attempts=1,
        duration_ms=1,
        request_id="synthetic-request",
        received_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        raw_payload=payload,
        response_hash=calculate_response_hash(payload),
        warnings=warnings or [],
    )


def counterparty_result(
    *,
    payload: dict[str, Any] | None = None,
    filters: str = "ADDRESS_BLOCK,MANAGER_BLOCK,OWNER_BLOCK,OKVED_BLOCK,WORKERS_COUNT_BLOCK",
) -> DataNewtonResult:
    return build_result(
        dataset="counterparty",
        endpoint="/v1/counterparty",
        payload=payload or load_fixture("counterparty_success.json"),
        request_parameters={"inn": "0000000000", "filters": filters},
    )


def finance_result(payload: dict[str, Any] | None = None) -> DataNewtonResult:
    return build_result(
        dataset="finance",
        endpoint="/v1/finance",
        payload=payload or load_fixture("finance_success.json"),
        request_parameters={"inn": "0000000000"},
    )


def arbitration_result(payload: dict[str, Any] | None = None) -> DataNewtonResult:
    return build_result(
        dataset="arbitration_cases",
        endpoint="/v1/arbitration-cases",
        payload=payload or load_fixture("arbitration_success.json"),
        request_parameters={"inn": "0000000000", "offset": 0, "limit": 5},
    )
