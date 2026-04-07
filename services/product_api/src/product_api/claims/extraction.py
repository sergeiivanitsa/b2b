import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from product_api.settings import Settings
from shared.schemas import ChatMessage

from .gateway_adapter import request_claim_extraction

REQUIRED_FIELDS = (
    "creditor_name",
    "creditor_inn",
    "debtor_name",
    "debtor_inn",
    "contract_signed",
    "debt_amount",
    "payment_due_date",
)

CASE_TYPE_ALIASES = {
    "supply": "supply",
    "delivery": "supply",
    "поставка": "supply",
    "договор поставки": "supply",
    "services": "services",
    "service": "services",
    "услуги": "services",
    "оказание услуг": "services",
    "contract_work": "contract_work",
    "works": "contract_work",
    "work": "contract_work",
    "подряд": "contract_work",
    "договор подряда": "contract_work",
}

DOCUMENT_ALIASES = {
    "contract": "contract",
    "договор": "contract",
    "дог": "contract",
    "invoice": "invoice",
    "счет": "invoice",
    "счёт": "invoice",
    "upd": "upd",
    "упд": "upd",
    "waybill": "waybill",
    "накладная": "waybill",
    "services_act": "services_act",
    "акт услуг": "services_act",
    "acceptance_act": "acceptance_act",
    "акт": "acceptance_act",
    "ks-2": "ks_2",
    "кс-2": "ks_2",
    "ks-3": "ks_3",
    "кс-3": "ks_3",
    "specification": "specification",
    "спецификация": "specification",
    "payment_order": "payment_order",
    "платежка": "payment_order",
    "платёжка": "payment_order",
}


def build_empty_normalized_data() -> dict[str, Any]:
    normalized = {
        "creditor_name": None,
        "creditor_inn": None,
        "debtor_name": None,
        "debtor_inn": None,
        "contract_signed": None,
        "contract_number": None,
        "contract_date": None,
        "debt_amount": None,
        "payment_due_date": None,
        "partial_payments_present": None,
        "partial_payments": [],
        "penalty_exists": None,
        "penalty_rate_text": None,
        "documents_mentioned": [],
    }
    normalized["missing_fields"] = build_missing_fields(normalized)
    return normalized


def build_claim_extraction_messages(input_text: str) -> list[ChatMessage]:
    system_prompt = (
        "You extract structured facts from a Russian B2B debt-claim description. "
        "Return only one JSON object. Do not use markdown fences. "
        "Use these keys exactly: "
        "case_type, creditor_name, creditor_inn, debtor_name, debtor_inn, "
        "contract_signed, contract_number, "
        "contract_date, debt_amount, payment_due_date, partial_payments_present, "
        "partial_payments, penalty_exists, penalty_rate_text, documents_mentioned. "
        "case_type must be one of supply, contract_work, services, or null. "
        "Dates must be YYYY-MM-DD when exact, otherwise null. "
        "debt_amount must be a number when exact, otherwise null. "
        "partial_payments must be an array of objects with amount and date. "
        "Unknown values must be null, false, or empty arrays where appropriate."
    )
    return [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=input_text),
    ]


def build_missing_fields(normalized_data: dict[str, Any]) -> list[str]:
    missing_fields: list[str] = []
    for field_name in REQUIRED_FIELDS:
        if _is_missing_value(normalized_data.get(field_name)):
            missing_fields.append(field_name)

    if normalized_data.get("partial_payments_present") is True and not normalized_data.get(
        "partial_payments"
    ):
        missing_fields.append("partial_payments")

    if normalized_data.get("penalty_exists") is True and _is_missing_value(
        normalized_data.get("penalty_rate_text")
    ):
        missing_fields.append("penalty_rate_text")

    return missing_fields


def count_populated_fields(normalized_data: dict[str, Any]) -> int:
    fields = (
        "creditor_name",
        "creditor_inn",
        "debtor_name",
        "debtor_inn",
        "contract_signed",
        "contract_number",
        "contract_date",
        "debt_amount",
        "payment_due_date",
        "partial_payments_present",
        "partial_payments",
        "penalty_exists",
        "penalty_rate_text",
        "documents_mentioned",
    )
    return sum(1 for field_name in fields if not _is_missing_value(normalized_data.get(field_name)))


