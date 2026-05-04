import re
from datetime import date
from typing import Any, Mapping

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
    "invoice": "счёт",
    "specification": "спецификацию",
    "application": "заявку",
    "заявка": "заявку",
    "upd": "УПД",
    "services_act": "акт",
    "acceptance_act": "акт",
    "waybill": "накладную",
    "ks_2": "акт КС-2",
    "ks_3": "акт КС-3",
    "payment_order": "платёжное поручение",
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
    debt_amount = _format_amount(data.get("debt_amount"))
    due_date = _format_iso_date(data.get("payment_due_date"))
    first_paragraph = _build_relationship_opening_paragraph(data, case_type)

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


def _build_relationship_opening_paragraph(
    data: Mapping[str, Any],
    case_type: str | None,
) -> str:
    terms = _case_type_relationship_terms(case_type)
    if terms is None:
        return _build_neutral_relationship_opening(data)

    creditor = _optional_str(data.get("creditor_name"))
    debtor = _optional_str(data.get("debtor_name"))
    parties = _relationship_parties_phrase(creditor=creditor, debtor=debtor)
    contract_reference = _build_contract_reference(data, terms["contract_label"])
    document_labels = _document_labels(data.get("documents_mentioned"))
    documents_phrase = _documents_basis_phrase(document_labels)

    if contract_reference:
        if data.get("contract_signed") is False:
            basis = f"отношения сторон связаны с {contract_reference}"
            if documents_phrase:
                basis += f" и {documents_phrase}"
            return (
                f"{parties} возникли обязательственные отношения, связанные с "
                f"{terms['relationship_phrase']}; {basis}. "
                f"По представленным данным {creditor or 'сторона, заявляющая требование'} "
                f"выступило {terms['creditor_role']} и обязалось {terms['creditor_action']}, "
                f"тогда как {debtor or 'обязанная сторона'}, являясь {terms['debtor_role']}, "
                f"обязалось {terms['debtor_action']} в порядке и сроки, предусмотренные "
                "соглашением сторон."
            )

        return (
            f"{parties} был заключён {contract_reference}, на основании которого между сторонами "
            f"возникли взаимные обязательства, связанные с {terms['relationship_phrase']}. "
            f"По условиям договора {creditor or 'сторона, заявляющая требование'} "
            f"выступило {terms['creditor_role']} и обязалось {terms['creditor_action']}, "
            f"тогда как {debtor or 'обязанная сторона'}, являясь {terms['debtor_role']}, "
            f"обязалось {terms['debtor_action']} в порядке и сроки, предусмотренные договором."
        )

    if documents_phrase:
        return (
            f"{parties} возникли обязательственные отношения, связанные с "
            f"{terms['relationship_phrase']}. Основанием возникновения обязательств являются "
            f"{documents_phrase}, включая {_join_ru_list(document_labels)}. "
            f"По представленным данным {creditor or 'сторона, заявляющая требование'} "
            f"выступило {terms['creditor_role']} и обязалось {terms['creditor_action']}, "
            f"тогда как {debtor or 'обязанная сторона'}, являясь {terms['debtor_role']}, "
            f"обязалось {terms['debtor_action']}."
        )

    return (
        f"{parties} возникли обязательственные отношения, связанные с "
        f"{terms['relationship_phrase']}. По представленным данным "
        f"{creditor or 'сторона, заявляющая требование'} выступило {terms['creditor_role']} "
        f"и обязалось {terms['creditor_action']}, тогда как "
        f"{debtor or 'обязанная сторона'}, являясь {terms['debtor_role']}, "
        f"обязалось {terms['debtor_action']} в порядке и сроки, согласованные сторонами."
    )


def _case_type_relationship_terms(case_type: str | None) -> dict[str, str] | None:
    if case_type == "supply":
        return {
            "contract_label": "договор поставки",
            "relationship_phrase": "поставкой, приёмкой и оплатой товара",
            "creditor_role": "поставщиком",
            "debtor_role": "покупателем",
            "creditor_action": "передать товар покупателю",
            "debtor_action": "принять поставленный товар и своевременно произвести оплату его стоимости",
        }
    if case_type == "services":
        return {
            "contract_label": "договор оказания услуг",
            "relationship_phrase": "оказанием, приёмкой и оплатой услуг",
            "creditor_role": "исполнителем",
            "debtor_role": "заказчиком",
            "creditor_action": "оказать услуги заказчику",
            "debtor_action": "принять оказанные услуги и своевременно произвести оплату их стоимости",
        }
    if case_type == "contract_work":
        return {
            "contract_label": "договор подряда",
            "relationship_phrase": "выполнением, приёмкой и оплатой работ",
            "creditor_role": "подрядчиком",
            "debtor_role": "заказчиком",
            "creditor_action": "выполнить работы для заказчика",
            "debtor_action": "принять результат выполненных работ и своевременно произвести оплату их стоимости",
        }
    return None


def _build_neutral_relationship_opening(data: Mapping[str, Any]) -> str:
    creditor = _optional_str(data.get("creditor_name"))
    debtor = _optional_str(data.get("debtor_name"))
    parties = _relationship_parties_phrase(creditor=creditor, debtor=debtor)
    document_labels = _document_labels(data.get("documents_mentioned"))
    documents_phrase = _documents_basis_phrase(document_labels)

    basis_sentence = (
        f" Основанием возникновения обязательств являются {documents_phrase}, "
        f"включая {_join_ru_list(document_labels)}."
        if documents_phrase
        else ""
    )
    return (
        f"{parties} возникли обязательственные отношения, связанные с исполнением "
        f"согласованных обязательств и последующей оплатой.{basis_sentence} "
        "Сторона, заявляющая требование, указывает на исполнение своих обязанностей, "
        "тогда как обязанная сторона должна была произвести оплату в порядке и сроки, "
        "вытекающие из достигнутых договорённостей и представленных документов."
    )


def _relationship_parties_phrase(*, creditor: str | None, debtor: str | None) -> str:
    if creditor and debtor:
        return f"Между {creditor} и {debtor}"
    return "Между сторонами"


def _build_contract_reference(data: Mapping[str, Any], contract_label: str) -> str | None:
    contract_number = _optional_str(data.get("contract_number"))
    contract_date = _format_contract_reference_date(data.get("contract_date"))
    if data.get("contract_signed") is not True and not contract_number and not contract_date:
        return None

    parts = [contract_label]
    if contract_number:
        parts.append(f"№{contract_number}")
    if contract_date:
        parts.append(f"от {contract_date}")
    return " ".join(parts)


def _format_contract_reference_date(value: Any) -> str | None:
    normalized = _optional_str(value)
    if not normalized:
        return None
    iso_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", normalized)
    if iso_match:
        year, month, day = iso_match.groups()
        if not _is_valid_date_parts(year=year, month=month, day=day):
            return None
        return f"{day}.{month}.{year}"
    dotted_match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", normalized)
    if dotted_match:
        day, month, year = dotted_match.groups()
        if not _is_valid_date_parts(year=year, month=month, day=day):
            return None
        return normalized
    return None


def _is_valid_date_parts(*, year: str, month: str, day: str) -> bool:
    try:
        date(int(year), int(month), int(day))
    except ValueError:
        return False
    return True


def _documents_basis_phrase(document_labels: list[str]) -> str | None:
    if not document_labels:
        return None
    return "представленные документы сторон"


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
