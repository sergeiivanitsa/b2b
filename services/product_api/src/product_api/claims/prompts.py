import json
from typing import Any

from shared.schemas import ChatMessage

_BLOCK_LIMIT_NOTES = {
    "legal_basis": "не добавлять правовой блок со ссылками на нормы права",
    "penalty_section": "не добавлять расчет санкций или неустойки",
    "attachments": "не добавлять раздел приложений",
}

_RISK_LIMIT_NOTES = {
    "case_type_uncertain": "если тип отношений неочевиден, использовать осторожные нейтральные формулировки",
    "contract_status_uncertain": "не утверждать факт подписания договора без данных",
    "no_supporting_documents": "не перечислять документы как приложенные, если это не подтверждено данными",
    "high_claim_amount": "не делать категоричных выводов без дополнительной проверки",
}


def build_preview_generation_messages(
    *,
    input_text: str,
    case_type: str | None,
    normalized_data: dict[str, Any] | None,
    allowed_blocks: list[str],
    blocked_blocks: list[str],
    risk_flags: list[str],
) -> list[ChatMessage]:
    system_prompt = (
        "Ты юрист по претензионной работе в РФ. "
        "Сформируй только plain text тела preview досудебной претензии на русском языке: 1–2 содержательных абзаца. "
        "Абзац 1 описывает основание отношений: стороны, их роли, договор или представленные документы; номер и дату договора можно использовать только если они есть в данных. "
        "Абзац 2 описывает исполнение и оплату: сумму задолженности, срок оплаты и условия исполнения, если эти сведения есть в данных. "
        "Не возвращай markdown. Не возвращай JSON. "
        "Не используй списки, bullets или нумерацию. "
        "Не дублируй шапку документа. "
        "Не генерируй заголовок ПРЕТЕНЗИЯ, исходящий номер, дату самой претензии, контакты, приложения или подпись. "
        "Не добавляй финальное требование оплатить, судебный блок, исковое заявление или полный правовой блок со статьями ГК РФ/АПК РФ. "
        "Не добавляй demo/paywall текст: Демо-версия, полная версия после оплаты, оплатите доступ. "
        "Не используй английские технические названия блоков. "
        "Не пиши строки header, facts, legal_basis, demand_block, allowed_blocks, blocked_blocks, risk_flags. "
        "Не добавляй строки \"Кому:\", \"От кого:\", \"Адрес:\", \"E-mail:\", \"E-mail/контакты:\", \"Email:\", \"Контакты:\", \"Телефон:\". "
        "Не выдумывай факты, которых нет в исходных данных. "
        "Если данных недостаточно, используй осторожные нейтральные формулировки без служебных пометок."
    )
    context = {
        "case_type": case_type,
        "normalized_data": normalized_data or {},
        "generation_limits": _build_generation_limit_notes(
            blocked_blocks=blocked_blocks,
            risk_flags=risk_flags,
        ),
    }
    user_prompt = (
        "Ситуация пользователя:\n"
        f"{input_text.strip()}\n\n"
        "Данные для учета. Не копируй формат и названия полей в ответ:\n"
        f"{json.dumps(context, ensure_ascii=False)}\n\n"
        "Верни только 1–2 абзаца тела preview. "
        "Не добавляй labels, списки технических ограничений, финальное требование, судебный блок, статьи закона, приложения, подпись, demo/paywall текст или сведения, которых нет в данных."
    )
    return [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]


def _build_generation_limit_notes(
    *,
    blocked_blocks: list[str],
    risk_flags: list[str],
) -> list[str]:
    notes: list[str] = []
    for block_name in blocked_blocks:
        note = _BLOCK_LIMIT_NOTES.get(block_name)
        if note and note not in notes:
            notes.append(note)

    for risk_flag in risk_flags:
        note = _RISK_LIMIT_NOTES.get(risk_flag)
        if note and note not in notes:
            notes.append(note)

    if not notes:
        notes.append("не добавлять сведения, которых нет во входных данных")
    return notes
