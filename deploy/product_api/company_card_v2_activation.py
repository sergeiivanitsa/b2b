"""Atomic, secret-safe environment activation for Company Card v2 production.

The helper intentionally edits only the two server-local environment files.  It
never prints environment values or secret material.  Runtime recreation and
health checks remain owned by the protected GitHub workflow.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path
from typing import Final


class ActivationError(RuntimeError):
    """Raised when activation cannot be proven safe."""


_SHA_RE: Final = re.compile(r"^[0-9a-f]{40}$")
_KEY_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_ENV_KEY_RE: Final = re.compile(r"^[A-Z][A-Z0-9_]*$")
_BINARY: Final = getattr(os, "O_BINARY", 0)
_MAX_KEYRING_UTF8_BYTES: Final = 8192
_MAX_KEYRING_ENTRIES: Final = 16
_MIN_MASK_SECRET_BYTES: Final = 32
_MAX_MASK_SECRET_BYTES: Final = 64
_DURABLE_MASK_SCHEMA: Final = "company_card_v2_arbitration_mask_v1"

_PRODUCT_STATIC: Final = {
    "COMPANY_CARD_V2_PRESENTATIONS_ENABLED": "true",
    "COMPANY_CARD_V2_WRITER_ENABLED": "true",
    "COMPANY_CARD_V2_DIRECT_LAUNCH_ENABLED": "true",
    "COMPANY_CARD_V2_ROLLOUT_GENERATION": "1",
    "COMPANY_CARD_V2_ALLOWLIST_INNS": "",
    "COMPANY_CARD_V2_PERCENTAGE_BASIS_POINTS": "10000",
    "COMPANY_CARD_V2_ARBITRATION_COLLECTION_ENABLED": "true",
    "COMPANY_CARD_AI_NARRATIVE_ENABLED": "true",
    "COMPANY_CARD_AI_NARRATIVE_KILL_SWITCH": "false",
    "COMPANY_CARD_AI_NARRATIVE_QUOTA_MODE": "unlimited",
    "COMPANY_CARD_AI_NARRATIVE_DAILY_DISPATCH_CREDITS": "0",
    "COMPANY_CARD_AI_NARRATIVE_MONTHLY_DISPATCH_CREDITS": "0",
    # This is worker backpressure, not a spend/quota limit.
    "COMPANY_CARD_AI_NARRATIVE_WORKER_CONCURRENCY": "1",
    "COMPANY_CARD_AI_NARRATIVE_GATEWAY_TIMEOUT_SECONDS": "20",
    "COMPANY_CARD_AI_NARRATIVE_MAX_OUTPUT_TOKENS": "600",
}
_GATEWAY_STATIC: Final = {
    "COMPANY_CARD_NARRATIVE_GATEWAY_ENABLED": "true",
    "COMPANY_CARD_NARRATIVE_MODEL_PROFILE": "company_card_narrative_structured_v1",
    "COMPANY_CARD_NARRATIVE_MODEL": "gpt-5-nano",
}
_MASK_ID = "COMPANY_CARD_V2_ARBITRATION_MASK_ACTIVE_KEY_ID"
_MASK_KEYRING = "COMPANY_CARD_V2_ARBITRATION_MASK_KEYRING_JSON"


def _require_sha(value: str) -> str:
    if _SHA_RE.fullmatch(value) is None:
        raise ActivationError("release SHA must be exact lowercase 40-hex")
    return value


def _regular_absolute(path: Path, *, must_exist: bool) -> os.stat_result | None:
    if not path.is_absolute():
        raise ActivationError("environment and receipt paths must be absolute")
    try:
        info = path.lstat()
    except FileNotFoundError:
        if must_exist:
            raise ActivationError("required file is absent") from None
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ActivationError("path must be a regular nonsymlinked file")
    return info


def _read_bytes(path: Path) -> tuple[bytes, os.stat_result]:
    info = _regular_absolute(path, must_exist=True)
    assert info is not None
    flags = os.O_RDONLY | _BINARY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ActivationError("file identity changed during read")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read()
    finally:
        os.close(descriptor)
    if b"\x00" in payload or b"\r" in payload:
        raise ActivationError("environment file encoding is not canonical")
    return payload, info


def _decode_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def _parse_environment(payload: bytes) -> tuple[list[str], dict[str, str]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ActivationError("environment file must be UTF-8") from exc
    rows = text.splitlines()
    values: dict[str, str] = {}
    for number, row in enumerate(rows, start=1):
        stripped = row.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in row:
            continue
        key, raw = row.split("=", 1)
        key = key.strip()
        if _ENV_KEY_RE.fullmatch(key) is None:
            continue
        if key in values:
            raise ActivationError(f"duplicate environment key at line {number}")
        values[key] = _decode_value(raw)
    return rows, values


def _validate_mask(values: dict[str, str]) -> tuple[str, str] | None:
    active = values.get(_MASK_ID, "")
    raw_keyring = values.get(_MASK_KEYRING, "")
    if not active and not raw_keyring:
        return None
    if not active or not raw_keyring or _KEY_RE.fullmatch(active) is None:
        raise ActivationError("arbitration mask configuration is incomplete")
    if len(raw_keyring.encode("utf-8")) > _MAX_KEYRING_UTF8_BYTES:
        raise ActivationError("arbitration mask keyring is too large")
    try:
        parsed = json.loads(raw_keyring, object_pairs_hook=_unique_json_object)
    except json.JSONDecodeError as exc:
        raise ActivationError("arbitration mask keyring is invalid JSON") from exc
    if (
        not isinstance(parsed, dict)
        or active not in parsed
        or not 1 <= len(parsed) <= _MAX_KEYRING_ENTRIES
    ):
        raise ActivationError("active arbitration mask key is absent")
    canonical: dict[str, str] = {}
    for key, encoded in parsed.items():
        if not isinstance(key, str) or _KEY_RE.fullmatch(key) is None or not isinstance(encoded, str):
            raise ActivationError("arbitration mask keyring shape is invalid")
        try:
            if not encoded or "=" in encoded:
                raise ValueError
            raw = encoded.encode("ascii")
            material = base64.b64decode(
                raw + b"=" * (-len(raw) % 4),
                altchars=b"-_",
                validate=True,
            )
            if base64.urlsafe_b64encode(material).rstrip(b"=").decode("ascii") != encoded:
                raise ValueError
        except (ValueError, UnicodeError, binascii.Error) as exc:
            raise ActivationError("arbitration mask key material is invalid") from exc
        if not _MIN_MASK_SECRET_BYTES <= len(material) <= _MAX_MASK_SECRET_BYTES:
            raise ActivationError("arbitration mask key size is invalid")
        canonical[key] = encoded
    return active, json.dumps(canonical, separators=(",", ":"), sort_keys=True)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ActivationError("arbitration mask keyring contains a duplicate key")
        result[key] = value
    return result


def _require_product_provider(values: dict[str, str]) -> None:
    if values.get("DATANEWTON_ENABLED", "").strip().lower() != "true":
        raise ActivationError("DataNewton provider is disabled; STOP")
    if not values.get("DATANEWTON_API_KEY", "").strip():
        raise ActivationError("DATANEWTON_API_KEY is absent or blank; STOP")


def _durable_mask_payload(active: str, keyring: str) -> bytes:
    return (
        json.dumps(
            {
                "active_key_id": active,
                "keyring_json": keyring,
                "schema_version": _DURABLE_MASK_SCHEMA,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _load_durable_mask(path: Path) -> tuple[str, str]:
    payload, info = _read_bytes(path)
    if os.name != "nt" and stat.S_IMODE(info.st_mode) & 0o077:
        raise ActivationError("durable arbitration mask file permissions are unsafe")
    if len(payload) > _MAX_KEYRING_UTF8_BYTES + 512:
        raise ActivationError("durable arbitration mask file is too large")
    try:
        document = json.loads(payload, object_pairs_hook=_unique_json_object)
    except json.JSONDecodeError as exc:
        raise ActivationError("durable arbitration mask file is invalid JSON") from exc
    if not isinstance(document, dict) or set(document) != {
        "active_key_id",
        "keyring_json",
        "schema_version",
    }:
        raise ActivationError("durable arbitration mask schema mismatch")
    if document.get("schema_version") != _DURABLE_MASK_SCHEMA:
        raise ActivationError("durable arbitration mask schema mismatch")
    active = document.get("active_key_id")
    keyring = document.get("keyring_json")
    if not isinstance(active, str) or not isinstance(keyring, str):
        raise ActivationError("durable arbitration mask shape is invalid")
    validated = _validate_mask({_MASK_ID: active, _MASK_KEYRING: keyring})
    if validated is None:  # pragma: no cover - guarded by the non-empty schema above.
        raise ActivationError("durable arbitration mask is absent")
    return validated


def _write_durable_mask(
    path: Path,
    active: str,
    keyring: str,
    owner: os.stat_result,
) -> None:
    _regular_absolute(path, must_exist=False)
    payload = _durable_mask_payload(active, keyring)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        if hasattr(os, "fchown"):
            os.fchown(descriptor, owner.st_uid, owner.st_gid)
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def prepare_mask(environment_file: Path, durable_mask_file: Path) -> None:
    payload, info = _read_bytes(environment_file)
    _, values = _parse_environment(payload)
    configured = _validate_mask(values)
    durable_info = _regular_absolute(durable_mask_file, must_exist=False)
    if durable_info is not None:
        durable = _load_durable_mask(durable_mask_file)
        if configured is not None and configured != durable:
            raise ActivationError(
                "configured and durable arbitration mask identities differ; STOP"
            )
        return
    if configured is None:
        active = "production_v1"
        encoded = (
            base64.urlsafe_b64encode(secrets.token_bytes(32))
            .rstrip(b"=")
            .decode("ascii")
        )
        configured = (
            active,
            json.dumps({active: encoded}, separators=(",", ":"), sort_keys=True),
        )
    try:
        _write_durable_mask(durable_mask_file, *configured, info)
    except FileExistsError:
        durable = _load_durable_mask(durable_mask_file)
        if durable != configured:
            raise ActivationError(
                "concurrent durable arbitration mask identity differs; STOP"
            ) from None


def _desired(
    role: str,
    values: dict[str, str],
    durable_mask_file: Path | None = None,
) -> dict[str, str]:
    if role == "gateway":
        if not values.get("OPENAI_API_KEY", "").strip():
            raise ActivationError("OPENAI_API_KEY is absent or blank; STOP")
        return dict(_GATEWAY_STATIC)
    if role != "product":
        raise ActivationError("unsupported activation role")
    _require_product_provider(values)
    mask = _validate_mask(values)
    if mask is None:
        if durable_mask_file is None:
            raise ActivationError("durable arbitration mask identity is required; STOP")
        active, keyring = _load_durable_mask(durable_mask_file)
    else:
        active, keyring = mask
        if durable_mask_file is not None:
            durable = _load_durable_mask(durable_mask_file)
            if durable != mask:
                raise ActivationError(
                    "configured and durable arbitration mask identities differ; STOP"
                )
    return {**_PRODUCT_STATIC, _MASK_ID: active, _MASK_KEYRING: keyring}


def _render(rows: list[str], desired: dict[str, str]) -> bytes:
    rendered: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if "=" in row:
            candidate = row.split("=", 1)[0].strip()
            if candidate in desired:
                rendered.append(f"{candidate}={desired[candidate]}")
                seen.add(candidate)
                continue
        rendered.append(row)
    if rendered and rendered[-1] != "":
        rendered.append("")
    for key in sorted(desired):
        if key not in seen:
            rendered.append(f"{key}={desired[key]}")
    return ("\n".join(rendered).rstrip("\n") + "\n").encode("utf-8")


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":  # Directory handles are not openable through os.open on Windows.
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _exclusive_copy(path: Path, payload: bytes, info: os.stat_result) -> None:
    _regular_absolute(path, must_exist=False)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, stat.S_IMODE(info.st_mode))
    try:
        if hasattr(os, "fchown"):
            os.fchown(descriptor, info.st_uid, info.st_gid)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _atomic_replace(path: Path, payload: bytes, info: os.stat_result) -> None:
    descriptor, temporary_raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_raw)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, stat.S_IMODE(info.st_mode))
        else:
            os.chmod(temporary, stat.S_IMODE(info.st_mode))
        if hasattr(os, "fchown"):
            os.fchown(descriptor, info.st_uid, info.st_gid)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_receipt(
    path: Path,
    *,
    role: str,
    release_sha: str,
    environment_file: Path,
    before: bytes,
    after: bytes,
) -> None:
    _regular_absolute(path, must_exist=False)
    receipt = {
        "after_sha256": _hash(after),
        "before_sha256": _hash(before),
        "environment_file": str(environment_file),
        "release_sha": release_sha,
        "role": role,
        "schema_version": "company_card_v2_activation_v1",
    }
    encoded = (json.dumps(receipt, separators=(",", ":"), sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _load_receipt(path: Path, *, role: str, release_sha: str, environment_file: Path) -> dict[str, str]:
    payload, _ = _read_bytes(path)
    try:
        receipt = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ActivationError("activation receipt is invalid") from exc
    expected_keys = {
        "after_sha256", "before_sha256", "environment_file", "release_sha", "role", "schema_version"
    }
    if set(receipt) != expected_keys or receipt.get("schema_version") != "company_card_v2_activation_v1":
        raise ActivationError("activation receipt schema mismatch")
    if receipt.get("role") != role or receipt.get("release_sha") != release_sha:
        raise ActivationError("activation receipt identity mismatch")
    if receipt.get("environment_file") != str(environment_file):
        raise ActivationError("activation receipt environment mismatch")
    for key in ("after_sha256", "before_sha256"):
        if not isinstance(receipt.get(key), str) or re.fullmatch(r"[0-9a-f]{64}", receipt[key]) is None:
            raise ActivationError("activation receipt digest mismatch")
    return receipt


def preflight(role: str, environment_file: Path) -> None:
    payload, _ = _read_bytes(environment_file)
    _, values = _parse_environment(payload)
    if role == "gateway" and not values.get("OPENAI_API_KEY", "").strip():
        raise ActivationError("OPENAI_API_KEY is absent or blank; STOP")
    if role == "product":
        _require_product_provider(values)
        _validate_mask(values)
    elif role != "gateway":
        raise ActivationError("unsupported activation role")


def apply(
    role: str,
    environment_file: Path,
    backup_file: Path,
    receipt_file: Path,
    release_sha: str,
    durable_mask_file: Path | None = None,
) -> None:
    release_sha = _require_sha(release_sha)
    payload, info = _read_bytes(environment_file)
    rows, values = _parse_environment(payload)
    desired = _desired(role, values, durable_mask_file)
    updated = _render(rows, desired)
    _exclusive_copy(backup_file, payload, info)
    # Publish the restore authority durably before crossing the env mutation
    # boundary so cancellation can never leave an untracked active config.
    _write_receipt(
        receipt_file,
        role=role,
        release_sha=release_sha,
        environment_file=environment_file,
        before=payload,
        after=updated,
    )
    _atomic_replace(environment_file, updated, info)


def verify(role: str, environment_file: Path) -> None:
    payload, _ = _read_bytes(environment_file)
    _, values = _parse_environment(payload)
    desired = _desired(role, values)
    for key, expected in desired.items():
        if values.get(key) != expected:
            raise ActivationError(f"activation value mismatch for {key}")


def restore(role: str, environment_file: Path, backup_file: Path, receipt_file: Path, release_sha: str) -> None:
    release_sha = _require_sha(release_sha)
    current, info = _read_bytes(environment_file)
    backup, _ = _read_bytes(backup_file)
    receipt = _load_receipt(
        receipt_file,
        role=role,
        release_sha=release_sha,
        environment_file=environment_file,
    )
    if _hash(backup) != receipt["before_sha256"]:
        raise ActivationError("environment backup digest mismatch")
    if _hash(current) == receipt["before_sha256"]:
        return
    if _hash(current) != receipt["after_sha256"]:
        raise ActivationError("environment changed after activation; automatic restore refused")
    _atomic_replace(environment_file, backup, info)


def in_process_verify(role: str, release_sha: str) -> None:
    release_sha = _require_sha(release_sha)
    if role == "product":
        from product_api.settings import get_settings

        settings = get_settings()
        if not settings.datanewton_enabled or not (
            settings.datanewton_api_key and settings.datanewton_api_key.strip()
        ):
            raise ActivationError("Product DataNewton provider is unavailable")
        checks = {
            "COMPANY_CARD_V2_PRESENTATIONS_ENABLED": settings.company_card_v2_presentations_enabled,
            "COMPANY_CARD_V2_WRITER_ENABLED": settings.company_card_v2_writer_enabled,
            "COMPANY_CARD_V2_DIRECT_LAUNCH_ENABLED": settings.company_card_v2_direct_launch_enabled,
            "COMPANY_CARD_V2_ARBITRATION_COLLECTION_ENABLED": settings.company_card_v2_arbitration_collection_enabled,
            "COMPANY_CARD_AI_NARRATIVE_ENABLED": settings.company_card_v2_narrative_enabled,
        }
        if not all(checks.values()):
            raise ActivationError("Product activation settings are not effective")
        if settings.company_card_v2_narrative_kill_switch:
            raise ActivationError("Product narrative kill switch remains closed")
        if settings.company_card_v2_narrative_quota_mode != "unlimited":
            raise ActivationError("Product narrative quota mode is not unlimited")
        if settings.company_card_v2_rollout_generation != 1 or settings.company_card_v2_percentage_basis_points != 10000:
            raise ActivationError("Product H2 global generation is not effective")
        if settings.company_card_v2_allowlist_inns:
            raise ActivationError("Product H2 direct launch must not use an allowlist")
        if settings.company_card_v2_narrative_daily_limit != 0 or settings.company_card_v2_narrative_monthly_limit != 0:
            raise ActivationError("Product AI quota limits remain configured")
        if settings.company_card_v2_narrative_concurrency != 1:
            raise ActivationError("Product narrative worker backpressure mismatch")
        if os.environ.get("PRODUCT_RELEASE_COMMIT") != release_sha:
            raise ActivationError("Product runtime release mismatch")
        return
    if role == "gateway":
        from gateway_api.settings import get_settings

        settings = get_settings()
        if not settings.company_card_narrative_gateway_enabled:
            raise ActivationError("Gateway narrative profile is disabled")
        if settings.company_card_narrative_model_profile != "company_card_narrative_structured_v1":
            raise ActivationError("Gateway narrative profile mismatch")
        if settings.company_card_narrative_model != "gpt-5-nano":
            raise ActivationError("Gateway narrative model mismatch")
        if not (settings.openai_api_key and settings.openai_api_key.strip()):
            raise ActivationError("Gateway OpenAI credential is unavailable")
        if settings.gateway_release_commit != release_sha:
            raise ActivationError("Gateway runtime release mismatch")
        return
    raise ActivationError("unsupported activation role")


def schema_head(expected: str) -> None:
    import asyncio
    from sqlalchemy import text
    from product_api.db.session import AsyncSessionMaker

    async def inspect() -> None:
        async with AsyncSessionMaker() as session:
            rows = tuple((await session.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))).scalars().all())
        if rows != (expected,):
            raise ActivationError("production database schema head mismatch")

    asyncio.run(inspect())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "verify"):
        child = subparsers.add_parser(command)
        child.add_argument("--role", choices=("product", "gateway"), required=True)
        child.add_argument("--environment-file", type=Path, required=True)
    for command in ("apply", "restore"):
        child = subparsers.add_parser(command)
        child.add_argument("--role", choices=("product", "gateway"), required=True)
        child.add_argument("--environment-file", type=Path, required=True)
        child.add_argument("--backup-file", type=Path, required=True)
        child.add_argument("--receipt-file", type=Path, required=True)
        child.add_argument("--release-sha", required=True)
        if command == "apply":
            child.add_argument("--durable-mask-file", type=Path)
    prepare = subparsers.add_parser("prepare-mask")
    prepare.add_argument("--environment-file", type=Path, required=True)
    prepare.add_argument("--durable-mask-file", type=Path, required=True)
    runtime = subparsers.add_parser("in-process-verify")
    runtime.add_argument("--role", choices=("product", "gateway"), required=True)
    runtime.add_argument("--release-sha", required=True)
    schema = subparsers.add_parser("schema-head")
    schema.add_argument("--expected", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "preflight":
        preflight(args.role, args.environment_file)
    elif args.command == "prepare-mask":
        prepare_mask(args.environment_file, args.durable_mask_file)
    elif args.command == "apply":
        apply(
            args.role,
            args.environment_file,
            args.backup_file,
            args.receipt_file,
            args.release_sha,
            args.durable_mask_file,
        )
    elif args.command == "verify":
        verify(args.role, args.environment_file)
    elif args.command == "restore":
        restore(args.role, args.environment_file, args.backup_file, args.receipt_file, args.release_sha)
    elif args.command == "in-process-verify":
        in_process_verify(args.role, args.release_sha)
    elif args.command == "schema-head":
        schema_head(args.expected)
    else:  # pragma: no cover - argparse owns this boundary.
        raise ActivationError("unsupported command")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ActivationError as exc:
        raise SystemExit(f"activation refused: {exc}") from None
