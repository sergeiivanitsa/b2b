import hashlib
import hmac
import threading
import time

from fastapi import HTTPException, Request, status

from gateway_api.settings import get_settings

SIGNATURE_HEADER = "X-Signature"
TIMESTAMP_HEADER = "X-Timestamp"
NONCE_HEADER = "X-Nonce"
BODY_HASH_HEADER = "X-Body-SHA256"


class NonceCache:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, float] = {}

    def _prune(self, now: float) -> None:
        expired = [nonce for nonce, exp in self._entries.items() if exp <= now]
        for nonce in expired:
            del self._entries[nonce]

    def check_and_store(self, nonce: str, now: float) -> bool:
        with self._lock:
            self._prune(now)
            if nonce in self._entries:
                return False
            self._entries[nonce] = now + self._ttl_seconds
            return True


_settings = get_settings()
_nonce_cache = NonceCache(_settings.gateway_nonce_ttl_seconds)


def _body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _canonical_string(method: str, path: str, timestamp: str, nonce: str, body_hash: str) -> str:
    return "\n".join([method, path, timestamp, nonce, body_hash])


def _path_with_query(request: Request) -> str:
    path = request.url.path
    if request.url.query:
        return f"{path}?{request.url.query}"
    return path


async def verify_gateway_signature(request: Request) -> None:
    signature = request.headers.get(SIGNATURE_HEADER)
    timestamp = request.headers.get(TIMESTAMP_HEADER)
    nonce = request.headers.get(NONCE_HEADER)
    if not signature or not timestamp or not nonce:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing signature headers")

    try:
        timestamp_int = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid timestamp")

    now = int(time.time())
    if abs(now - timestamp_int) > _settings.gateway_clock_skew_seconds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="timestamp out of range")

    body = await request.body()
    body_hash = _body_sha256(body)
    header_body_hash = request.headers.get(BODY_HASH_HEADER)
    if header_body_hash and header_body_hash.lower() != body_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="body hash mismatch")

    canonical = _canonical_string(
        request.method.upper(),
        _path_with_query(request),
        timestamp,
        nonce,
        body_hash,
    )
    expected = hmac.new(
        _settings.gateway_shared_secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

    if not _nonce_cache.check_and_store(nonce, time.time()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="replay detected")
