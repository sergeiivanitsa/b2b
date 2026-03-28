import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from product_api.auth import utcnow

from .extraction import CASE_TYPE_ALIASES, DOCUMENT_ALIASES, build_empty_normalized_data, build_missing_fields

SUPPORTED_CASE_TYPES = {"supply", "contract_work", "services"}
STEP2_ALWAYS_VISIBLE_FIELDS = [
    "creditor_name",
    "debtor_name",
    "case_type",
    "contract_signed",
    "contract_number",
    "contract_date",
    "debt_amount",
    "payment_due_date",
    "partial_payments_present",
    "penalty_exists",
    "documents_mentioned",
]


def normalize_case_type(value: Any) -> str | None:
    normalized = _normalize_string(value)
    if normalized is None:
        return None
    lowered = normalized.lower()
    mapped = CASE_TYPE_ALIASES.get(lowered)
    if mapped in SUPPORTED_CASE_TYPES:
        return mapped
    for alias, canonical in CASE_TYPE_ALIASES.items():
        if alias in lowered and canonical in SUPPORTED_CASE_TYPES:
            return canonical
    raise ValueError("invalid case_type")


def normalize_client_email(value: Any) -> str | None:
    normalized = _normalize_string(value)
    if normalized is None:
        return None
    lowered = normalized.lower()
    if "@" not in lowered:
        raise ValueError("invalid client_email")
    return lowered


def normalize_client_phone(value: Any) -> str | None:
    normalized = _normalize_string(value)
    if normalized is None:
        return None
    collapsed = re.sub(r"\s+", "", normalized)
    if not collapsed:
        return None
    return collapsed


def merge_normalized_data_patch(
    current_normalized_data: dict[str, Any] | None,
    patch_values: dict[str, Any],
    patch_fields: set[str],
) -> tuple[dict[str, Any], list[str]]:
    merged = _normalize_existing_payload(current_normalized_data)
    changed_fields: list[str] = []

    for field_name in patch_fields:
        if field_name not in merged:
            continue
        new_value = _normalize_patch_field(field_name, patch_values.get(field_name))
        if merged[field_name] != new_value:
            changed_fields.append(field_name)
            merged[field_name] = new_value

    if merged.get("partial_payments_present") is not True and merged.get("partial_payments"):
        merged["partial_payments"] = []
        if "partial_payments" not in changed_fields:
            changed_fields.append("partial_payments")

    if merged.get("penalty_exists") is not True and merged.get("penalty_rate_text") is not None:
        merged["penalty_rate_text"] = None
        if "penalty_rate_text" not in changed_fields:
            changed_fields.append("penalty_rate_text")

    merged["missing_fields"] = build_missing_fields(merged)
    return merged, changed_fields


def build_step2_contract(
    normalized_data: dict[str, Any] | None,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    normalized = _normalize_existing_payload(normalized_data)
    now_date = today or utcnow().date()

    total_paid = _sum_partial_payments(normalized.get("partial_payments"))
    debt_amount = normalized.get("debt_amount")
    remaining_debt = _compute_remaining_debt(debt_amount, total_paid)

    payment_due_date = _parse_iso_date(normalized.get("payment_due_date"))
    if payment_due_date is None:
        overdue_days: int | None = None
        is_overdue: bool | None = None
    else:
        overdue_days = max((now_date - payment_due_date).days, 0)
        is_overdue = overdue_days > 0

    missing_fields = normalized.get("missing_fields")
    return {
        "always_visible_fields": STEP2_ALWAYS_VISIBLE_FIELDS,
        "conditional_visibility": {
            "show_partial_payments": normalized.get("partial_payments_present") is True,
            "show_penalty_rate": normalized.get("penalty_exists") is True,
        },
        "missing_fields": missing_fields if isinstance(missing_fields, list) else [],
        "derived": {
            "total_paid_amount": total_paid,
            "remaining_debt_amount": remaining_debt,
            "overdue_days": overdue_days,
            "is_overdue": is_overdue,
        },
    }


def _normalize_existing_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    merged = build_empty_normalized_data()
    if isinstance(payload, dict):
        for field_name in merged:
            if field_name == "missing_fields":
                continue
            if field_name in payload:
                merged[field_name] = payload[field_name]

    merged["creditor_name"] = _normalize_string(merged.get("creditor_name"))
    merged["debtor_name"] = _normalize_string(merged.get("debtor_name"))
    merged["contract_signed"] = _normalize_bool(merged.get("contract_signed"))
    merged["contract_number"] = _normalize_string(merged.get("contract_number"))
    merged["contract_date"] = _normalize_date(merged.get("contract_date"))
    merged["debt_amount"] = _normalize_amount(merged.get("debt_amount"))
    merged["payment_due_date"] = _normalize_date(merged.get("payment_due_date"))
    merged["partial_payments_present"] = _normalize_bool(merged.get("partial_payments_present"))
    merged["partial_payments"] = _normalize_partial_payments(merged.get("partial_payments"))
    merged["penalty_exists"] = _normalize_bool(merged.get("penalty_exists"))
    merged["penalty_rate_text"] = _normalize_string(merged.get("penalty_rate_text"))
    merged["documents_mentioned"] = _normalize_documents(merged.get("documents_mentioned"))
    merged["missing_fields"] = build_missing_fields(merged)
    return merged


def _normalize_patch_field(field_name: str, value: Any) -> Any:
    if field_name in {"creditor_name", "debtor_name", "contract_number", "penalty_rate_text"}:
        return _normalize_string(value)
    if field_name in {"contract_signed", "partial_payments_present", "penalty_exists"}:
        return _normalize_bool(value)
    if field_name in {"contract_date", "payment_due_date"}:
        return _normalize_date(value)
    if field_name == "debt_amount":
        return _normalize_amount(value)
    if field_name == "partial_payments":
        return _normalize_partial_payments(value)
    if field_name == "documents_mentioned":
        return _normalize_documents(value)
    return value


def _normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    normalized = value.strip()
    return normalized or None


def _normalize_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "yes", "y", "1", "да", "истина"}:
        return True
    if normalized in {"false", "no", "n", "0", "нет", "ложь"}:
        return False
    return None


