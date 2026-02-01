import json
import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from gateway_api.logging_config import configure_logging
from gateway_api.openai_client import OpenAIError, create_chat_completion, stream_chat_completion
from gateway_api.request_id import REQUEST_ID_HEADER, set_request_id
from gateway_api.security import verify_gateway_signature
from gateway_api.settings import get_settings
from shared.constants import MODEL_GPT_5_2
from shared.schemas import ChatRequest, ChatResponse

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Gateway API")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    set_request_id(request_id)
    if settings.app_env.lower() == "prod":
        if request.url.path in ("/docs", "/openapi.json"):
            return JSONResponse(status_code=404, content={"detail": "not found"})
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


@app.middleware("http")
async def gateway_auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/internal") or request.url.path.startswith("/v1"):
        try:
            await verify_gateway_signature(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/internal/ping")
async def internal_ping():
    return {"status": "ok"}


@app.post("/v1/chat")
async def chat(payload: ChatRequest):
    if payload.model != MODEL_GPT_5_2:
        raise HTTPException(status_code=400, detail="unsupported model")

    logger.info(
        "chat request metadata company_id=%s user_id=%s conversation_id=%s message_id=%s",
        payload.metadata.company_id,
        payload.metadata.user_id,
        payload.metadata.conversation_id,
        payload.metadata.message_id,
    )

    def _format_sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    if payload.stream:
        async def event_stream():
            try:
                async for event in stream_chat_completion(
                    settings,
                    payload.model,
                    [msg.model_dump() for msg in payload.messages],
                    payload.timeout,
                ):
                    if event.get("type") == "delta":
                        yield _format_sse("delta", {"text": event.get("text", "")})
                    elif event.get("type") == "final":
                        yield _format_sse(
                            "final",
                            {"text": event.get("text", ""), "usage": event.get("usage")},
                        )
                        return
            except OpenAIError as exc:
                logger.warning("openai error code=%s status=%s", exc.code, exc.status_code)
                yield _format_sse(
                    "error",
                    {
                        "type": exc.err_type,
                        "code": exc.code,
                        "message": exc.message,
                        "retryable": exc.retryable,
                    },
                )
                return

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        text, usage = await create_chat_completion(
            settings,
            payload.model,
            [msg.model_dump() for msg in payload.messages],
            payload.timeout,
        )
    except OpenAIError as exc:
        logger.warning("openai error code=%s status=%s", exc.code, exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "type": exc.err_type,
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                }
            },
        )
    return ChatResponse(text=text, usage=usage)
