import re
from typing import Any

from product_api.gateway_client import GatewayError, send_chat
from product_api.settings import Settings
from shared.constants import MODEL_GPT_5_2
from shared.schemas import ChatMetadata, ChatRequest

from .prompts import build_preview_generation_messages


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
        normalized_preview_text = _normalize_preview_text(preview_text)
        if not normalized_preview_text:
            raise ValueError("empty preview")
        return {
            "generated_preview_text": normalized_preview_text,
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
    creditor = _safe_str(data.get("creditor_name"), "Кредитор требует уточнения")
    debtor = _safe_str(data.get("debtor_name"), "Должник требует уточнения")
    debt_amount = _safe_str(data.get("debt_amount"), "Сумма долга требует уточнения")
    due_date = _safe_str(data.get("payment_due_date"), "Срок оплаты требует уточнения")
    case_type_label = _safe_str(case_type, "тип спора не определен")
    missing_fields = decision.get("missing_fields") or []
    blocked_blocks = decision.get("blocked_blocks") or []

    lines = [
        "Черновик досудебной претензии",
        "",
        f"Тип спора: {case_type_label}.",
        f"Кредитор: {creditor}.",
        f"Должник: {debtor}.",
        f"Сумма долга: {debt_amount}.",
        f"Срок оплаты: {due_date}.",
        "",
        "Основание требований:",
        "По представленным данным у кредитора есть основания требовать оплату задолженности.",
        "",
        "Требование:",
        "Просим погасить задолженность в добровольном порядке в разумный срок после получения претензии.",
        "",
        "Комментарий по проверке:",
    ]
    if missing_fields:
        lines.append(
            "Нужно уточнить данные: " + ", ".join(str(item) for item in missing_fields) + "."
        )
    if blocked_blocks:
        lines.append(
            "Разделы для ручной проверки юристом: "
            + ", ".join(str(item) for item in blocked_blocks)
            + "."
        )
    if not missing_fields and not blocked_blocks:
        lines.append("Документ сформирован в безопасном режиме и требует финальной юридической проверки.")

    lines.extend(
        [
            "",
            "Исходное описание ситуации:",
            input_text.strip(),
        ]
    )
    return "\n".join(lines).strip()


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


def _normalize_preview_text(raw_text: str | None) -> str:
    if raw_text is None:
        return ""
    candidate = str(raw_text).strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:text|markdown)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    return candidate.strip()


def _safe_str(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    normalized = str(value).strip()
    return normalized if normalized else fallback
