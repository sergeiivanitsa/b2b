import re
from typing import Any

from product_api.gateway_client import GatewayError, send_chat
from product_api.settings import Settings
from shared.constants import MODEL_GPT_5_2
from shared.schemas import ChatMetadata, ChatRequest

from .prompts import build_preview_generation_messages

_TECHNICAL_BLOCK_IDS = (
    "header",
    "facts",
    "legal_basis",
    "demand_block",
    "allowed_blocks",
    "blocked_blocks",
    "risk_flags",
)
_TECHNICAL_BLOCK_PATTERN = "|".join(re.escape(item) for item in _TECHNICAL_BLOCK_IDS)
_TECHNICAL_STANDALONE_RE = re.compile(
    rf"^(?:{_TECHNICAL_BLOCK_PATTERN})$",
    flags=re.IGNORECASE,
)
_TECHNICAL_LABEL_RE = re.compile(
    rf"^(?:{_TECHNICAL_BLOCK_PATTERN})\s*:",
    flags=re.IGNORECASE,
)
_TECHNICAL_JSON_KEY_RE = re.compile(
    rf"[\"'](?:{_TECHNICAL_BLOCK_PATTERN})[\"']\s*:",
    flags=re.IGNORECASE,
)
_JSON_LIKE_RE = re.compile(r"^\s*[\{\[][\s\S]*[\}\]]\s*$")
_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S", flags=re.MULTILINE)
_HEADER_OR_CONTACT_LABEL_RE = re.compile(
    r"^(?:кому|от\s+кого|адрес(?:\s+[^:]{1,80})?|e-?mail(?:\s*/\s*контакты)?|email|контакты|контактные\s+данные|телефон|тел\.)\s*:",
    flags=re.IGNORECASE,
)
_PREVIEW_PARAGRAPH_LIMIT = 2
_STANDALONE_CLAIM_TITLE_RE = re.compile(r"^\s*претензия\s*$", flags=re.IGNORECASE | re.MULTILINE)
_FINAL_PAYMENT_DEMAND_RE = re.compile(
    r"(?:требуем|просим)\s+оплатить|погасить\s+задолженность\s+в\s+срок",
    flags=re.IGNORECASE,
)
_COURT_BLOCK_RE = re.compile(
    r"обратиться\s+в\s+суд|обратимся\s+в\s+(?:арбитражный\s+)?суд|"
    r"в\s+судебном\s+порядке|исковое\s+заявление|арбитражный\s+суд",
    flags=re.IGNORECASE,
)
_LEGAL_REFERENCE_RE = re.compile(
    r"\bст\.\s*\d+|\bстатья\s+\d+|\bстатьи\s+\d+|\bгк\s*рф\b|"
    r"\bапк\s*рф\b|гражданск(?:ий|ого|ому|им|ом)\s+кодекс",
    flags=re.IGNORECASE,
)
_ATTACHMENT_OR_SIGNATURE_RE = re.compile(
    r"\bприложения\s*:|\bподпись\b|\bс\s+уважением\b",
    flags=re.IGNORECASE,
)
_DEMO_PAYWALL_RE = re.compile(
    r"демо-?версия|полная\s+версия\s+после\s+оплаты|оплатите\s+доступ",
    flags=re.IGNORECASE,
)
_LIST_LINE_RE = re.compile(r"^\s*(?:[-*\u2022]\s+|\d+[.)]\s+)", flags=re.MULTILINE)
_DOCUMENT_LABELS = {
    "contract": "договор",
    "invoice": "счет",
    "specification": "спецификацию",
    "application": "заявку",
    "заявка": "заявку",
    "upd": "УПД",
    "services_act": "акт",
    "acceptance_act": "акт",
    "waybill": "накладную",
    "ks_2": "акт КС-2",
    "ks_3": "акт КС-3",
}


async def generate_claim_preview(
    settings: Settings,
    *,
    claim_id: int,
    input_text: str,
    case_type: str | None,
    normalized_data: dict[str, Any] | None,
    decision: dict[str, Any],
) -> dict[str, Any]:
    messages = build_preview_generation_messages(
        input_text=input_text,
        case_type=case_type,
        normalized_data=normalized_data,
        allowed_blocks=decision["allowed_blocks"],
        blocked_blocks=decision["blocked_blocks"],
        risk_flags=decision["risk_flags"],
    )
    try:
        preview_text = await _request_preview_text(settings, claim_id=claim_id, messages=messages)
        preview_body = _prepare_preview_body(preview_text)
        return {
            "generated_preview_text": preview_body,
            "used_fallback": False,
            "error_code": None,
        }
    except (GatewayError, ValueError):
        fallback_text = build_safe_draft_preview(
            input_text=input_text,
            case_type=case_type,
            normalized_data=normalized_data,
            decision=decision,
        )
        return {
            "generated_preview_text": fallback_text,
            "used_fallback": True,
            "error_code": "preview_fallback",
        }


