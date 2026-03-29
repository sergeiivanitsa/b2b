import json
from typing import Any

from shared.schemas import ChatMessage


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
        "Сформируй безопасный черновик досудебной претензии на русском языке. "
        "Верни только plain text, без markdown и без JSON. "
        "Не выдумывай факты, которых нет в исходных данных. "
        "Если данных недостаточно по отдельным частям, помечай их как требующие уточнения."
    )
    context = {
        "case_type": case_type,
        "normalized_data": normalized_data or {},
        "allowed_blocks": allowed_blocks,
        "blocked_blocks": blocked_blocks,
        "risk_flags": risk_flags,
    }
    user_prompt = (
        "Ситуация пользователя:\n"
        f"{input_text.strip()}\n\n"
        "Структурированные данные и ограничения:\n"
        f"{json.dumps(context, ensure_ascii=False)}\n\n"
        "Используй только allowed_blocks. "
        "По blocked_blocks напиши безопасные заглушки, что раздел требует ручной проверки."
    )
    return [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]
