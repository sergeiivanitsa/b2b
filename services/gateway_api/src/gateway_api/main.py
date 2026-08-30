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
from shared.constants import (
    AI_EXPLANATION_MODEL_PROFILE,
    COMPANY_CARD_NARRATIVE_MAX_REQUEST_BYTES,
    COMPANY_CARD_NARRATIVE_MAX_RESPONSE_BYTES,
    COMPANY_CARD_NARRATIVE_MODEL_PROFILE,
    COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME,
    MODEL_GPT_5_2,
)
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
    return {"status": "ok", "release_commit": settings.gateway_release_commit}


@app.post("/v1/chat")
async def chat(payload: ChatRequest, request: Request):
    def _format_sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    if payload.model is not None:
        if payload.model != MODEL_GPT_5_2:
            raise HTTPException(status_code=400, detail="unsupported model")
        # The request validator guarantees legacy metadata is present here.
        logger.info(
            "chat request metadata company_id=%s user_id=%s conversation_id=%s message_id=%s",
            payload.metadata.company_id,
            payload.metadata.user_id,
            payload.metadata.conversation_id,
            payload.metadata.message_id,
        )
        return await _legacy_chat(payload, _format_sse)

    if payload.model_profile == COMPANY_CARD_NARRATIVE_MODEL_PROFILE:
        if len(await request.body()) > COMPANY_CARD_NARRATIVE_MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="narrative request is too large")
        return await _narrative_chat(payload, request)
    if payload.model_profile != AI_EXPLANATION_MODEL_PROFILE:
        raise HTTPException(status_code=400, detail="unsupported model profile")
    # The logging formatter adds request_id. Do not log structured metadata,
    # prompt, schema, model response, or resolved model.
    logger.info("structured chat request model_profile=%s", payload.model_profile)
    try:
        text, usage = await create_chat_completion(
            settings,
            settings.ai_explanation_model,
            [msg.model_dump() for msg in payload.messages],
            payload.timeout,
            response_format=payload.response_format.model_dump(by_alias=True),
            max_output_tokens=payload.max_output_tokens,
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
    response = ChatResponse(
        text=text,
        usage=usage,
        model_profile=payload.model_profile,
        resolved_model=settings.ai_explanation_model,
    )
    # Preserve the byte-level legacy structured response contract.
    payload_data = response.model_dump(mode="json")
    payload_data.pop("gateway_dispatch_id", None)
    return JSONResponse(content=payload_data)


async def _narrative_chat(payload: ChatRequest, request: Request):
    if not settings.company_card_narrative_gateway_enabled:
        raise HTTPException(status_code=503, detail="company card narrative profile is disabled")
    if payload.gateway_dispatch_id is None:
        raise HTTPException(status_code=400, detail="narrative dispatch id is required")
    if request.headers.get("X-Gateway-Dispatch-ID") != str(payload.gateway_dispatch_id):
        raise HTTPException(status_code=400, detail="narrative dispatch id mismatch")
    if payload.response_format is None or payload.response_format.json_schema.name != COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME:
        raise HTTPException(status_code=400, detail="unsupported narrative schema")
    logger.info("narrative structured request model_profile=%s", payload.model_profile)
    try:
        text, usage = await create_chat_completion(settings, settings.company_card_narrative_model, [msg.model_dump() for msg in payload.messages], payload.timeout, response_format=payload.response_format.model_dump(by_alias=True), max_output_tokens=payload.max_output_tokens, reasoning_effort="minimal", require_complete_output=True)
    except OpenAIError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": {"type": exc.err_type, "code": exc.code, "message": exc.message, "retryable": exc.retryable}})
    if len(text.encode("utf-8")) > COMPANY_CARD_NARRATIVE_MAX_RESPONSE_BYTES:
        raise HTTPException(status_code=502, detail="narrative response too large")
    return JSONResponse(content=ChatResponse(
        text=text,
        usage=usage,
        model_profile=payload.model_profile,
        resolved_model=settings.company_card_narrative_model,
        gateway_dispatch_id=payload.gateway_dispatch_id,
    ).model_dump(mode="json"))


async def _legacy_chat(payload: ChatRequest, _format_sse):
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
    response = ChatResponse(text=text, usage=usage)
    payload_data = response.model_dump(mode="json")
    # The optional iteration-21 dispatch field must not alter legacy JSON.
    payload_data.pop("gateway_dispatch_id", None)
    return JSONResponse(content=payload_data)
