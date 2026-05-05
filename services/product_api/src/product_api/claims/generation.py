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
    reference_date: date | None = None,
) -> dict[str, Any]:
    data = normalized_data or {}
    messages = build_preview_generation_messages(
        input_text=input_text,
        case_type=case_type,
        normalized_data=normalized_data,
        derived_preview_data=_build_preview_derived_data(data, reference_date),
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
            reference_date=reference_date,
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
    reference_date: date | None = None,
) -> str:
    data = normalized_data or {}
    first_paragraph = _build_relationship_opening_paragraph(data, case_type)
    second_paragraph = _build_performance_and_debt_paragraph(
        data,
        case_type,
        reference_date=reference_date,
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


def _build_performance_and_debt_paragraph(
    data: Mapping[str, Any],
    case_type: str | None,
    *,
    reference_date: date | None = None,
) -> str:
    terms = _case_type_performance_terms(case_type)
    if terms is None:
        return _build_neutral_performance_and_debt_paragraph(
            data,
            reference_date=reference_date,
        )

    creditor = _optional_str(data.get("creditor_name"))
    debtor = _optional_str(data.get("debtor_name"))
    creditor_subject = creditor or "сторона, заявляющая требование"
    debtor_subject = debtor or "обязанная сторона"
    debtor_role = terms["debtor_role_genitive"]
    payment_basis = "предусмотренные договором"
    non_payment_deadline = "в установленный договором срок"
    if data.get("contract_signed") is False:
        payment_basis = "согласованные сторонами"
        non_payment_deadline = "в установленный срок"

    if data.get("contract_signed") is False:
        opening = (
            f"Исходя из представленных данных, {creditor_subject} "
            f"{_typed_creditor_verb(creditor)} обязательства, связанные с "
            f"{terms['performance_obligation_phrase']} {terms['performance_destination'](debtor_subject)}."
        )
    else:
        opening = (
            f"Во исполнение условий {terms['contract_label']} {creditor_subject}, "
            f"исходя из представленных данных, {_typed_creditor_verb(creditor)} принятые на себя "
            f"обязательства, {terms['performance_completion'](debtor_subject)}."
        )

    amount = _format_amount(data.get("debt_amount"))
    due_date = _format_payment_due_date_strict(data.get("payment_due_date"))
    overdue_days = _calculate_overdue_days(data.get("payment_due_date"), reference_date)

    sentences = [
        opening,
        (
            f"{terms['performance_fact']} и является основанием для возникновения у {debtor_role} "
            f"встречной обязанности по оплате {terms['payment_object']} в порядке, размере и сроки, "
            f"{payment_basis}."
        ),
        (
            f"Несмотря на исполнение обязательств со стороны {terms['creditor_role_genitive']}, "
            f"{debtor_subject} оплату {terms['non_payment_object']} {non_payment_deadline} "
            f"{_typed_debtor_non_payment_verb(debtor)}, чем {_typed_debtor_violation_verb(debtor)} принятые на себя "
            "обязательства по своевременному внесению оплаты."
        ),
        _build_debt_amount_sentence(amount=amount, creditor=creditor),
        _build_due_date_status_sentence(due_date, overdue_days=overdue_days),
    ]

    partial_payments_sentence = _build_partial_payments_sentence(data, debtor_role)
    if partial_payments_sentence:
        sentences.append(partial_payments_sentence)

    return " ".join(sentence for sentence in sentences if sentence)


def _case_type_performance_terms(case_type: str | None) -> dict[str, Any] | None:
    if case_type == "supply":
        return {
            "contract_label": "договора поставки",
            "creditor_role_genitive": "поставщика",
            "debtor_role_genitive": "покупателя",
            "performance_obligation_phrase": "передачей товара",
            "performance_completion": lambda debtor: f"обеспечив передачу товара в адрес {debtor}",
            "performance_destination": lambda debtor: f"в адрес {debtor}",
            "performance_fact": (
                "Поставка товара свидетельствует о фактическом исполнении поставщиком "
                "своей части договорных обязательств"
            ),
            "payment_object": "полученного товара",
            "non_payment_object": "поставленного товара",
        }
    if case_type == "services":
        return {
            "contract_label": "договора оказания услуг",
            "creditor_role_genitive": "исполнителя",
            "debtor_role_genitive": "заказчика",
            "performance_obligation_phrase": "оказанием услуг",
            "performance_completion": lambda debtor: f"обеспечив оказание услуг в адрес {debtor}",
            "performance_destination": lambda debtor: f"в адрес {debtor}",
            "performance_fact": (
                "Оказание услуг свидетельствует о фактическом исполнении исполнителем "
                "своей части договорных обязательств"
            ),
            "payment_object": "оказанных услуг",
            "non_payment_object": "оказанных услуг",
        }
    if case_type == "contract_work":
        return {
            "contract_label": "договора подряда",
            "creditor_role_genitive": "подрядчика",
            "debtor_role_genitive": "заказчика",
            "performance_obligation_phrase": "выполнением работ",
            "performance_completion": lambda debtor: f"обеспечив выполнение работ для {debtor}",
            "performance_destination": lambda debtor: f"для {debtor}",
            "performance_fact": (
                "Выполнение работ свидетельствует о фактическом исполнении подрядчиком "
                "своей части договорных обязательств"
            ),
            "payment_object": "выполненных работ",
            "non_payment_object": "выполненных работ",
        }
    return None


def _build_neutral_performance_and_debt_paragraph(
    data: Mapping[str, Any],
    *,
    reference_date: date | None = None,
) -> str:
    creditor = _optional_str(data.get("creditor_name"))
    debtor = _optional_str(data.get("debtor_name"))
    creditor_subject = creditor or "сторона, заявляющая требование"
    creditor_side = creditor or "стороны, заявляющей требование"
    debtor_subject = debtor or "обязанная сторона"
    amount = _format_amount(data.get("debt_amount"))
    due_date = _format_payment_due_date_strict(data.get("payment_due_date"))
    overdue_days = _calculate_overdue_days(data.get("payment_due_date"), reference_date)

    sentences = [
        (
            f"Исходя из представленных данных, {creditor_subject} {_neutral_creditor_verb(creditor)} "
            "принятые на себя обязательства, в связи с чем у обязанной стороны возникла "
            "встречная обязанность по оплате."
        ),
        (
            f"Несмотря на исполнение обязательств со стороны {creditor_side}, "
            f"{debtor_subject} {_neutral_debtor_non_payment_verb(debtor)} денежное обязательство "
            "в установленный срок."
        ),
        _build_debt_amount_sentence(amount=amount, creditor=creditor),
        _build_due_date_status_sentence(due_date, overdue_days=overdue_days),
    ]

    partial_payments_sentence = _build_partial_payments_sentence(data, "обязанной стороны")
    if partial_payments_sentence:
        sentences.append(partial_payments_sentence)

    return " ".join(sentence for sentence in sentences if sentence)


def _typed_creditor_verb(creditor: str | None) -> str:
    return "выполнило" if creditor else "исполнила"


def _typed_debtor_non_payment_verb(debtor: str | None) -> str:
    return "не произвело" if debtor else "не произвела"


def _typed_debtor_violation_verb(debtor: str | None) -> str:
    return "нарушило" if debtor else "нарушила"


def _neutral_creditor_verb(creditor: str | None) -> str:
    return "исполнило" if creditor else "исполнила"


def _neutral_debtor_non_payment_verb(debtor: str | None) -> str:
    return "не исполнило" if debtor else "не исполнила"


def _build_debt_amount_sentence(*, amount: str | None, creditor: str | None) -> str:
    creditor_phrase = f" перед {creditor}" if creditor else ""
    if amount:
        return _ensure_sentence_period(
            f"В результате неисполнения денежного обязательства{creditor_phrase} "
            f"образовалась задолженность в размере {amount}"
        )
    return f"В результате неисполнения денежного обязательства{creditor_phrase} образовалась задолженность."


def _ensure_sentence_period(value: str) -> str:
    return value if value.endswith(".") else f"{value}."


def _build_due_date_status_sentence(
    due_date: str | None,
    *,
    overdue_days: int | None = None,
) -> str:
    if due_date:
        overdue_phrase = (
            f", период просрочки составляет {_format_calendar_days(overdue_days)}"
            if overdue_days is not None
            else ""
        )
        return (
            f"Срок исполнения обязанности по оплате наступил {due_date}, однако по состоянию "
            f"на дату направления настоящего обращения задолженность остаётся непогашенной{overdue_phrase}."
        )
    return "По состоянию на дату направления настоящего обращения задолженность остаётся непогашенной."


def _format_calendar_days(days: int) -> str:
    last_two_digits = days % 100
    last_digit = days % 10
    if 11 <= last_two_digits <= 14:
        suffix = "календарных дней"
    elif last_digit == 1:
        suffix = "календарный день"
    elif 2 <= last_digit <= 4:
        suffix = "календарных дня"
    else:
        suffix = "календарных дней"
    return f"{days} {suffix}"


def _build_partial_payments_sentence(
    data: Mapping[str, Any],
    debtor_role: str | None,
) -> str | None:
    partial_payments_present = data.get("partial_payments_present")
    partial_payments = data.get("partial_payments")
    has_partial_payments = isinstance(partial_payments, list) and bool(partial_payments)
    debtor_role_phrase = debtor_role or "обязанной стороны"

    if partial_payments_present is False and not has_partial_payments:
        return (
            "Информация о частичном погашении задолженности либо об ином исполнении денежного "
            "обязательства отсутствует, в связи с чем задолженность считается сохраняющейся "
            f"в полном размере, а нарушение обязательств со стороны {debtor_role_phrase} "
            "является продолжающимся."
        )
    if partial_payments_present is None:
        return "Сведения о частичных оплатах в представленных данных не указаны."
    if partial_payments_present is True and has_partial_payments:
        return (
            "Сведения о частичных оплатах учитываются при оценке размера задолженности; "
            "денежное обязательство в соответствующей части остаётся неисполненным."
        )
    if partial_payments_present is True:
        return (
            "В представленных данных указано на наличие частичных оплат, однако сведения, "
            "достаточные для их учёта, отсутствуют."
        )
    return None


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


def _build_preview_derived_data(
    data: Mapping[str, Any],
    reference_date: date | None,
) -> dict[str, Any] | None:
    if reference_date is None:
        return None

    derived: dict[str, Any] = {
        "reference_date": reference_date.isoformat(),
    }
    overdue_days = _calculate_overdue_days(data.get("payment_due_date"), reference_date)
    if overdue_days is not None:
        derived["overdue_days"] = overdue_days
    return derived


def _parse_payment_due_date(value: Any) -> date | None:
    normalized = _optional_str(value)
    if not normalized:
        return None

    iso_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", normalized)
    if iso_match:
        year, month, day = (int(part) for part in iso_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    dotted_match = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", normalized)
    if dotted_match:
        day, month, year = (int(part) for part in dotted_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    return None


def _calculate_overdue_days(value: Any, reference_date: date | None) -> int | None:
    if reference_date is None:
        return None
    due_date = _parse_payment_due_date(value)
    if due_date is None:
        return None
    overdue_days = (reference_date - due_date).days
    return overdue_days if overdue_days > 0 else None


def _format_payment_due_date_strict(value: Any) -> str | None:
    due_date = _parse_payment_due_date(value)
    if due_date is None:
        return None
    return f"{due_date.day:02d}.{due_date.month:02d}.{due_date.year}"


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