def build_safe_draft_preview(
    *,
    input_text: str,
    case_type: str | None,
    normalized_data: dict[str, Any] | None,
    decision: dict[str, Any],
) -> str:
    data = normalized_data or {}
    creditor = _optional_str(data.get("creditor_name"))
    debtor = _optional_str(data.get("debtor_name"))
    debt_amount = _format_amount(data.get("debt_amount"))
    due_date = _format_iso_date(data.get("payment_due_date"))
    creditor_role, debtor_role, _contract_label, creditor_action, debtor_action = _case_type_terms(
        case_type
    )
    document_phrase = _relationship_document_phrase(data, case_type)

    if creditor and debtor:
        first_paragraph = (
            f"Между {creditor} (далее — \"{creditor_role}\") и {debtor} "
            f"(далее — \"{debtor_role}\") возникли отношения {document_phrase}, "
            f"в рамках которых {creditor_role} обязался {creditor_action}, "
            f"а {debtor_role} — {debtor_action}."
        )
    else:
        first_paragraph = (
            f"Между сторонами возникли отношения {document_phrase}, "
            f"в рамках которых {creditor_role} и {debtor_role} исполняют согласованные обязательства."
        )

    payment_details: list[str] = []
    if debt_amount:
        payment_details.append(f"размер задолженности указан как {debt_amount}")
    if due_date:
        payment_details.append(f"срок оплаты указан как {due_date}")

    if payment_details:
        second_paragraph = (
            "По представленным данным " + ", ".join(payment_details) + ". "
            "Условия исполнения и оплаты оцениваются по соглашению сторон и подтверждающим документам."
        )
    else:
        second_paragraph = (
            "Условия исполнения и оплаты определяются соглашением сторон и представленными документами; "
            "размер задолженности и срок исполнения оцениваются по имеющимся материалам."
        )

    return f"{first_paragraph}\n\n{second_paragraph}"


async def _request_preview_text(
    settings: Settings,
    *,
    claim_id: int,
    messages,
) -> str:
    payload = ChatRequest(
        messages=messages,
        model=MODEL_GPT_5_2,
        stream=False,
        timeout=settings.gateway_timeout_seconds,
        metadata=ChatMetadata(
            company_id=claim_id,
            user_id=claim_id,
            conversation_id=claim_id,
            message_id=claim_id,
        ),
    )
    response = await send_chat(settings, payload)
    return response.text


def _prepare_preview_body(raw_text: str | None) -> str:
    normalized = _normalize_preview_text(raw_text)
    if _is_invalid_preview_response(normalized):
        raise ValueError("invalid preview response")

    paragraphs = _split_preview_paragraphs(normalized)
    if not paragraphs:
        raise ValueError("empty preview")

    selected_body = "\n\n".join(paragraphs[:_PREVIEW_PARAGRAPH_LIMIT]).strip()
    if _is_invalid_preview_body(selected_body):
        raise ValueError("invalid preview body")
    return selected_body


def _normalize_preview_text(raw_text: str | None) -> str:
    if raw_text is None:
        return ""
    candidate = str(raw_text).strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[^\r\n]*\r?\n?", "", candidate, count=1)
        candidate = re.sub(r"\r?\n?```\s*$", "", candidate)
    candidate = candidate.replace("\r\n", "\n").replace("\r", "\n")
    candidate = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", candidate)
    return candidate.strip()


def _is_invalid_preview_response(text: str) -> bool:
    candidate = text.strip()
    if not candidate:
        return True
    if _JSON_LIKE_RE.fullmatch(candidate):
        return True

    meaningful_lines = [line.strip() for line in candidate.splitlines() if line.strip()]
    return bool(meaningful_lines) and all(
        _TECHNICAL_STANDALONE_RE.fullmatch(line) for line in meaningful_lines
    )


def _split_preview_paragraphs(text: str) -> list[str]:
    candidate = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []
    for block in re.split(r"\n[ \t]*\n+", candidate):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        separator = "\n" if _has_structural_line(lines) else " "
        paragraph = re.sub(r"[ \t]+", " ", separator.join(lines)).strip()
        if paragraph:
            paragraphs.append(paragraph)
    return paragraphs


