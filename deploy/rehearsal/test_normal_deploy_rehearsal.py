"""Contracts for the executable disposable normal-deploy rehearsal."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "deploy/rehearsal/normal_deploy_rehearsal.py"
SPEC = importlib.util.spec_from_file_location("normal_deploy_rehearsal", MODULE)
assert SPEC and SPEC.loader
rehearsal = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = rehearsal
SPEC.loader.exec_module(rehearsal)


RELEASE_SHA = "1" * 40
PRODUCT_IMAGE = f"sha256:{'a' * 64}"
GATEWAY_IMAGE = f"sha256:{'b' * 64}"
PRODUCT_CONFIG_IMAGE = f"sha256:{'d' * 64}"
GATEWAY_CONFIG_IMAGE = f"sha256:{'e' * 64}"
POSTGRES_IMAGE = "postgres:16.9-alpine@sha256:" + "c" * 64


def _release_root(tmp_path: Path) -> Path:
    root = tmp_path / "release"
    root.mkdir()
    manifest = {
        "release_sha": RELEASE_SHA,
        "pins": {"postgres_image": POSTGRES_IMAGE},
        "images": {
            f"product-api-{RELEASE_SHA}.oci.tar": {
                "oci_digest": PRODUCT_IMAGE,
                "config_digest": PRODUCT_CONFIG_IMAGE,
            },
            f"gateway-api-{RELEASE_SHA}.oci.tar": {
                "oci_digest": GATEWAY_IMAGE,
                "config_digest": GATEWAY_CONFIG_IMAGE,
            },
        },
    }
    (root / f"release-manifest-{RELEASE_SHA}.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return root


def test_release_image_verification_binds_both_loaded_images_to_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _release_root(tmp_path)

    def run(arguments, **kwargs):
        tag = tuple(arguments)[-1]
        return {
            f"b2b-product-api:{RELEASE_SHA}": PRODUCT_IMAGE,
            f"b2b-gateway-api:{RELEASE_SHA}": GATEWAY_IMAGE,
        }[tag]

    monkeypatch.setattr(rehearsal, "_run", run)
    assert rehearsal._verify_release_images(root, RELEASE_SHA, POSTGRES_IMAGE) == (
        PRODUCT_IMAGE,
        GATEWAY_IMAGE,
    )


def test_release_image_verification_accepts_classic_config_store_identities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _release_root(tmp_path)

    def run(arguments, **kwargs):
        tag = tuple(arguments)[-1]
        return {
            f"b2b-product-api:{RELEASE_SHA}": PRODUCT_CONFIG_IMAGE,
            f"b2b-gateway-api:{RELEASE_SHA}": GATEWAY_CONFIG_IMAGE,
        }[tag]

    monkeypatch.setattr(rehearsal, "_run", run)
    assert rehearsal._verify_release_images(root, RELEASE_SHA, POSTGRES_IMAGE) == (
        PRODUCT_CONFIG_IMAGE,
        GATEWAY_CONFIG_IMAGE,
    )


def test_release_image_verification_rejects_loaded_tag_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _release_root(tmp_path)
    monkeypatch.setattr(rehearsal, "_run", lambda *args, **kwargs: f"sha256:{'c' * 64}")

    with pytest.raises(rehearsal.RehearsalError, match="image/manifest identity mismatch"):
        rehearsal._verify_release_images(root, RELEASE_SHA, POSTGRES_IMAGE)


def test_rehearsal_executes_the_exact_shared_controls_and_owned_cleanup() -> None:
    text = MODULE.read_text(encoding="utf-8")
    for token in (
        "WORKER_DRAIN",
        "WORKER_RECOVERY",
        "WORKER_IDENTITY",
        "GATEWAY_IDENTITY",
        '"--validate-only"',
        '"--candidate-release-sha"',
        '"--expected-release-sha"',
        'if test \\"$count\\" -eq 2; then exit 70; fi',
        'if state != "false|no"',
        'recovery_receipt.get("outcome") != "recovered"',
        'drain_receipt.get("outcome") != "drained"',
        '"--compose-override-file"',
        '"    network_mode: host\\n"',
        'f"port={postgres_port}"',
        'str(WORKER_IDENTITY)',
        '"worker_runtime_identity_v1"',
        'label="prior shared worker identity"',
        'label="recovered shared worker identity"',
        'label="candidate shared worker identity"',
        'get("NetworkMode") != "host"',
        '"down", "--remove-orphans"',
        'com.b2b.deploy-rehearsal.run-id=',
    ):
        assert token in text
    for forbidden in (
        "docker system prune",
        "docker container prune",
        "docker image prune",
        "docker build",
        "docker pull",
        "apt-get",
    ):
        assert forbidden not in text


def test_gateway_compose_keeps_literal_production_port() -> None:
    compose = (ROOT / "deploy/us/compose/docker-compose.gateway.yml").read_text(
        encoding="utf-8"
    )
    assert '127.0.0.1:8001:8001' in compose
    assert "GATEWAY_HOST_PORT" not in compose


def test_rehearsal_gateway_copy_changes_only_the_loopback_port(tmp_path: Path) -> None:
    target = tmp_path / "docker-compose.gateway.yml"

    rehearsal._copy_gateway_compose_for_port(
        ROOT / "deploy/us/compose/docker-compose.gateway.yml", target, 49123
    )

    text = target.read_text(encoding="utf-8")
    assert '127.0.0.1:49123:8001' in text
    assert '127.0.0.1:8001:8001' not in text


def test_compose_builders_keep_exact_product_override_and_gateway_file(
    tmp_path: Path,
) -> None:
    product = tmp_path / "docker-compose.product.yml"
    override = tmp_path / "docker-compose.product.rehearsal.yml"
    gateway = tmp_path / "docker-compose.gateway.yml"
    environment_file = tmp_path / ".env"

    product_command = rehearsal._compose(
        project="product_project",
        compose_files=(product, override),
        environment_file=environment_file,
        tail=("ps", "--quiet", "company_report_worker"),
    )
    gateway_command = rehearsal._gateway_compose(
        project="gateway_project",
        compose_file=gateway,
        environment_file=environment_file,
        tail=("ps", "--quiet", "gateway_api"),
    )

    assert product_command[6:10] == ("-f", str(product), "-f", str(override))
    assert gateway_command[4:6] == ("-f", str(gateway))
