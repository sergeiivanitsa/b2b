import json
import logging

import httpx

from gateway_api.settings import Settings

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

logger = logging.getLogger(__name__)


class OpenAIError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        code: str,
        retryable: bool,
        err_type: str,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.retryable = retryable
        self.err_type = err_type


def _retryable_for_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def _extract_error(payload: dict) -> tuple[str, str]:
    # OpenAI error format: {"error": {"message": "...", "type": "...", "code": "..."}}
    err = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(err, dict):
        return ("upstream_error", "upstream_error")
    err_type = err.get("type") or "upstream_error"
    err_code = err.get("code") or err_type
    return (str(err_type), str(err_code))


async def create_chat_completion(
    settings: Settings,
    model: str,
    messages: list[dict],
    timeout_seconds: int | None = None,
) -> tuple[str, dict | None]:
    if not settings.openai_api_key:
        raise OpenAIError(
            status_code=503,
            message="missing OpenAI API key",
            code="missing_api_key",
            retryable=False,
            err_type="gateway_error",
        )

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
    }

    try:
        timeout = timeout_seconds or settings.openai_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(OPENAI_CHAT_URL, json=payload, headers=headers)
    except httpx.TimeoutException:
        raise OpenAIError(
            status_code=502,
            message="upstream timeout",
            code="upstream_timeout",
            retryable=True,
            err_type="upstream_error",
        )
    except httpx.RequestError:
        raise OpenAIError(
            status_code=502,
            message="upstream connection error",
            code="upstream_unavailable",
            retryable=True,
            err_type="upstream_error",
        )

    if resp.status_code != 200:
        err_message = "upstream error"
        err_type = "upstream_error"
        err_code = "upstream_error"
        try:
            payload = resp.json()
            err_type, err_code = _extract_error(payload)
            if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
                err_message = payload["error"].get("message") or err_message
        except ValueError:
            logger.warning("non-json upstream error: %s", resp.text)
        raise OpenAIError(
            status_code=resp.status_code,
            message=err_message,
            code=err_code or err_type,
            retryable=_retryable_for_status(resp.status_code),
            err_type=err_type,
        )

    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise OpenAIError(
            status_code=502,
            message="empty response",
            code="empty_response",
            retryable=True,
            err_type="upstream_error",
        )
    message = choices[0].get("message") or {}
    text = message.get("content")
    if text is None:
        raise OpenAIError(
            status_code=502,
            message="missing content",
            code="missing_content",
            retryable=True,
            err_type="upstream_error",
        )
    usage = data.get("usage")
    return text, usage


async def stream_chat_completion(
    settings: Settings,
    model: str,
    messages: list[dict],
    timeout_seconds: int | None = None,
):
    if not settings.openai_api_key:
        raise OpenAIError(
            status_code=503,
            message="missing OpenAI API key",
            code="missing_api_key",
            retryable=False,
            err_type="gateway_error",
        )

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    timeout = timeout_seconds or settings.openai_timeout_seconds

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", OPENAI_CHAT_URL, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    err_message = "upstream error"
                    err_type = "upstream_error"
                    err_code = "upstream_error"
                    raw = await resp.aread()
                    try:
                        payload = json.loads(raw)
                        err_type, err_code = _extract_error(payload)
                        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
                            err_message = payload["error"].get("message") or err_message
                    except json.JSONDecodeError:
                        logger.warning("non-json upstream error: %s", raw)
                    raise OpenAIError(
                        status_code=resp.status_code,
                        message=err_message,
                        code=err_code or err_type,
                        retryable=_retryable_for_status(resp.status_code),
                        err_type=err_type,
                    )

                buffer_text = ""
                usage = None
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(chunk, dict) and "error" in chunk:
                        err_type, err_code = _extract_error(chunk)
                        err_message = chunk.get("error", {}).get("message", "upstream error")
                        raise OpenAIError(
                            status_code=502,
                            message=err_message,
                            code=err_code or err_type,
                            retryable=True,
                            err_type=err_type,
                        )

                    if isinstance(chunk, dict) and chunk.get("usage"):
                        usage = chunk["usage"]

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    delta_text = delta.get("content")
                    if delta_text:
                        buffer_text += delta_text
                        yield {"type": "delta", "text": delta_text}

                yield {"type": "final", "text": buffer_text, "usage": usage}
    except httpx.TimeoutException:
        raise OpenAIError(
            status_code=502,
            message="upstream timeout",
            code="upstream_timeout",
            retryable=True,
            err_type="upstream_error",
        )
    except httpx.RequestError:
        raise OpenAIError(
            status_code=502,
            message="upstream connection error",
            code="upstream_unavailable",
            retryable=True,
            err_type="upstream_error",
        )