def _normalize_date(value: Any) -> str | None:
    normalized = _normalize_string(value)
    if not normalized:
        return None

    iso_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", normalized)
    if iso_match:
        return normalized

    dotted_match = re.fullmatch(r"(\d{2})[./](\d{2})[./](\d{4})", normalized)
    if dotted_match:
        day, month, year = dotted_match.groups()
        return f"{year}-{month}-{day}"

    return None


def _normalize_amount(value: Any) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value

    normalized = str(value).strip().lower()
    normalized = normalized.replace("\u00a0", " ").replace("\u202f", " ")
    normalized = (
        normalized.replace("рублей", "")
        .replace("рубля", "")
        .replace("руб.", "")
        .replace("руб", "")
        .replace("₽", "")
        .replace("rur", "")
        .replace("rub.", "")
        .replace("rub", "")
        .replace("р.", "")
        .replace("р", "")
    )
    normalized = normalized.replace(" ", "").replace(",", ".")
    normalized = re.sub(r"[^0-9.\-]", "", normalized)
    if not normalized:
        return None

    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return None

    return int(amount) if amount == amount.to_integral_value() else float(amount)


def _normalize_partial_payments(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        return []

    normalized_items: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            amount = _normalize_amount(item.get("amount"))
            payment_date = _normalize_date(item.get("date"))
        else:
            amount = None
            payment_date = None
        if amount is None and payment_date is None:
            continue
        normalized_items.append({"amount": amount, "date": payment_date})
    return normalized_items


def _normalize_documents(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [item for item in value if isinstance(item, str)]
    else:
        return []

    normalized_items: list[str] = []
    for item in items:
        normalized = item.strip().lower()
        if not normalized:
            continue
        mapped = DOCUMENT_ALIASES.get(normalized)
        if mapped:
            normalized_items.append(mapped)
            continue
        for alias, canonical in DOCUMENT_ALIASES.items():
            if alias in normalized:
                normalized_items.append(canonical)
                break
        else:
            normalized_items.append(normalized)

    deduped: list[str] = []
    for item in normalized_items:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _sum_partial_payments(value: Any) -> int | float:
    if not isinstance(value, list):
        return 0
    total = Decimal("0")
    for item in value:
        if not isinstance(item, dict):
            continue
        amount = item.get("amount")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            continue
        total += Decimal(str(amount))
    return int(total) if total == total.to_integral_value() else float(total)


def _compute_remaining_debt(debt_amount: Any, total_paid: int | float) -> int | float | None:
    if not isinstance(debt_amount, (int, float)) or isinstance(debt_amount, bool):
        return None
    remaining = Decimal(str(debt_amount)) - Decimal(str(total_paid))
    if remaining < 0:
        remaining = Decimal("0")
    return int(remaining) if remaining == remaining.to_integral_value() else float(remaining)


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None
