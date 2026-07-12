import hashlib
import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import httpx

from product_api.providers.datanewton import DataNewtonClient
from product_api.settings import Settings
from product_api.tools.datanewton_probe import main

IDENTIFIER = "7701234567"
IP_IDENTIFIER = "500100000001"
API_SECRET = "LOCAL_MOCK_SECRET_VALUE"
FIXED_NOW = datetime(2026, 7, 12, 6, 30, tzinfo=timezone.utc)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "DATABASE_URL": "postgresql+asyncpg://app:app@postgres:5432/app",
        "GATEWAY_URL": "http://gateway_api:8001",
        "GATEWAY_SHARED_SECRET": "test-shared-secret",
        "AUTH_TOKEN_SECRET": "test-auth-secret",
        "CLAIM_EDIT_TOKEN_SECRET": "test-claim-edit-secret",
        "CLAIMS_UPLOAD_DIR": "C:/tmp/claims",
        "INVITE_TOKEN_SECRET": "test-invite-secret",
        "SESSION_SECRET": "test-session-secret",
        "EMAIL_FROM": "no-reply@example.com",
        "DATANEWTON_ENABLED": True,
        "DATANEWTON_API_KEY": API_SECRET,
        "DATANEWTON_RETRY_COUNT": 0,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def _run_id(identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:12]
    return f"20260712T063000Z_{digest}"


def _read_json(path: Path):
    return json.loads(path.read_text("utf-8"))


