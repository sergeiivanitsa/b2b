from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from product_api.company_reports.errors import (
    CompanyReportNormalizationError,
    DatasetMismatchError,
    InvalidDatasetPayloadError,
)
from product_api.company_reports.models import NormalizationWarning, SourceMetadata
from product_api.providers.datanewton import DataNewtonResult


def validate_result(
    result: DataNewtonResult,
    *,
    expected_dataset: str,
    expected_endpoint: str,
) -> dict[str, Any]:
    if result.provider != "datanewton":
        raise CompanyReportNormalizationError(
            "unsupported provider for company report normalization",
            dataset=result.dataset,
            endpoint=result.endpoint,
        )
    if result.dataset != expected_dataset or result.endpoint != expected_endpoint:
        raise DatasetMismatchError(
            expected_dataset=expected_dataset,
            actual_dataset=result.dataset,
            expected_endpoint=expected_endpoint,
            actual_endpoint=result.endpoint,
        )
    if not isinstance(result.raw_payload, dict):
        raise InvalidDatasetPayloadError(
            "dataset payload root must be an object",
            dataset=result.dataset,
            endpoint=result.endpoint,
        )
    return result.raw_payload


def warning(code: str, path: str, message: str) -> NormalizationWarning:
    return NormalizationWarning(code=code, path=path, message=message)


def source_metadata(
    result: DataNewtonResult,
    warnings: list[NormalizationWarning],
) -> SourceMetadata:
    provider_warnings = [
        warning("provider_warning", "$", message) for message in result.warnings
    ]
    return SourceMetadata(
        provider=result.provider,
        dataset=result.dataset,
        endpoint=result.endpoint,
        response_hash=result.response_hash,
        received_at=result.received_at,
        request_id=result.request_id,
        warnings=[*provider_warnings, *warnings],
    )


def optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def parse_date(
    value: object,
    *,
    path: str,
    warnings: list[NormalizationWarning],
) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            seconds = value / 1000 if abs(value) >= 10_000_000_000 else value
            return datetime.fromtimestamp(seconds, tz=timezone.utc).date()
        except (OSError, OverflowError, ValueError):
            pass
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            try:
                return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
            except ValueError:
                pass
    warnings.append(warning("date_parse_failed", path, "date value could not be parsed"))
    return None


def parse_temporal(
    value: object,
    *,
    path: str,
    warnings: list[NormalizationWarning],
) -> date | datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return date.fromisoformat(stripped)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
                return parsed
            except ValueError:
                pass
    warnings.append(warning("date_parse_failed", path, "date value could not be parsed"))
    return None


def parse_decimal(
    value: object,
    *,
    path: str,
    warnings: list[NormalizationWarning],
) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        warnings.append(
            warning("decimal_parse_failed", path, "numeric value could not be parsed")
        )
        return None
    try:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, float):
            return Decimal(str(value))
        if isinstance(value, (int, str)):
            return Decimal(value.strip() if isinstance(value, str) else value)
    except (InvalidOperation, ValueError):
        pass
    warnings.append(
        warning("decimal_parse_failed", path, "numeric value could not be parsed")
    )
    return None
