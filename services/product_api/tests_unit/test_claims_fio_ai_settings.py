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


def test_claims_fio_ai_safe_defaults():
    settings = Settings.model_validate(_base_settings_payload())

    assert settings.claims_fio_ai_enabled is False
    assert settings.claims_fio_ai_model == "gpt-5.2"
    assert settings.claims_fio_ai_prompt_version == "v1"
    assert settings.claims_fio_ai_timeout_seconds == 10
    assert settings.claims_fio_ai_cache_ttl_seconds == 86400
    assert settings.claims_fio_ai_negative_cache_ttl_seconds == 300


@pytest.mark.parametrize("timeout_value", [0, -1])
def test_claims_fio_ai_invalid_timeout(timeout_value: int):
    with pytest.raises(ValidationError, match="CLAIMS_FIO_AI_TIMEOUT_SECONDS must be > 0"):
        Settings.model_validate(
            _base_settings_payload(
                CLAIMS_FIO_AI_TIMEOUT_SECONDS=timeout_value,
            )
        )


@pytest.mark.parametrize(
    ("field_name", "error_message"),
    [
        ("CLAIMS_FIO_AI_CACHE_TTL_SECONDS", "CLAIMS_FIO_AI_CACHE_TTL_SECONDS must be >= 0"),
        (
            "CLAIMS_FIO_AI_NEGATIVE_CACHE_TTL_SECONDS",
            "CLAIMS_FIO_AI_NEGATIVE_CACHE_TTL_SECONDS must be >= 0",
        ),
    ],
)
def test_claims_fio_ai_invalid_cache_ttl(field_name: str, error_message: str):
    with pytest.raises(ValidationError, match=error_message):
        Settings.model_validate(
            _base_settings_payload(
                **{field_name: -1},
            )
        )


def test_claims_fio_ai_empty_model_is_rejected():
    with pytest.raises(ValidationError, match="CLAIMS_FIO_AI_MODEL must not be empty"):
        Settings.model_validate(
            _base_settings_payload(
                CLAIMS_FIO_AI_MODEL="   ",
            )
        )


@pytest.mark.parametrize(
    "prompt_version",
    [
        "v 1",
        "v/1",
    ],
)
def test_claims_fio_ai_invalid_prompt_version(prompt_version: str):
    with pytest.raises(
        ValidationError,
        match=r"CLAIMS_FIO_AI_PROMPT_VERSION must match \[A-Za-z0-9_.-\]\{1,32\}",
    ):
        Settings.model_validate(
            _base_settings_payload(
                CLAIMS_FIO_AI_PROMPT_VERSION=prompt_version,
            )
        )


def test_openai_api_key_guard_remains_intact():
    with pytest.raises(ValidationError, match="OPENAI_API_KEY must not be set in product_api"):
        Settings.model_validate(
            _base_settings_payload(
                OPENAI_API_KEY="sk-test",
            )
        )