def test_live_mock_writes_manifest_meta_raw_and_shape_for_all_datasets(tmp_path):
    requests: list[httpx.Request] = []
    payloads = {
        "/v1/counterparty": {"company": {"inn": IDENTIFIER, "name": "Private Co"}},
        "/v1/finance": {"balances": [{"code": "Private Code", "value": 999}]},
        "/v1/batchCards": {"cards": [{"inn": IDENTIFIER, "name": "Private Co"}]},
        "/v1/taxInfo": {"paid_taxes": [{"amount": 12345}]},
        "/v1/arbitration-cases": {"cases": [{"number": "PRIVATE-CASE"}]},
        "/v1/fssp": {"items": [{"department": "Private Department"}]},
        "/v1/bankruptcy": {"messages": [{"type_name": "Private Type"}]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.params["key"] == API_SECRET
        if request.url.path == "/v1/counterparty":
            assert request.url.params["filters"] == "MANAGER_BLOCK,ADDRESS_BLOCK"
        return httpx.Response(
            200,
            json=payloads[request.url.path],
            headers={"X-RateLimit-Remaining": "15"},
        )

    settings = _settings()
    output = StringIO()
    error = StringIO()
    exit_code = main(
        [
            "--identifier",
            IDENTIFIER,
            "--datasets",
            "all",
            "--detail-limit",
            "20",
            "--confirm-live",
            "--output-dir",
            str(tmp_path),
        ],
        settings_factory=lambda: settings,
        client_factory=lambda current: DataNewtonClient(
            current, http_transport=httpx.MockTransport(handler)
        ),
        stdout=output,
        stderr=error,
        now_factory=lambda: FIXED_NOW,
    )

    assert exit_code == 0
    assert error.getvalue() == ""
    assert len(requests) == 7
    assert [request.url.path for request in requests] == list(payloads)
    assert IDENTIFIER not in output.getvalue()
    assert API_SECRET not in output.getvalue()
    for private_value in ("Private Co", "PRIVATE-CASE", "Private Department"):
        assert private_value not in output.getvalue()

    run_directory = tmp_path / _run_id(IDENTIFIER)
    manifest = _read_json(run_directory / "manifest.json")
    assert manifest["planned_requests"] == 7
    assert manifest["completed_requests"] == 7
    assert manifest["successful_requests"] == 7
    assert manifest["failed_requests"] == 0
    assert manifest["masked_identifier"] == "********67"

    for dataset in (
        "counterparty",
        "finance",
        "batch_cards",
        "tax_info",
        "arbitration",
        "fssp",
        "bankruptcy",
    ):
        dataset_directory = run_directory / dataset
        meta = _read_json(dataset_directory / "meta.json")
        raw = _read_json(dataset_directory / "raw.json")
        shape = _read_json(dataset_directory / "shape.json")
        assert meta["status"] == "success"
        assert meta["raw_file"] == "raw.json"
        assert meta["shape_file"] == "shape.json"
        assert raw == payloads[meta["endpoint"]]
        assert shape["type"] == "object"

    all_json_paths = list(run_directory.rglob("*.json"))
    for path in all_json_paths:
        contents = path.read_text("utf-8")
        assert API_SECRET not in contents
        if path.name != "raw.json":
            assert IDENTIFIER not in contents
            assert "Private Co" not in contents
            assert "PRIVATE-CASE" not in contents
    assert list(run_directory.rglob("*.tmp")) == []


def test_access_denied_is_partial_safe_and_other_datasets_continue(tmp_path):
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/v1/taxInfo":
            return httpx.Response(403, text="unsafe provider response body")
        return httpx.Response(200, json={"ok": True})

    settings = _settings()
    exit_code = main(
        [
            "--identifier",
            IDENTIFIER,
            "--confirm-live",
            "--output-dir",
            str(tmp_path),
        ],
        settings_factory=lambda: settings,
        client_factory=lambda current: DataNewtonClient(
            current, http_transport=httpx.MockTransport(handler)
        ),
        stdout=StringIO(),
        stderr=StringIO(),
        now_factory=lambda: FIXED_NOW,
    )

    assert exit_code == 2
    assert len(requests) == 7
    run_directory = tmp_path / _run_id(IDENTIFIER)
    manifest = _read_json(run_directory / "manifest.json")
    assert manifest["completed_requests"] == 7
    assert manifest["successful_requests"] == 6
    assert manifest["failed_requests"] == 1
    tax_directory = run_directory / "tax_info"
    tax_meta = _read_json(tax_directory / "meta.json")
    assert tax_meta["status"] == "error"
    assert tax_meta["safe_error_type"] == "DataNewtonAccessDeniedError"
    assert tax_meta["status_code"] == 403
    assert tax_meta["identifier_type"] == "legal_entity_inn"
    assert tax_meta["endpoint"] == "/v1/taxInfo"
    assert tax_meta["dataset"] == "tax_info"
    assert tax_meta["retryable"] is False
    assert (tax_directory / "raw.json").exists() is False
    assert (tax_directory / "shape.json").exists() is False
    serialized_tax_meta = json.dumps(tax_meta)
    assert "unsafe provider response body" not in serialized_tax_meta
    assert IDENTIFIER not in serialized_tax_meta
    assert API_SECRET not in serialized_tax_meta
    assert tax_meta["attempts"] == 1
    assert tax_meta["duration_ms"] >= 0
    assert tax_meta["request_id"] == _run_id(IDENTIFIER)
    assert (run_directory / "bankruptcy" / "raw.json").is_file()


def test_fssp_unsupported_skips_http_without_failing_probe(tmp_path):
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    settings = _settings()
    exit_code = main(
        [
            "--identifier",
            IP_IDENTIFIER,
            "--confirm-live",
            "--output-dir",
            str(tmp_path),
        ],
        settings_factory=lambda: settings,
        client_factory=lambda current: DataNewtonClient(
            current, http_transport=httpx.MockTransport(handler)
        ),
        stdout=StringIO(),
        stderr=StringIO(),
        now_factory=lambda: FIXED_NOW,
    )

    assert exit_code == 0
    assert len(requests) == 6
    assert "/v1/fssp" not in requests
    run_directory = tmp_path / _run_id(IP_IDENTIFIER)
    fssp_meta = _read_json(run_directory / "fssp" / "meta.json")
    manifest = _read_json(run_directory / "manifest.json")
    assert fssp_meta["status"] == "unsupported"
    assert (run_directory / "fssp" / "raw.json").exists() is False
    assert manifest["planned_requests"] == 6
    assert manifest["completed_requests"] == 6
    assert manifest["successful_requests"] == 6
    assert manifest["failed_requests"] == 0


def test_existing_run_directory_is_not_overwritten(tmp_path):
    run_directory = tmp_path / _run_id(IDENTIFIER)
    run_directory.mkdir()
    sentinel = run_directory / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    settings = _settings()
    exit_code = main(
        [
            "--identifier",
            IDENTIFIER,
            "--confirm-live",
            "--output-dir",
            str(tmp_path),
        ],
        settings_factory=lambda: settings,
        client_factory=lambda current: DataNewtonClient(
            current, http_transport=httpx.MockTransport(handler)
        ),
        stdout=StringIO(),
        stderr=StringIO(),
        now_factory=lambda: FIXED_NOW,
    )

    assert exit_code == 5
    assert called is False
    assert sentinel.read_text("utf-8") == "keep"


def test_filesystem_error_returns_code_5_without_http(tmp_path):
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("occupied", encoding="utf-8")
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    settings = _settings()
    exit_code = main(
        [
            "--identifier",
            IDENTIFIER,
            "--confirm-live",
            "--output-dir",
            str(output_file),
        ],
        settings_factory=lambda: settings,
        client_factory=lambda current: DataNewtonClient(
            current, http_transport=httpx.MockTransport(handler)
        ),
        stdout=StringIO(),
        stderr=StringIO(),
        now_factory=lambda: FIXED_NOW,
    )

    assert exit_code == 5
    assert called is False
