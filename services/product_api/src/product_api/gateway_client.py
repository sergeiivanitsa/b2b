import hashlib
import hmac
import json
import time
import uuid

import httpx

from product_api.request_id import get_request_id_header
from product_api.settings import Settings
from shared.schemas import ChatRequest, ChatResponse

SIGNATURE_HEADER = "X-Signature"
TIMESTAMP_HEADER = "X-Timestamp"
NONCE_HEADER = "X-Nonce"
BODY_HASH_HEADER = "X-Body-SHA256"


class GatewayError(Exception):
    pass


def _body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _canonical_string(method: str, path: str, timestamp: str, nonce: str, body_hash: str) -> str:
    return "\n".join([method, path, timestamp, nonce, body_hash])


def _sign_headers(secret: str, method: str, path: str, body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    body_hash = _body_sha256(body)
    canonical = _canonical_string(method.upper(), path, timestamp, nonce, body_hash)
    signature = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        SIGNATURE_HEADER: signature,
        TIMESTAMP_HEADER: timestamp,
        NONCE_HEADER: nonce,
        BODY_HASH_HEADER: body_hash,
    }


async def send_chat(settings: Settings, payload: ChatRequest) -> ChatResponse:
    path = "/v1/chat"
    url = f"{settings.gateway_url}{path}"
    body = json.dumps(payload.model_dump(), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = _sign_headers(settings.gateway_shared_secret, "POST", path, body)
    headers.update(get_request_id_header())
    headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=settings.gateway_timeout_seconds) as client:
        resp = await client.post(url, content=body, headers=headers)

    if resp.status_code != 200:
        raise GatewayError(f"gateway status {resp.status_code}")

    return ChatResponse.model_validate(resp.json())


async def stream_chat(settings: Settings, payload: ChatRequest):
    path = "/v1/chat"
    url = f"{settings.gateway_url}{path}"
    body = json.dumps(payload.model_dump(), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = _sign_headers(settings.gateway_shared_secret, "POST", path, body)
    headers.update(get_request_id_header())
    headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=settings.gateway_timeout_seconds) as client:
        async with client.stream("POST", url, content=body, headers=headers) as resp:
            if resp.status_code != 200:
                text = await resp.aread()
                raise GatewayError(f"gateway status {resp.status_code}: {text.decode('utf-8', 'ignore')}")

            event_name = None
            data_lines: list[str] = []
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                    continue
                if line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
                    continue
                if line == "":
                    if event_name and data_lines:
                        data_str = "\n".join(data_lines)
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            data = {"raw": data_str}
                        yield event_name, data
                    event_name = None
                    data_lines = []
            if event_name and data_lines:
                data_str = "\n".join(data_lines)
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    data = {"raw": data_str}
                yield event_name, data
