from product_api.gateway_client import send_chat
from product_api.settings import Settings
from shared.constants import MODEL_GPT_5_2
from shared.schemas import ChatMessage, ChatMetadata, ChatRequest


async def request_claim_extraction(
    settings: Settings,
    *,
    claim_id: int,
    messages: list[ChatMessage],
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
