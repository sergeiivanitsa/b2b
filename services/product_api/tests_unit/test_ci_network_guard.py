from __future__ import annotations

import asyncio
import socket
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import httpx
import pytest

from tests_support.network_guard import (
    NetworkAccessDenied,
    TestEnvironmentError as UnsafeTestEnvironment,
    assert_safe_test_environment,
)


def _contains_denial(error: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if isinstance(current, NetworkAccessDenied):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def test_raw_dns_and_socket_escape_are_denied() -> None:
    with pytest.raises(NetworkAccessDenied):
        socket.getaddrinfo("example.invalid", 443)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        with pytest.raises(NetworkAccessDenied):
            client.connect(("192.0.2.1", 443))


def test_stdlib_http_escape_is_denied() -> None:
    opener = build_opener(ProxyHandler({}))
    with pytest.raises((NetworkAccessDenied, URLError)) as caught:
        opener.open("http://example.invalid/", timeout=0.1)
    assert _contains_denial(caught.value)


def test_httpx_escape_is_denied() -> None:
    async def attempt() -> None:
        async with httpx.AsyncClient(trust_env=False, timeout=0.1) as client:
            await client.get("http://example.invalid/")

    with pytest.raises((NetworkAccessDenied, httpx.ConnectError)) as caught:
        asyncio.run(attempt())
    assert _contains_denial(caught.value)


def test_loopback_socket_is_allowed() -> None:
    with socket.create_server(("127.0.0.1", 0)) as server:
        host, port = server.getsockname()
        with socket.create_connection((host, port), timeout=1) as client:
            accepted, _address = server.accept()
            accepted.close()
            assert client.getpeername() == (host, port)


def test_inherited_credentials_and_wrong_placeholders_fail_closed() -> None:
    with pytest.raises(UnsafeTestEnvironment, match="OPENAI_API_KEY"):
        assert_safe_test_environment(
            suite="product-unit",
            environ={"OPENAI_API_KEY": "production-secret"},
        )
    with pytest.raises(UnsafeTestEnvironment, match="AUTH_TOKEN_SECRET"):
        assert_safe_test_environment(
            suite="product-unit",
            environ={"AUTH_TOKEN_SECRET": "unexpected"},
        )
    with pytest.raises(UnsafeTestEnvironment, match="SMTP_PASSWORD"):
        assert_safe_test_environment(
            suite="product-unit",
            environ={"SMTP_PASSWORD": " "},
        )


def test_exact_iteration25_disposable_postgres_identity_is_accepted() -> None:
    environ: dict[str, str] = {
        "TEST_NETWORK_GUARD_OWNER": "iteration25",
        "TEST_NETWORK_POSTGRES_URL": (
            "postgresql+asyncpg://i24u0123456789ab:"
            "i25p0123456789ab00000000000000000000@127.0.0.1:55432/"
            "i25_suite_0123456789ab"
        ),
    }
    endpoint = assert_safe_test_environment(
        suite="product-integration", environ=environ
    )
    assert endpoint is not None
    assert (endpoint.host, endpoint.port) == ("127.0.0.1", 55432)


@pytest.mark.parametrize(
    "url",
    (
        "postgresql+asyncpg://i24u0123456789ab:i25p0123456789ab00000000000000000000@example.com:5432/i25_suite_0123456789ab",
        "postgresql+asyncpg://other:i25p0123456789ab00000000000000000000@127.0.0.1:5432/i25_suite_0123456789ab",
        "postgresql+asyncpg://i24u0123456789ab:i25p0123456789ab00000000000000000000@127.0.0.1:5432/production",
        "postgresql+asyncpg://i24u0123456789ab:i25p0123456789ab00000000000000000000@127.0.0.1:5432/i25_suite_ffffffffffff",
        "postgresql+asyncpg://i24u0123456789ab:i25pffffffffffff00000000000000000000@127.0.0.1:5432/i25_suite_0123456789ab",
    ),
)
def test_arbitrary_postgres_identity_is_rejected(url: str) -> None:
    with pytest.raises(UnsafeTestEnvironment, match="runner database"):
        assert_safe_test_environment(
            suite="product-integration",
            environ={
                "TEST_NETWORK_GUARD_OWNER": "iteration25",
                "TEST_NETWORK_POSTGRES_URL": url,
            },
        )
