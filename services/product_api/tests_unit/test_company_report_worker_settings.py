import pytest
from pydantic import SecretStr, ValidationError

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
    assert settings.company_card_v2_direct_launch_enabled is False
    assert settings.company_card_v2_narrative_enabled is False
    assert settings.company_card_v2_narrative_kill_switch is True
    assert settings.company_card_v2_narrative_quota_mode == "bounded"
    assert settings.company_card_v2_narrative_daily_limit == 0
    assert settings.company_card_v2_narrative_monthly_limit == 0
    assert settings.company_card_v2_narrative_concurrency == 0
    assert settings.company_card_v2_narrative_gateway_timeout_seconds == 20
    assert settings.company_card_v2_narrative_max_output_tokens == 600
    assert settings.company_card_v2_arbitration_collection_enabled is False
    assert settings.company_card_v2_arbitration_mask_active_key_id is None
    assert settings.company_card_v2_arbitration_mask_keyring_json is None


def test_arbitration_settings_preserve_unparsed_values_and_mask_keyring_secret() -> None:
    raw_secret = '{"active_key":"private-keyring-marker"}'
    settings = Settings.model_validate(
        _base_settings_payload(
            COMPANY_CARD_V2_ARBITRATION_COLLECTION_ENABLED=True,
            COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID=" active_key ",
            COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON=raw_secret,
        )
    )

    assert settings.company_card_v2_arbitration_collection_enabled is True
    assert settings.company_card_v2_arbitration_mask_active_key_id == " active_key "
    assert isinstance(settings.company_card_v2_arbitration_mask_keyring_json, SecretStr)
    assert (
        settings.company_card_v2_arbitration_mask_keyring_json.get_secret_value()
        == raw_secret
    )
    assert raw_secret not in repr(settings)
    assert raw_secret not in settings.model_dump_json()


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


@pytest.mark.parametrize(
    "overrides",
    [
        {"COMPANY_CARD_AI_NARRATIVE_ENABLED": True},
        {
            "COMPANY_CARD_AI_NARRATIVE_ENABLED": True,
            "COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH": False,
            "COMPANY_CARD_AI_NARRATIVE_DAILY_DISPATCH_CREDITS": 1,
            "COMPANY_CARD_AI_NARRATIVE_MONTHLY_DISPATCH_CREDITS": 1,
            "COMPANY_CARD_AI_NARRATIVE_WORKER_CONCURRENCY": 0,
        },
        {"COMPANY_CARD_AI_NARRATIVE_DAILY_DISPATCH_CREDITS": -1},
        {"COMPANY_CARD_AI_NARRATIVE_MONTHLY_DISPATCH_CREDITS": -1},
        {"COMPANY_CARD_AI_NARRATIVE_WORKER_CONCURRENCY": -1},
    ],
)
def test_narrative_worker_controls_fail_closed(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(_base_settings_payload(**overrides))


def test_narrative_unlimited_mode_uses_zero_calendar_caps_and_positive_backpressure() -> None:
    settings = Settings.model_validate(
        _base_settings_payload(
            COMPANY_CARD_AI_NARRATIVE_ENABLED=True,
            COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH=False,
            COMPANY_CARD_AI_NARRATIVE_QUOTA_MODE="unlimited",
            COMPANY_CARD_AI_NARRATIVE_DAILY_DISPATCH_CREDITS=0,
            COMPANY_CARD_AI_NARRATIVE_MONTHLY_DISPATCH_CREDITS=0,
            COMPANY_CARD_AI_NARRATIVE_WORKER_CONCURRENCY=2,
        )
    )

    assert settings.company_card_v2_narrative_quota_mode == "unlimited"
    assert settings.company_card_v2_narrative_daily_limit == 0
    assert settings.company_card_v2_narrative_monthly_limit == 0
    assert settings.company_card_v2_narrative_concurrency == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "COMPANY_CARD_AI_NARRATIVE_ENABLED": True,
            "COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH": False,
            "COMPANY_CARD_AI_NARRATIVE_QUOTA_MODE": "unlimited",
            "COMPANY_CARD_AI_NARRATIVE_WORKER_CONCURRENCY": 0,
        },
        {
            "COMPANY_CARD_AI_NARRATIVE_QUOTA_MODE": "unlimited",
            "COMPANY_CARD_AI_NARRATIVE_DAILY_DISPATCH_CREDITS": 1,
        },
        {"COMPANY_CARD_AI_NARRATIVE_QUOTA_MODE": "unknown"},
    ],
)
def test_narrative_unlimited_mode_rejects_ambiguous_or_closed_controls(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(_base_settings_payload(**overrides))


def test_direct_h2_launch_requires_global_presentations_and_writer() -> None:
    settings = Settings.model_validate(
        _base_settings_payload(
            COMPANY_CARD_V2_PRESENTATIONS_ENABLED=True,
            COMPANY_CARD_V2_WRITER_ENABLED=True,
            COMPANY_CARD_V2_DIRECT_LAUNCH_ENABLED=True,
            COMPANY_CARD_V2_ROLLOUT_GENERATION=1,
            COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS=10000,
        )
    )

    assert settings.company_card_v2_direct_launch_enabled is True


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"COMPANY_CARD_V2_PRESENTATIONS_ENABLED": True},
        {
            "COMPANY_CARD_V2_PRESENTATIONS_ENABLED": True,
            "COMPANY_CARD_V2_WRITER_ENABLED": True,
            "COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS": 9999,
        },
    ],
)
def test_direct_h2_launch_rejects_partial_activation(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="direct Company Card v2 launch"):
        Settings.model_validate(
            _base_settings_payload(
                COMPANY_CARD_V2_DIRECT_LAUNCH_ENABLED=True,
                COMPANY_CARD_V2_ROLLOUT_GENERATION=1,
                **overrides,
            )
        )


@pytest.mark.parametrize(
    ("timeout", "tokens"),
    [(1, 1), (20, 600)],
)
def test_narrative_gateway_options_accept_exact_closed_boundaries(timeout: int, tokens: int) -> None:
    settings = Settings.model_validate(
        _base_settings_payload(
            COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS=timeout,
            COMPANY_CARD_AI_NARRATIVE_MAX_OUTPUT_TOKENS=tokens,
        )
    )
    assert settings.company_card_v2_narrative_gateway_timeout_seconds == timeout
    assert settings.company_card_v2_narrative_max_output_tokens == tokens


@pytest.mark.parametrize(
    ("timeout", "tokens"),
    [(0, 1), (21, 1), (1, 0), (1, 601)],
)
def test_narrative_gateway_options_reject_outside_boundaries(timeout: int, tokens: int) -> None:
    with pytest.raises(ValidationError, match="out of bounds"):
        Settings.model_validate(
            _base_settings_payload(
                COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS=timeout,
                COMPANY_CARD_AI_NARRATIVE_MAX_OUTPUT_TOKENS=tokens,
            )
        )
