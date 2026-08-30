from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_SRC = ROOT / "services/product_api/src"
sys.path.insert(0, str(PRODUCT_SRC))

from deploy.product_api import company_card_v2_activation as activation
from product_api.company_reports.company_card_v2.arbitration_keyring import (
    resolve_arbitration_mask_secret_bytes,
)


SHA = "a" * 40


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o640)


def _values(path: Path) -> dict[str, str]:
    _, values = activation._parse_environment(path.read_bytes())
    return values


def test_product_apply_is_atomic_global_h2_unlimited_ai_and_restorable(tmp_path: Path) -> None:
    environment = tmp_path / ".env.product"
    backup = tmp_path / "product.before"
    receipt = tmp_path / "product.receipt.json"
    durable_mask = tmp_path / "product.mask.json"
    original = (
        "APP_ENV=prod\n"
        "DATANEWTON_ENABLED=true\n"
        "DATANEWTON_API_KEY=server-provider-secret\n"
    )
    _write(environment, original)

    activation.prepare_mask(environment, durable_mask)
    activation.apply(
        "product",
        environment,
        backup,
        receipt,
        SHA,
        durable_mask,
    )

    values = _values(environment)
    assert values["DATANEWTON_ENABLED"] == "true"
    assert values["COMPANY_CARD_V2_PRESENTATIONS_ENABLED"] == "true"
    assert values["COMPANY_CARD_V2_WRITER_ENABLED"] == "true"
    assert values["COMPANY_CARD_V2_DIRECT_LAUNCH_ENABLED"] == "true"
    assert values["COMPANY_CARD_V2_ROLLOUT_GENERATION"] == "1"
    assert values["COMPANY_CARD_V2_ALLOWLIST_INNS"] == ""
    assert values["COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS"] == "10000"
    assert values["COMPANY_CARD_V2_ARBITRATION_COLLECTION_ENABLED"] == "true"
    assert values["COMPANY_CARD_AI_NARRATIVE_ENABLED"] == "true"
    assert values["COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH"] == "false"
    assert values["COMPANY_CARD_AI_NARRATIVE_QUOTA_MODE"] == "unlimited"
    assert values["COMPANY_CARD_AI_NARRATIVE_DAILY_DISPATCH_CREDITS"] == "0"
    assert values["COMPANY_CARD_AI_NARRATIVE_MONTHLY_DISPATCH_CREDITS"] == "0"
    assert values["COMPANY_CARD_AI_NARRATIVE_WORKER_CONCURRENCY"] == "1"
    active = values["COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID"]
    keyring = json.loads(values["COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON"])
    assert active == "production_v1"
    assert "=" not in keyring[active]
    assert resolve_arbitration_mask_secret_bytes(
        key_id=active,
        keyring_json=SecretStr(values["COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON"]),
    ) is not None
    assert backup.read_text(encoding="utf-8") == original
    assert "production_v1" not in receipt.read_text(encoding="utf-8")
    durable_before_rollback = durable_mask.read_bytes()

    activation.verify("product", environment)
    activation.restore("product", environment, backup, receipt, SHA)
    assert environment.read_text(encoding="utf-8") == original
    assert durable_mask.read_bytes() == durable_before_rollback

    activation.prepare_mask(environment, durable_mask)
    activation.apply(
        "product",
        environment,
        tmp_path / "product.retry.before",
        tmp_path / "product.retry.receipt.json",
        SHA,
        durable_mask,
    )
    retry_values = _values(environment)
    assert retry_values["COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID"] == active
    assert retry_values["COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON"] == values[
        "COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON"
    ]


def test_product_apply_preserves_existing_valid_mask_key(tmp_path: Path) -> None:
    environment = tmp_path / ".env.product"
    material = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode("ascii")
    keyring = json.dumps({"kms_v7": material}, separators=(",", ":"))
    _write(
        environment,
        "APP_ENV=prod\n"
        "DATANEWTON_ENABLED=true\n"
        "DATANEWTON_API_KEY=server-provider-secret\n"
        "COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID=kms_v7\n"
        f"COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON={keyring}\n",
    )

    durable_mask = tmp_path / "product.mask.json"
    activation.prepare_mask(environment, durable_mask)
    activation.apply(
        "product",
        environment,
        tmp_path / "before",
        tmp_path / "receipt",
        SHA,
        durable_mask,
    )

    values = _values(environment)
    assert values["COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID"] == "kms_v7"
    assert json.loads(values["COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON"]) == {"kms_v7": material}
    assert resolve_arbitration_mask_secret_bytes(
        key_id="kms_v7",
        keyring_json=SecretStr(values["COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON"]),
    ) == b"x" * 32


