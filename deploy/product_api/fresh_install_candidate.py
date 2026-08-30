#!/usr/bin/env python3
"""Privacy-safe exact-candidate checks used by the durable fresh installer."""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import re
import sys
from typing import Any


EXPECTED_HEAD = "0020_company_card_narrative_quota_mode"
_SHA = re.compile(r"^[0-9a-f]{40}$")


class CandidateCheckError(RuntimeError):
    pass


def _validate_release_sha(value: str) -> str:
    if _SHA.fullmatch(value) is None:
        raise CandidateCheckError("candidate release identity is invalid; STOP")
    return value


def _settings_contract(
    settings: Any,
    release_sha: str,
    provider_state: str,
    company_card_mode: str,
) -> None:
    admin = settings.superadmin_email or ""
    provider = "enabled" if settings.datanewton_enabled else "disabled"
    key_ok = provider != "enabled" or bool((settings.datanewton_api_key or "").strip())
    common = (
        os.environ.get("PRODUCT_RELEASE_COMMIT") == release_sha,
        provider_state in {"enabled", "disabled"},
        provider == provider_state,
        key_ok,
        bool(admin) and admin == admin.strip() and len(admin) <= 320,
        settings.claims_upload_dir == "/data/claims_uploads",
    )
    default_off = (
        not settings.company_card_v2_presentations_enabled,
        not settings.company_card_v2_writer_enabled,
        not settings.company_card_v2_direct_launch_enabled,
        settings.company_card_v2_rollout_generation == 0,
        settings.company_card_v2_allowlist_inns == [],
        settings.company_card_v2_percentage_basis_points == 0,
        not settings.company_card_v2_arbitration_collection_enabled,
        settings.company_card_v2_arbitration_mask_active_key_id is None,
        settings.company_card_v2_arbitration_mask_keyring_json is None,
        not settings.company_card_v2_narrative_enabled,
        settings.company_card_v2_narrative_kill_switch,
        settings.company_card_v2_narrative_quota_mode == "bounded",
        settings.company_card_v2_narrative_daily_limit == 0,
        settings.company_card_v2_narrative_monthly_limit == 0,
        settings.company_card_v2_narrative_concurrency == 0,
    )
    direct_h2 = (
        settings.company_card_v2_presentations_enabled,
        settings.company_card_v2_writer_enabled,
        settings.company_card_v2_direct_launch_enabled,
        settings.company_card_v2_rollout_generation == 1,
        settings.company_card_v2_allowlist_inns == [],
        settings.company_card_v2_percentage_basis_points == 10000,
        settings.company_card_v2_arbitration_collection_enabled,
        bool(settings.company_card_v2_arbitration_mask_active_key_id),
        settings.company_card_v2_arbitration_mask_keyring_json is not None,
        settings.company_card_v2_narrative_enabled,
        not settings.company_card_v2_narrative_kill_switch,
        settings.company_card_v2_narrative_quota_mode == "unlimited",
        settings.company_card_v2_narrative_daily_limit == 0,
        settings.company_card_v2_narrative_monthly_limit == 0,
        settings.company_card_v2_narrative_concurrency == 1,
    )
    if company_card_mode == "default-off":
        company_card_ok = all(default_off)
    elif company_card_mode == "default-off-or-direct-h2":
        company_card_ok = all(default_off) or all(direct_h2)
    else:
        raise CandidateCheckError("candidate Company Card mode is invalid; STOP")
    if not (all(common) and company_card_ok):
        raise CandidateCheckError("candidate settings contract mismatch; STOP")


def _validate_settings(
    release_sha: str,
    provider_state: str,
    company_card_mode: str,
) -> None:
    try:
        from product_api.settings import get_settings

        settings = get_settings()
        _settings_contract(settings, release_sha, provider_state, company_card_mode)
    except CandidateCheckError:
        raise
    except Exception:
        raise CandidateCheckError("candidate settings could not be validated; STOP") from None


def _validate_alembic_graph() -> None:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(Config("/app/alembic.ini"))
        if tuple(script.get_heads()) != (EXPECTED_HEAD,):
            raise CandidateCheckError("candidate Alembic graph is not exact sole 0020; STOP")
    except CandidateCheckError:
        raise
    except Exception:
        raise CandidateCheckError("candidate Alembic graph could not be validated; STOP") from None


def _provider_state() -> str:
    try:
        from product_api.settings import get_settings

        return "enabled" if get_settings().datanewton_enabled else "disabled"
    except Exception:
        raise CandidateCheckError("provider state could not be validated; STOP") from None


def _legacy_claims_path() -> None:
    try:
        from product_api.settings import get_settings

        path = Path(get_settings().claims_upload_dir)
        valid = (
            path.as_posix() == "/data/claims_uploads"
            and not path.is_symlink()
            and (
                not path.exists()
                or (path.is_dir() and next(path.iterdir(), None) is None)
            )
        )
        if not valid:
            raise CandidateCheckError("legacy Claims path is not exact empty state; STOP")
    except CandidateCheckError:
        raise
    except Exception:
        raise CandidateCheckError("legacy Claims path could not be validated; STOP") from None


async def _signed_gateway(release_sha: str) -> None:
    try:
        import httpx

        from product_api.gateway_client import _sign_headers
        from product_api.settings import get_settings

        settings = get_settings()
        body = b""
        headers = _sign_headers(
            settings.gateway_shared_secret, "POST", "/internal/ping", body
        )
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.gateway_url}/internal/ping",
                content=body,
                headers=headers,
            )
        if response.status_code != 200 or response.json() != {
            "status": "ok",
            "release_commit": release_sha,
        }:
            raise CandidateCheckError("signed exact-Gateway identity mismatch; STOP")
    except CandidateCheckError:
        raise
    except Exception:
        raise CandidateCheckError("signed exact-Gateway check failed; STOP") from None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "settings",
            "alembic",
            "gateway",
            "provider",
            "legacy-claims",
        ),
    )
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--provider-state", choices=("enabled", "disabled"))
    parser.add_argument(
        "--company-card-mode",
        choices=("default-off", "default-off-or-direct-h2"),
    )
    args = parser.parse_args(argv[1:])
    try:
        release_sha = _validate_release_sha(args.release_sha)
        result: str | None = None
        if args.command == "settings":
            if args.provider_state is None or args.company_card_mode is None:
                raise CandidateCheckError(
                    "provider state and Company Card mode are required; STOP"
                )
            _validate_settings(
                release_sha,
                args.provider_state,
                args.company_card_mode,
            )
        elif args.command == "alembic":
            _validate_alembic_graph()
        elif args.command == "gateway":
            asyncio.run(_signed_gateway(release_sha))
        elif args.command == "provider":
            result = _provider_state()
        elif args.command == "legacy-claims":
            _legacy_claims_path()
        if result is not None:
            print(result)
    except CandidateCheckError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("candidate verification failed without details; STOP", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
