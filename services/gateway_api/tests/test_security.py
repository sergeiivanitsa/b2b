from .utils import sign_headers


def test_hmac_valid_and_replay(client):
    secret = "test-shared-secret"
    body = b""
    headers = sign_headers(secret, "POST", "/internal/ping", body)

    resp = client.post("/internal/ping", headers=headers, data=body)
    assert resp.status_code == 200

    replay = client.post("/internal/ping", headers=headers, data=body)
    assert replay.status_code == 409


def test_hmac_invalid_signature(client):
    secret = "test-shared-secret"
    body = b""
    headers = sign_headers(secret, "POST", "/internal/ping", body)
    headers["X-Signature"] = "deadbeef"

    resp = client.post("/internal/ping", headers=headers, data=body)
    assert resp.status_code == 401