def build_extraction_event_payload(result: dict[str, Any]) -> dict[str, Any]:
    normalized_data = result["normalized_data"]
    payload = {
        "result": "fallback" if result["error_code"] else "success",
        "case_type": result["case_type"],
        "fields_populated": count_populated_fields(normalized_data),
        "missing_fields": normalized_data["missing_fields"],
    }
    if result["error_code"]:
        payload["error_code"] = result["error_code"]
    return payload


async def run_claim_extraction(
    settings: Settings,
    *,
    claim_id: int,
    input_text: str,
) -> dict[str, Any]:
    messages = build_claim_extraction_messages(input_text)
    raw_text = await request_claim_extraction(settings, claim_id=claim_id, messages=messages)
    return parse_claim_extraction_response(raw_text)


def parse_claim_extraction_response(raw_text: str) -> dict[str, Any]:
    try:
        payload = _load_extraction_payload(raw_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "case_type": None,
            "normalized_data": build_empty_normalized_data(),
            "error_code": "invalid_response",
        }

    return {
        "case_type": _normalize_case_type(payload.get("case_type")),
        "normalized_data": normalize_extraction_payload(payload),
        "error_code": None,
    }


def normalize_extraction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = build_empty_normalized_data()

    normalized["creditor_name"] = _normalize_string(payload.get("creditor_name"))
    normalized["creditor_inn"] = _normalize_inn(payload.get("creditor_inn"))
    normalized["debtor_name"] = _normalize_string(payload.get("debtor_name"))
    normalized["debtor_inn"] = _normalize_inn(payload.get("debtor_inn"))
    normalized["contract_signed"] = _normalize_bool(payload.get("contract_signed"))
    normalized["contract_number"] = _normalize_string(payload.get("contract_number"))
    normalized["contract_date"] = _normalize_date(payload.get("contract_date"))
    normalized["debt_amount"] = _normalize_amount(payload.get("debt_amount"))
    normalized["payment_due_date"] = _normalize_date(payload.get("payment_due_date"))
    normalized["partial_payments_present"] = _normalize_bool(
        payload.get("partial_payments_present")
    )
    normalized["partial_payments"] = _normalize_partial_payments(payload.get("partial_payments"))
    normalized["penalty_exists"] = _normalize_bool(payload.get("penalty_exists"))
    normalized["penalty_rate_text"] = _normalize_string(payload.get("penalty_rate_text"))
    normalized["documents_mentioned"] = _normalize_documents(payload.get("documents_mentioned"))

    if normalized["contract_signed"] is None and (
        normalized["contract_number"] or normalized["contract_date"]
    ):
        normalized["contract_signed"] = True
    if normalized["partial_payments_present"] is None and normalized["partial_payments"]:
        normalized["partial_payments_present"] = True
    if normalized["penalty_exists"] is None and normalized["penalty_rate_text"]:
        normalized["penalty_exists"] = True

    normalized["missing_fields"] = build_missing_fields(normalized)
    return normalized


def _load_extraction_payload(raw_text: str) -> dict[str, Any]:
    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be a string")

    candidate = raw_text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or start >= end:
        raise ValueError("json object not found")

    payload = json.loads(candidate[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("json payload must be an object")
    return payload


def _normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    normalized = value.strip()
    return normalized or None


def _normalize_inn(value: Any) -> str | None:
    normalized = _normalize_string(value)
    if normalized is None:
        return None
    digits_only = re.sub(r"\D+", "", normalized)
    if not digits_only:
        return None
    if len(digits_only) not in {10, 12}:
        return None
    return digits_only


def _normalize_case_type(value: Any) -> str | None:
    normalized = _normalize_string(value)
    if not normalized:
        return None
    lowered = normalized.lower()
    mapped = CASE_TYPE_ALIASES.get(lowered)
    if mapped:
        return mapped
    for alias, canonical in CASE_TYPE_ALIASES.items():
        if alias in lowered:
            return canonical
    return None


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
    if not isinstance(value, list):
        return []

    normalized_items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        amount = _normalize_amount(item.get("amount"))
        payment_date = _normalize_date(item.get("date"))
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


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list):
        return len(value) == 0
    return False