def test_prepare_mask_rejects_different_existing_durable_identity(tmp_path: Path) -> None:
    environment = tmp_path / ".env.product"
    durable_mask = tmp_path / "product.mask.json"
    _write(
        environment,
        "DATANEWTON_ENABLED=true\nDATANEWTON_API_KEY=server-provider-secret\n",
    )
    activation.prepare_mask(environment, durable_mask)
    first = durable_mask.read_bytes()

    material = base64.urlsafe_b64encode(b"z" * 32).rstrip(b"=").decode("ascii")
    keyring = json.dumps({"kms_v7": material}, separators=(",", ":"))
    _write(
        environment,
        "DATANEWTON_ENABLED=true\n"
        "DATANEWTON_API_KEY=server-provider-secret\n"
        "COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID=kms_v7\n"
        f"COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON={keyring}\n",
    )
    with pytest.raises(activation.ActivationError, match="identities differ"):
        activation.prepare_mask(environment, durable_mask)
    assert durable_mask.read_bytes() == first


@pytest.mark.parametrize(
    ("key_id", "encoded"),
    (
        ("UPPER", base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode("ascii")),
        ("kms_v7", base64.urlsafe_b64encode(b"x" * 32).decode("ascii")),
        ("kms_v7", base64.urlsafe_b64encode(b"short").rstrip(b"=").decode("ascii")),
    ),
)
def test_product_preflight_rejects_mask_outside_runtime_canonical_contract(
    tmp_path: Path,
    key_id: str,
    encoded: str,
) -> None:
    environment = tmp_path / ".env.product"
    keyring = json.dumps({key_id: encoded}, separators=(",", ":"))
    _write(
        environment,
        "DATANEWTON_ENABLED=true\n"
        "DATANEWTON_API_KEY=server-provider-secret\n"
        f"COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID={key_id}\n"
        f"COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON={keyring}\n",
    )
    with pytest.raises(activation.ActivationError):
        activation.preflight("product", environment)


def test_gateway_apply_requires_credential_and_selects_gpt_5_nano(tmp_path: Path) -> None:
    environment = tmp_path / ".env.gateway"
    _write(environment, "APP_ENV=prod\nOPENAI_API_KEY=server-secret\n")

    activation.preflight("gateway", environment)
    activation.apply(
        "gateway",
        environment,
        tmp_path / "before",
        tmp_path / "receipt",
        SHA,
    )

    values = _values(environment)
    assert values["OPENAI_API_KEY"] == "server-secret"
    assert values["COMPANY_CARD_NARRATIVE_GATEWAY_ENABLED"] == "true"
    assert values["COMPANY_CARD_NARRATIVE_MODEL_PROFILE"] == "company_card_narrative_structured_v1"
    assert values["COMPANY_CARD_NARRATIVE_MODEL"] == "gpt-5-nano"
    assert "server-secret" not in (tmp_path / "receipt").read_text(encoding="utf-8")
    activation.verify("gateway", environment)


def test_gateway_preflight_rejects_blank_openai_key_without_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    environment = tmp_path / ".env.gateway"
    _write(environment, "APP_ENV=prod\nOPENAI_API_KEY=\n")
    with pytest.raises(activation.ActivationError, match="OPENAI_API_KEY"):
        activation.preflight("gateway", environment)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "provider_rows",
    (
        "DATANEWTON_ENABLED=false\nDATANEWTON_API_KEY=server-provider-secret\n",
        "DATANEWTON_ENABLED=true\nDATANEWTON_API_KEY=\n",
    ),
)
def test_product_preflight_requires_live_provider_without_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    provider_rows: str,
) -> None:
    environment = tmp_path / ".env.product"
    _write(environment, "APP_ENV=prod\n" + provider_rows)
    with pytest.raises(activation.ActivationError):
        activation.preflight("product", environment)
    assert capsys.readouterr().out == ""


def test_restore_refuses_to_overwrite_post_activation_change(tmp_path: Path) -> None:
    environment = tmp_path / ".env.gateway"
    backup = tmp_path / "before"
    receipt = tmp_path / "receipt"
    _write(environment, "APP_ENV=prod\nOPENAI_API_KEY=server-secret\n")
    activation.apply("gateway", environment, backup, receipt, SHA)
    environment.write_bytes(environment.read_bytes() + b"MANUAL_CHANGE=yes\n")

    with pytest.raises(activation.ActivationError, match="changed after activation"):
        activation.restore("gateway", environment, backup, receipt, SHA)


def test_restore_receipt_exists_before_mutation_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    environment = tmp_path / ".env.gateway"
    backup = tmp_path / "before"
    receipt = tmp_path / "receipt"
    original = b"APP_ENV=prod\nOPENAI_API_KEY=server-secret\n"
    environment.write_bytes(original)

    def interrupted(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated cancellation before env replace")

    monkeypatch.setattr(activation, "_atomic_replace", interrupted)
    with pytest.raises(RuntimeError, match="simulated cancellation"):
        activation.apply("gateway", environment, backup, receipt, SHA)

    assert backup.read_bytes() == original
    assert receipt.is_file()
    assert environment.read_bytes() == original
    activation.restore("gateway", environment, backup, receipt, SHA)


def test_duplicate_environment_key_is_rejected_before_backup(tmp_path: Path) -> None:
    environment = tmp_path / ".env.product"
    backup = tmp_path / "before"
    _write(environment, "APP_ENV=prod\nAPP_ENV=prod\n")

    with pytest.raises(activation.ActivationError, match="duplicate"):
        activation.apply("product", environment, backup, tmp_path / "receipt", SHA)
    assert not backup.exists()
