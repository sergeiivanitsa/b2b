from io import StringIO

import pytest

from product_api.settings import Settings
from product_api.tools.datanewton_probe import main, mask_identifier


IDENTIFIER = "7701234567"


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
        "DATANEWTON_ENABLED": False,
        "DATANEWTON_API_KEY": None,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def _must_not_load_settings() -> Settings:
    raise AssertionError("dry-run must not load live settings")


def test_without_confirm_live_is_safe_plan_and_creates_no_directory(tmp_path):
    output = StringIO()
    error = StringIO()
    output_dir = tmp_path / "probes"

    exit_code = main(
        ["--identifier", IDENTIFIER, "--output-dir", str(output_dir)],
        settings_factory=_must_not_load_settings,
        stdout=output,
        stderr=error,
    )

    assert exit_code == 0
    assert output_dir.exists() is False
    assert "Mode: DRY-RUN" in output.getvalue()
    assert "No HTTP requests were executed." in output.getvalue()
    assert IDENTIFIER not in output.getvalue()
    assert error.getvalue() == ""


def test_dry_run_overrides_confirm_live(tmp_path):
    output_dir = tmp_path / "probes"
    output = StringIO()

    exit_code = main(
        [
            "--identifier",
            IDENTIFIER,
            "--confirm-live",
            "--dry-run",
            "--output-dir",
            str(output_dir),
        ],
        settings_factory=_must_not_load_settings,
        stdout=output,
        stderr=StringIO(),
    )

    assert exit_code == 0
    assert output_dir.exists() is False
    assert "Mode: DRY-RUN" in output.getvalue()


def test_dry_run_plan_lists_correct_methods_and_endpoints():
    output = StringIO()

    exit_code = main(
        ["--identifier", IDENTIFIER, "--datasets", "all", "--dry-run"],
        settings_factory=_must_not_load_settings,
        stdout=output,
        stderr=StringIO(),
    )

    plan = output.getvalue()
    assert exit_code == 0
    assert "counterparty | GET | /v1/counterparty" in plan
    assert "finance | GET | /v1/finance" in plan
    assert "batch_cards | POST | /v1/batchCards" in plan
    assert "tax_info | GET | /v1/taxInfo" in plan
    assert "arbitration | GET | /v1/arbitration-cases" in plan
    assert "fssp | POST | /v1/fssp" in plan
    assert "bankruptcy | GET | /v1/bankruptcy" in plan
    assert "Planned HTTP requests: 7" in plan


@pytest.mark.parametrize(
    "arguments",
    [
        ["--identifier", IDENTIFIER, "--datasets", "unknown"],
        ["--identifier", "123"],
        ["--identifier", IDENTIFIER, "--detail-limit", "0"],
        ["--identifier", IDENTIFIER, "--detail-limit", "1001"],
        ["--identifier", IDENTIFIER, "--detail-limit", "not-a-number"],
    ],
)
def test_invalid_cli_input_returns_code_3_without_echoing_identifier(arguments):
    output = StringIO()
    error = StringIO()

    exit_code = main(arguments, stdout=output, stderr=error)

    assert exit_code == 3
    assert IDENTIFIER not in output.getvalue()
    assert IDENTIFIER not in error.getvalue()


def test_mask_identifier_preserves_only_two_digit_suffix():
    assert mask_identifier(IDENTIFIER) == "********67"
    assert mask_identifier("304500000000001") == "*************01"


def test_missing_live_configuration_returns_code_4_without_secrets(tmp_path):
    output = StringIO()
    error = StringIO()
    secret_marker = "CONFIG_SECRET_MUST_NOT_APPEAR"

    exit_code = main(
        [
            "--identifier",
            IDENTIFIER,
            "--confirm-live",
            "--output-dir",
            str(tmp_path / "probes"),
        ],
        settings_factory=lambda: _settings(DATANEWTON_API_KEY=secret_marker),
        stdout=output,
        stderr=error,
    )

    combined = output.getvalue() + error.getvalue()
    assert exit_code == 4
    assert secret_marker not in combined
    assert IDENTIFIER not in combined
    assert (tmp_path / "probes").exists() is False
