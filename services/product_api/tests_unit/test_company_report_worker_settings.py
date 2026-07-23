import pytest
from pydantic import ValidationError

from product_api.settings import Settings


def _base_settings_payload(**overrides):
    payload = {
        "DATABASE_URL": "postgresql+asyncpg://app:app@postgres:5432/app",
        "GATEWAY_URL": "http://gateway_api:8001",
        "GATEWAY_SHARED_SECRET": "test-shared-secret",
        "AUTH_TOKEN_SECRET": "test-auth-secret",
        "CLAIM_EDIT_TOKEN_SECRET": "test-claim-edit-secret",
        "CLAIMS_UPLOAD_DIR": "C:/tmp/claims",
        "INVITE_TOKEN_SECRET": "test-invite-secret",
        "SESSION_SECRET": "test-session-secret",
        "EMAIL_FROM": "no-reply@example.com",
    }
    payload.update(overrides)
    return payload


def test_company_report_worker_settings_have_safe_defaults():
    settings = Settings.model_validate(_base_settings_payload())

    assert settings.company_report_worker_poll_interval_seconds == 1
    assert settings.company_report_worker_lease_seconds == 60
    assert settings.company_report_worker_heartbeat_interval_seconds == 10
    assert settings.company_report_worker_shutdown_grace_seconds == 30


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (
            {"COMPANY_REPORT_WORKER_POLL_INTERVAL_SECONDS": 0},
            "COMPANY_REPORT_WORKER_POLL_INTERVAL_SECONDS must be > 0",
        ),
        (
            {"COMPANY_REPORT_WORKER_LEASE_SECONDS": 0},
            "COMPANY_REPORT_WORKER_LEASE_SECONDS must be > 0",
        ),
        (
            {"COMPANY_REPORT_WORKER_HEARTBEAT_INTERVAL_SECONDS": 0},
            "COMPANY_REPORT_WORKER_HEARTBEAT_INTERVAL_SECONDS must be > 0",
        ),
        (
            {"COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS": -1},
            "COMPANY_REPORT_WORKER_SHUTDOWN_GRACE_SECONDS must be >= 0",
        ),
        (
            {
                "COMPANY_REPORT_WORKER_LEASE_SECONDS": 10,
                "COMPANY_REPORT_WORKER_HEARTBEAT_INTERVAL_SECONDS": 10,
            },
            "must be less than COMPANY_REPORT_WORKER_LEASE_SECONDS",
        ),
    ],
)
def test_company_report_worker_settings_reject_invalid_timing(override, message):
    with pytest.raises(ValidationError, match=message):
        Settings.model_validate(_base_settings_payload(**override))
