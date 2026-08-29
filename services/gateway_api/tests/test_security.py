import pytest

from .utils import sign_headers
from gateway_api.settings import Settings


def test_hmac_valid_and_replay(client):
    secret = "test-shared-secret"
    body = b""
    headers = sign_headers(secret, "POST", "/internal/ping", body)

    resp = client.post("/internal/ping", headers=headers, data=body)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "release_commit": None}

    replay = client.post("/internal/ping", headers=headers, data=body)
    assert replay.status_code == 409


def test_gateway_release_commit_is_optional_or_exact_lowercase_sha():
    assert Settings(GATEWAY_SHARED_SECRET="test").gateway_release_commit is None
    assert (
        Settings(
            GATEWAY_SHARED_SECRET="test", GATEWAY_RELEASE_COMMIT="a" * 40
        ).gateway_release_commit
        == "a" * 40
    )
    for invalid in ("", "A" * 40, "a" * 39, "not-a-sha"):
        if invalid == "":
            assert (
                Settings(
                    GATEWAY_SHARED_SECRET="test", GATEWAY_RELEASE_COMMIT=invalid
                ).gateway_release_commit
                is None
            )
            continue
        with pytest.raises(ValueError):
            Settings(GATEWAY_SHARED_SECRET="test", GATEWAY_RELEASE_COMMIT=invalid)


def test_authenticated_ping_reports_exact_configured_release(client, monkeypatch):
    release_sha = "b" * 40
    monkeypatch.setattr(
        "gateway_api.main.settings.gateway_release_commit", release_sha
    )
    headers = sign_headers(
        "test-shared-secret", "POST", "/internal/ping", b""
    )
    response = client.post("/internal/ping", headers=headers, data=b"")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "release_commit": release_sha}


def test_hmac_invalid_signature(client):
    secret = "test-shared-secret"
    body = b""
    headers = sign_headers(secret, "POST", "/internal/ping", body)
    headers["X-Signature"] = "deadbeef"

    resp = client.post("/internal/ping", headers=headers, data=body)
    assert resp.status_code == 401