def _is_invalid_preview_body(text: str) -> bool:
    candidate = text.strip()
    if not candidate:
        return True
    if _JSON_LIKE_RE.fullmatch(candidate):
        return True
    if _TECHNICAL_JSON_KEY_RE.search(candidate):
        return True
    if _MARKDOWN_HEADING_RE.search(candidate):
        return True
    if _STANDALONE_CLAIM_TITLE_RE.search(candidate):
        return True
    if _FINAL_PAYMENT_DEMAND_RE.search(candidate):
        return True
    if _COURT_BLOCK_RE.search(candidate):
        return True
    if _LEGAL_REFERENCE_RE.search(candidate):
        return True
    if _ATTACHMENT_OR_SIGNATURE_RE.search(candidate):
        return True
    if _DEMO_PAYWALL_RE.search(candidate):
        return True
    if _LIST_LINE_RE.search(candidate):
        return True

    for raw_line in candidate.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _TECHNICAL_STANDALONE_RE.fullmatch(line):
            return True
        if _TECHNICAL_LABEL_RE.match(line):
            return True
        if _HEADER_OR_CONTACT_LABEL_RE.match(line):
            return True
    return False


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _has_structural_line(lines: list[str]) -> bool:
    return any(
        _TECHNICAL_STANDALONE_RE.fullmatch(line)
        or _STANDALONE_CLAIM_TITLE_RE.fullmatch(line)
        or _HEADER_OR_CONTACT_LABEL_RE.match(line)
        or _ATTACHMENT_OR_SIGNATURE_RE.search(line)
        or _LIST_LINE_RE.match(line)
        for line in lines
    )


def _case_type_terms(case_type: str | None) -> tuple[str, str, str, str, str]:
    if case_type == "supply":
        return (
            "Поставщик",
            "Покупатель",
            "договора поставки",
            "поставить товар",
            "принять товар и произвести оплату",
        )
    if case_type == "services":
        return (
            "Исполнитель",
            "Заказчик",
            "договора оказания услуг",
            "оказать услуги",
            "принять и оплатить услуги",
        )
    if case_type == "contract_work":
        return (
            "Подрядчик",
            "Заказчик",
            "договора подряда",
            "выполнить работы",
            "принять результат работ и произвести оплату",
        )
    return (
        "Кредитор",
        "Должник",
        "договора",
        "исполнить свои обязательства",
        "исполнить встречные обязательства",
    )


def _relationship_document_phrase(data: dict[str, Any], case_type: str | None) -> str:
    contract_number = _optional_str(data.get("contract_number"))
    contract_date = _format_iso_date(data.get("contract_date"))
    contract_signed = data.get("contract_signed") is True
    _creditor_role, _debtor_role, contract_label, _creditor_action, _debtor_action = (
        _case_type_terms(case_type)
    )
    if contract_signed or contract_number or contract_date:
        parts = [f"на основании {contract_label}"]
        if contract_number:
            parts.append(f"№ {contract_number}")
        if contract_date:
            parts.append(f"от {contract_date}")
        return " ".join(parts)

    document_labels = _document_labels(data.get("documents_mentioned"))
    if document_labels:
        return "на основании представленных документов, включая " + _join_ru_list(document_labels)
    return "на основании достигнутого сторонами соглашения и представленных данных"


def _document_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    labels: list[str] = []
    for item in value:
        normalized = _optional_str(item)
        if not normalized:
            continue
        label = _DOCUMENT_LABELS.get(normalized.lower())
        if label and label not in labels:
            labels.append(label)
    return labels


def _join_ru_list(items: list[str]) -> str:
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} и {items[1]}"
    return ", ".join(items[:-1]) + " и " + items[-1]


def _format_iso_date(value: Any) -> str | None:
    normalized = _optional_str(value)
    if not normalized:
        return None
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", normalized)
    if match:
        year, month, day = match.groups()
        return f"{day}.{month}.{year}"
    return normalized


def _format_amount(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ") + " руб."
    if isinstance(value, float):
        if value.is_integer():
            return f"{int(value):,}".replace(",", " ") + " руб."
        formatted = f"{value:,.2f}".replace(",", " ").replace(".", ",")
        formatted = formatted.rstrip("0").rstrip(",")
        return f"{formatted} руб."
    return _optional_str(value)
