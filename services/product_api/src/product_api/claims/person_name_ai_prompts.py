from __future__ import annotations

import json
from typing import Literal

from shared.schemas import ChatMessage

TargetCase = Literal["genitive", "dative"]
EntityKind = Literal["legal_entity", "individual_entrepreneur", "unknown"]


def build_person_name_ai_messages(
    *,
    fio: str,
    target_case: TargetCase,
    entity_kind: EntityKind,
    strip_ip_prefix: bool,
    prompt_version: str,
) -> list[ChatMessage]:
    system_prompt = (
        "Ты преобразуешь только ФИО в нужный падеж. "
        "Верни только JSON-объект вида {\"fio\":\"...\"}. "
        "Без markdown, без пояснений, без дополнительных ключей."
    )
    payload = {
        "task": "person_name_case_transform",
        "prompt_version": prompt_version,
        "input": {
            "fio": fio,
            "target_case": target_case,
            "entity_kind": entity_kind,
            "strip_ip_prefix": strip_ip_prefix,
        },
        "output_schema": {"fio": "string"},
    }
    return [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
    ]

