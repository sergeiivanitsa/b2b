"""Pre-import credential checks and a default-deny socket/DNS test guard."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
import ipaddress
import os
import re
import socket
from threading import RLock
from typing import Any
from urllib.parse import urlsplit


class TestEnvironmentError(RuntimeError):
    """Raised before application import when inherited test state is unsafe."""


class NetworkAccessDenied(RuntimeError):
    """Raised before a test can resolve or contact an undeclared endpoint."""


_SENSITIVE_CREDENTIALS = (
    "OPENAI_API_KEY",
    "DATANEWTON_API_KEY",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID",
    "COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON",
)
_PRODUCT_PLACEHOLDERS = {
    "GATEWAY_SHARED_SECRET": "test-shared-secret",
    "AUTH_TOKEN_SECRET": "test-auth-secret",
    "CLAIM_EDIT_TOKEN_SECRET": "test-claim-edit-secret",
    "INVITE_TOKEN_SECRET": "test-invite-secret",
    "SESSION_SECRET": "test-session-secret",
}
_GATEWAY_PLACEHOLDERS = {"GATEWAY_SHARED_SECRET": "test-shared-secret"}
_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain"})
_RUNNER_OWNER = "iteration25"
_RUNNER_DATABASE = re.compile(
    r"^(?:i24_guard_|i24_roundtrip_|i25_suite_)(?P<suffix>[0-9a-f]{12})$"
)
_RUNNER_USER = re.compile(r"^i24u(?P<suffix>[0-9a-f]{12})$")
_RUNNER_PASSWORD = re.compile(r"^i25p(?P<run>[0-9a-f]{32})$")


@dataclass(frozen=True, slots=True)
class _Endpoint:
    host: str
    port: int


@dataclass(slots=True)
class _GuardState:
    installed: bool
    allowed_endpoints: set[_Endpoint]


_STATE = _GuardState(installed=False, allowed_endpoints=set())
_LOCK = RLock()
_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_ORIGINAL_GETHOSTBYNAME = socket.gethostbyname
_ORIGINAL_GETHOSTBYNAME_EX = socket.gethostbyname_ex
_ORIGINAL_GETHOSTBYADDR = socket.gethostbyaddr
_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_SENDTO = socket.socket.sendto
_ORIGINAL_CREATE_CONNECTION = socket.create_connection


def _normalized_host(value: object) -> str:
    if isinstance(value, bytes):
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise NetworkAccessDenied("non-ASCII network host is denied") from exc
    if not isinstance(value, str):
        raise NetworkAccessDenied("network host must be a string")
    host = value.strip().lower().rstrip(".")
    if not host or any(character in host for character in "\r\n\x00"):
        raise NetworkAccessDenied("empty or malformed network host is denied")
    return host


def _is_loopback(host: str) -> bool:
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _validate_port(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 65535:
        raise NetworkAccessDenied("network port must be an integer in 1..65535")
    return value


def _is_allowed(host: object, port: object | None = None) -> bool:
    normalized = _normalized_host(host)
    if _is_loopback(normalized):
        if port is not None:
            _validate_port(port)
        return True
    if port is None:
        return any(endpoint.host == normalized for endpoint in _STATE.allowed_endpoints)
    return _Endpoint(normalized, _validate_port(port)) in _STATE.allowed_endpoints


def _require_allowed(host: object, port: object | None = None) -> None:
    if not _is_allowed(host, port):
        raise NetworkAccessDenied("undeclared external network access is denied")


def _guarded_getaddrinfo(host: object, port: object, *args: Any, **kwargs: Any):
    _require_allowed(host, port if isinstance(port, int) else None)
    return _ORIGINAL_GETADDRINFO(host, port, *args, **kwargs)


def _guarded_gethostbyname(host: object) -> str:
    _require_allowed(host)
    return _ORIGINAL_GETHOSTBYNAME(host)


def _guarded_gethostbyname_ex(host: object):
    _require_allowed(host)
    return _ORIGINAL_GETHOSTBYNAME_EX(host)


def _guarded_gethostbyaddr(host: object):
    _require_allowed(host)
    return _ORIGINAL_GETHOSTBYADDR(host)


def _internet_address(sock: socket.socket, address: object) -> tuple[object, object] | None:
    if sock.family not in {socket.AF_INET, socket.AF_INET6}:
        return None
    if not isinstance(address, tuple) or len(address) < 2:
        raise NetworkAccessDenied("malformed internet socket address is denied")
    return address[0], address[1]


def _guarded_connect(sock: socket.socket, address: object):
    endpoint = _internet_address(sock, address)
    if endpoint is not None:
        _require_allowed(*endpoint)
    return _ORIGINAL_CONNECT(sock, address)


def _guarded_connect_ex(sock: socket.socket, address: object):
    endpoint = _internet_address(sock, address)
    if endpoint is not None:
        _require_allowed(*endpoint)
    return _ORIGINAL_CONNECT_EX(sock, address)


def _guarded_sendto(sock: socket.socket, data: bytes, *args: Any):
    if not args:
        return _ORIGINAL_SENDTO(sock, data)
    address = args[-1]
    endpoint = _internet_address(sock, address)
    if endpoint is not None:
        _require_allowed(*endpoint)
    return _ORIGINAL_SENDTO(sock, data, *args)


def _guarded_create_connection(address: object, *args: Any, **kwargs: Any):
    if not isinstance(address, tuple) or len(address) != 2:
        raise NetworkAccessDenied("malformed connection address is denied")
    _require_allowed(address[0], address[1])
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


def _runner_endpoint(environ: Mapping[str, str]) -> _Endpoint | None:
    owner = environ.get("TEST_NETWORK_GUARD_OWNER")
    raw_url = environ.get("TEST_NETWORK_POSTGRES_URL")
    if owner is None and raw_url is None:
        return None
    if owner != _RUNNER_OWNER or not raw_url:
        raise TestEnvironmentError("disposable PostgreSQL network proof is incomplete")
    parsed = urlsplit(raw_url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise TestEnvironmentError("disposable PostgreSQL port is malformed") from exc
    database = parsed.path.removeprefix("/")
    database_match = _RUNNER_DATABASE.fullmatch(database)
    user_match = _RUNNER_USER.fullmatch(parsed.username or "")
    password_match = _RUNNER_PASSWORD.fullmatch(parsed.password or "")
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "postgresql+asyncpg"
        or parsed.query
        or parsed.fragment
        or port is None
        or database_match is None
        or user_match is None
        or password_match is None
        or database_match.group("suffix") != user_match.group("suffix")
        or not password_match.group("run").startswith(database_match.group("suffix"))
        or not _is_loopback(host)
    ):
        raise TestEnvironmentError(
            "TEST_NETWORK_POSTGRES_URL must name the iteration-25 runner database"
        )
    return _Endpoint(host=host, port=port)


def assert_safe_test_environment(
    *,
    suite: str,
    environ: MutableMapping[str, str] | None = None,
) -> _Endpoint | None:
    """Reject inherited credentials and establish exact test placeholders."""

    target = os.environ if environ is None else environ
    if suite not in {"product-unit", "product-integration", "gateway"}:
        raise ValueError("unknown test suite")
    for name in _SENSITIVE_CREDENTIALS:
        if target.get(name, "") != "":
            raise TestEnvironmentError(f"unsafe inherited credential is set: {name}")
    placeholders = (
        _GATEWAY_PLACEHOLDERS if suite == "gateway" else _PRODUCT_PLACEHOLDERS
    )
    for name, expected in placeholders.items():
        current = target.get(name)
        if current is not None and current != expected:
            raise TestEnvironmentError(f"unsafe inherited mandatory secret: {name}")
        target.setdefault(name, expected)
    endpoint = _runner_endpoint(target)
    if suite != "product-integration" and endpoint is not None:
        raise TestEnvironmentError("only Product integration may admit PostgreSQL")
    return endpoint


def install_test_network_guard(*, allowed_postgres: _Endpoint | None = None) -> None:
    """Install a process-wide deny guard; repeated installation is monotonic."""

    with _LOCK:
        if allowed_postgres is not None:
            _STATE.allowed_endpoints.add(allowed_postgres)
        if _STATE.installed:
            return
        socket.getaddrinfo = _guarded_getaddrinfo
        socket.gethostbyname = _guarded_gethostbyname
        socket.gethostbyname_ex = _guarded_gethostbyname_ex
        socket.gethostbyaddr = _guarded_gethostbyaddr
        socket.socket.connect = _guarded_connect
        socket.socket.connect_ex = _guarded_connect_ex
        socket.socket.sendto = _guarded_sendto
        socket.create_connection = _guarded_create_connection
        _STATE.installed = True


def prepare_test_environment(*, suite: str) -> None:
    """Perform the complete pre-import test safety setup."""

    endpoint = assert_safe_test_environment(suite=suite)
    install_test_network_guard(allowed_postgres=endpoint)


def guarded_product_app():
    """Uvicorn factory for the disposable BrowserE2E Product process."""

    prepare_test_environment(suite="product-integration")
    from product_api.main import app

    return app
