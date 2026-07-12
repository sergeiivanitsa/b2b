from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from pydantic import ValidationError

from product_api.providers.datanewton import (
    ARBITRATION_CASES_ENDPOINT,
    BANKRUPTCY_ENDPOINT,
    BATCH_CARDS_ENDPOINT,
    FSSP_ENDPOINT,
    TAX_INFO_ENDPOINT,
    DataNewtonClient,
    DataNewtonError,
    DataNewtonIdentifierType,
    DataNewtonResult,
    DataNewtonUnsupportedIdentifierError,
    DataNewtonValidationError,
    identify_identifier_type,
    normalize_identifier,
)
from product_api.settings import Settings

from .json_shape import build_json_shape

PROBE_VERSION = "1"
DEFAULT_OUTPUT_DIR = Path("data/datanewton-probes")
DEFAULT_DETAIL_LIMIT = 20
DATASET_ORDER = (
    "batch_cards",
    "tax_info",
    "arbitration",
    "fssp",
    "bankruptcy",
)


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    name: str
    method: str
    endpoint: str


@dataclass(frozen=True, slots=True)
class ProbeConfig:
    identifier: str
    identifier_type: DataNewtonIdentifierType
    masked_identifier: str
    datasets: tuple[str, ...]
    output_dir: Path
    request_id: str | None
    detail_limit: int
    dry_run: bool
    confirm_live: bool
    run_id: str


DATASET_DEFINITIONS = {
    "batch_cards": DatasetDefinition("batch_cards", "POST", BATCH_CARDS_ENDPOINT),
    "tax_info": DatasetDefinition("tax_info", "GET", TAX_INFO_ENDPOINT),
    "arbitration": DatasetDefinition(
        "arbitration", "GET", ARBITRATION_CASES_ENDPOINT
    ),
    "fssp": DatasetDefinition("fssp", "POST", FSSP_ENDPOINT),
    "bankruptcy": DatasetDefinition("bankruptcy", "GET", BANKRUPTCY_ENDPOINT),
}
_FSSP_IDENTIFIER_TYPES = {
    DataNewtonIdentifierType.LEGAL_ENTITY_INN,
    DataNewtonIdentifierType.OGRN,
}


class ProbeArgumentError(ValueError):
    pass


class ProbeFilesystemError(OSError):
    pass


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ProbeArgumentError("invalid CLI arguments")


def mask_identifier(identifier: str) -> str:
    normalized = normalize_identifier(identifier)
    visible_count = min(2, len(normalized))
    return "*" * (len(normalized) - visible_count) + normalized[-visible_count:]


def main(
    argv: Sequence[str] | None = None,
    *,
    settings_factory: Callable[[], Settings] = Settings,
    client_factory: Callable[[Settings], DataNewtonClient] = DataNewtonClient,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    now_factory: Callable[[], datetime] | None = None,
) -> int:
    output = stdout or sys.stdout
    error_output = stderr or sys.stderr
    now = now_factory or _utc_now

    try:
        arguments = _build_parser().parse_args(argv)
        identifier = normalize_identifier(arguments.identifier)
        identifier_type = identify_identifier_type(identifier)
        datasets = _parse_datasets(arguments.datasets)
        current_time = _as_utc(now())
        run_id = _build_run_id(current_time, identifier)
        output_dir = Path(arguments.output_dir).expanduser().resolve(strict=False)
        config = ProbeConfig(
            identifier=identifier,
            identifier_type=identifier_type,
            masked_identifier=mask_identifier(identifier),
            datasets=datasets,
            output_dir=output_dir,
            request_id=arguments.request_id,
            detail_limit=arguments.detail_limit,
            dry_run=arguments.dry_run,
            confirm_live=arguments.confirm_live,
            run_id=run_id,
        )
        _validate_request_id(config)
    except (
        OSError,
        RuntimeError,
        ProbeArgumentError,
        DataNewtonValidationError,
        ValueError,
    ):
        print("error: invalid CLI arguments or identifier", file=error_output)
        return 3

    live_mode = config.confirm_live and not config.dry_run
    _print_plan(config, live_mode=live_mode, output=output)
    if not live_mode:
        print("No HTTP requests were executed.", file=output)
        return 0

    try:
        settings = settings_factory()
    except (ValidationError, ValueError):
        print("error: DataNewton live configuration is incomplete", file=error_output)
        return 4
    if not _configuration_is_complete(settings):
        print("error: DataNewton live configuration is incomplete", file=error_output)
        return 4
    if config.request_id and _contains_forbidden_value(
        config.request_id, (settings.datanewton_api_key or "", config.identifier)
    ):
        print("error: unsafe request ID", file=error_output)
        return 3

    return asyncio.run(
        _run_live_probe(
            config,
            settings=settings,
            client_factory=client_factory,
            output=output,
            error_output=error_output,
            now_factory=now,
        )
    )


def _build_parser() -> _SafeArgumentParser:
    parser = _SafeArgumentParser(
        prog="python -m product_api.tools.datanewton_probe",
        description="Safely inspect DataNewton response structures.",
    )
    parser.add_argument("--identifier", required=True)
    parser.add_argument("--datasets", default="all")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--request-id")
    parser.add_argument(
        "--detail-limit",
        type=_detail_limit,
        default=DEFAULT_DETAIL_LIMIT,
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-live", action="store_true")
    return parser


def _detail_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("detail limit must be an integer") from None
    if not 1 <= limit <= 1000:
        raise argparse.ArgumentTypeError("detail limit must be between 1 and 1000")
    return limit


def _parse_datasets(value: str) -> tuple[str, ...]:
    requested = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not requested:
        raise ProbeArgumentError("dataset selection must not be empty")
    if "all" in requested:
        if any(item not in {*DATASET_ORDER, "all"} for item in requested):
            raise ProbeArgumentError("unknown dataset")
        return DATASET_ORDER
    if any(item not in DATASET_ORDER for item in requested):
        raise ProbeArgumentError("unknown dataset")
    return tuple(dict.fromkeys(requested))


def _validate_request_id(config: ProbeConfig) -> None:
    if config.identifier in str(config.output_dir):
        raise ProbeArgumentError("unsafe output path")
    if config.request_id is None:
        return
    request_id = config.request_id
    if not request_id or len(request_id) > 128:
        raise ProbeArgumentError("unsafe request ID")
    if config.identifier in request_id:
        raise ProbeArgumentError("unsafe request ID")
    digits = "".join(character for character in request_id if character.isdigit())
    if digits == config.identifier:
        raise ProbeArgumentError("unsafe request ID")
    if any(character in request_id for character in "\r\n"):
        raise ProbeArgumentError("unsafe request ID")


def _print_plan(config: ProbeConfig, *, live_mode: bool, output: TextIO) -> None:
    plan = _dataset_plan(config)
    planned_requests = sum(1 for _, will_run, _ in plan if will_run)
    mode = "LIVE" if live_mode else "DRY-RUN"
    print(f"Run ID: {config.run_id}", file=output)
    print(f"Mode: {mode}", file=output)
    print(f"Identifier: {config.masked_identifier}", file=output)
    print(f"Identifier type: {config.identifier_type.value}", file=output)
    print(f"Datasets: {', '.join(config.datasets)}", file=output)
    print(f"Planned HTTP requests: {planned_requests}", file=output)
    print(f"Output directory: {config.output_dir}", file=output)
    print("Warning: live requests may consume the DataNewton API limit.", file=output)
    print("Dataset | Method | Endpoint | Action | Reason", file=output)
    for definition, will_run, reason in plan:
        action = "Will run" if will_run else "Will skip"
        print(
            f"{definition.name} | {definition.method} | {definition.endpoint} | "
            f"{action} | {reason}",
            file=output,
        )


def _dataset_plan(
    config: ProbeConfig,
) -> list[tuple[DatasetDefinition, bool, str]]:
    plan: list[tuple[DatasetDefinition, bool, str]] = []
    for dataset in config.datasets:
        definition = DATASET_DEFINITIONS[dataset]
        if dataset == "fssp" and config.identifier_type not in _FSSP_IDENTIFIER_TYPES:
            plan.append(
                (definition, False, "identifier type is unsupported by local FSSP schema")
            )
        else:
            plan.append((definition, True, "selected"))
    return plan


async def _run_live_probe(
    config: ProbeConfig,
    *,
    settings: Settings,
    client_factory: Callable[[Settings], DataNewtonClient],
    output: TextIO,
    error_output: TextIO,
    now_factory: Callable[[], datetime],
) -> int:
    output_root = config.output_dir.resolve(strict=False)
    run_directory = output_root / config.run_id
    if run_directory.parent != output_root:
        print("error: unsafe output path", file=error_output)
        return 5
    if not _is_git_safe_output(run_directory):
        print("error: probe output is not ignored by Git", file=error_output)
        return 5
    try:
        run_directory.mkdir(parents=True, exist_ok=False)
    except OSError:
        print("error: unable to create probe output directory", file=error_output)
        return 5

    started_at = _as_utc(now_factory())
    started_perf = time.perf_counter()
    request_id = config.request_id or config.run_id
    dataset_summaries: dict[str, dict[str, Any]] = {}
    completed_requests = 0
    successful_requests = 0
    failed_requests = 0
    common_warnings: list[str] = []
    client = client_factory(settings)

    try:
        for definition, will_run, reason in _dataset_plan(config):
            dataset_directory = run_directory / definition.name
            dataset_directory.mkdir(exist_ok=False)
            if not will_run:
                meta = _unsupported_meta(
                    definition,
                    identifier_type=config.identifier_type,
                    request_id=request_id,
                    reason=reason,
                )
                _write_safe_json(
                    dataset_directory / "meta.json",
                    meta,
                    forbidden_values=(settings.datanewton_api_key or "", config.identifier),
                )
                dataset_summaries[definition.name] = _manifest_summary(meta)
                common_warnings.append(f"{definition.name} was skipped as unsupported")
                print(f"{definition.name}: unsupported", file=output)
                continue

            call_started = time.perf_counter()
            try:
                result = await _fetch_dataset(
                    client,
                    definition.name,
                    identifier=config.identifier,
                    detail_limit=config.detail_limit,
                    request_id=request_id,
                )
                duration_ms = (time.perf_counter() - call_started) * 1000
                meta = _success_meta(result)
                shape = build_json_shape(result.raw_payload)
                _write_safe_json(
                    dataset_directory / "raw.json",
                    result.raw_payload,
                    forbidden_values=(settings.datanewton_api_key or "",),
                )
                _write_safe_json(
                    dataset_directory / "shape.json",
                    shape,
                    forbidden_values=(settings.datanewton_api_key or "", config.identifier),
                )
                _write_safe_json(
                    dataset_directory / "meta.json",
                    meta,
                    forbidden_values=(settings.datanewton_api_key or "", config.identifier),
                )
                completed_requests += 1
                successful_requests += 1
                dataset_summaries[definition.name] = _manifest_summary(meta)
                print(
                    f"{definition.name}: success attempts={result.attempts} "
                    f"duration_ms={duration_ms:.3f}",
                    file=output,
                )
            except DataNewtonUnsupportedIdentifierError as exc:
                meta = _error_meta(
                    definition,
                    exc,
                    request_id=request_id,
                    duration_ms=(time.perf_counter() - call_started) * 1000,
                    status="unsupported",
                )
                _write_safe_json(
                    dataset_directory / "meta.json",
                    meta,
                    forbidden_values=(settings.datanewton_api_key or "", config.identifier),
                )
                dataset_summaries[definition.name] = _manifest_summary(meta)
                common_warnings.append(f"{definition.name} was skipped as unsupported")
                print(f"{definition.name}: unsupported", file=output)
            except DataNewtonError as exc:
                meta = _error_meta(
                    definition,
                    exc,
                    request_id=request_id,
                    duration_ms=(time.perf_counter() - call_started) * 1000,
                    status="error",
                )
                _write_safe_json(
                    dataset_directory / "meta.json",
                    meta,
                    forbidden_values=(settings.datanewton_api_key or "", config.identifier),
                )
                completed_requests += 1
                failed_requests += 1
                dataset_summaries[definition.name] = _manifest_summary(meta)
                print(
                    f"{definition.name}: error attempts={exc.attempts} "
                    f"duration_ms={meta['duration_ms']:.3f}",
                    file=output,
                )
            except (OSError, ProbeFilesystemError, TypeError, ValueError):
                raise
            except Exception:
                meta = _unexpected_error_meta(
                    definition,
                    request_id=request_id,
                    duration_ms=(time.perf_counter() - call_started) * 1000,
                )
                _write_safe_json(
                    dataset_directory / "meta.json",
                    meta,
                    forbidden_values=(settings.datanewton_api_key or "", config.identifier),
                )
                completed_requests += 1
                failed_requests += 1
                dataset_summaries[definition.name] = _manifest_summary(meta)
                print(
                    f"{definition.name}: error attempts=0 "
                    f"duration_ms={meta['duration_ms']:.3f}",
                    file=output,
                )
    except (OSError, ProbeFilesystemError, TypeError, ValueError):
        print("error: unable to safely write probe output", file=error_output)
        return 5
    finally:
        await client.aclose()

    finished_at = _as_utc(now_factory())
    total_duration_ms = (time.perf_counter() - started_perf) * 1000
    if failed_requests:
        common_warnings.append("one or more datasets failed")
    manifest = {
        "probe_version": PROBE_VERSION,
        "run_id": config.run_id,
        "started_at": _iso_utc(started_at),
        "finished_at": _iso_utc(finished_at),
        "masked_identifier": config.masked_identifier,
        "identifier_type": config.identifier_type.value,
        "selected_datasets": list(config.datasets),
        "planned_requests": sum(
            1 for _, will_run, _ in _dataset_plan(config) if will_run
        ),
        "completed_requests": completed_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "total_duration_ms": total_duration_ms,
        "datasets": dataset_summaries,
        "warnings": common_warnings,
    }
    try:
        _write_safe_json(
            run_directory / "manifest.json",
            manifest,
            forbidden_values=(settings.datanewton_api_key or "", config.identifier),
        )
    except (OSError, ProbeFilesystemError, TypeError, ValueError):
        print("error: unable to safely write probe manifest", file=error_output)
        return 5

    print(f"Output path: {run_directory}", file=output)
    print(
        f"Completed={completed_requests} Successful={successful_requests} "
        f"Failed={failed_requests}",
        file=output,
    )
    return 2 if failed_requests else 0


async def _fetch_dataset(
    client: DataNewtonClient,
    dataset: str,
    *,
    identifier: str,
    detail_limit: int,
    request_id: str,
) -> DataNewtonResult:
    if dataset == "batch_cards":
        return await client.fetch_batch_cards([identifier], request_id=request_id)
    if dataset == "tax_info":
        return await client.fetch_tax_info(identifier, request_id=request_id)
    if dataset == "arbitration":
        return await client.fetch_arbitration_cases(
            identifier,
            offset=0,
            limit=detail_limit,
            request_id=request_id,
        )
    if dataset == "fssp":
        return await client.fetch_fssp(
            identifier,
            offset=0,
            limit=detail_limit,
            request_id=request_id,
        )
    if dataset == "bankruptcy":
        return await client.fetch_bankruptcy(
            identifier,
            offset=0,
            limit=detail_limit,
            request_id=request_id,
        )
    raise ProbeArgumentError("unknown dataset")


def _success_meta(result: DataNewtonResult) -> dict[str, Any]:
    return {
        "provider": result.provider,
        "dataset": result.dataset,
        "endpoint": result.endpoint,
        "status": "success",
        "status_code": result.status_code,
        "attempts": result.attempts,
        "duration_ms": result.duration_ms,
        "request_id": result.request_id,
        "received_at": _iso_utc(result.received_at),
        "response_hash": result.response_hash,
        "provider_limit_metadata": result.provider_limit_metadata,
        "warnings": result.warnings,
        "raw_file": "raw.json",
        "shape_file": "shape.json",
    }


def _error_meta(
    definition: DatasetDefinition,
    error: DataNewtonError,
    *,
    request_id: str,
    duration_ms: float,
    status: str,
) -> dict[str, Any]:
    return {
        "provider": "datanewton",
        "dataset": definition.name,
        "endpoint": definition.endpoint,
        "status": status,
        "safe_error_type": type(error).__name__,
        "safe_error_message": str(error),
        "retryable": error.retryable,
        "attempts": error.attempts,
        "request_id": request_id,
        "duration_ms": duration_ms,
    }


def _unexpected_error_meta(
    definition: DatasetDefinition,
    *,
    request_id: str,
    duration_ms: float,
) -> dict[str, Any]:
    return {
        "provider": "datanewton",
        "dataset": definition.name,
        "endpoint": definition.endpoint,
        "status": "error",
        "safe_error_type": "UnexpectedProviderError",
        "safe_error_message": "unexpected provider client error",
        "retryable": False,
        "attempts": 0,
        "request_id": request_id,
        "duration_ms": duration_ms,
    }


def _unsupported_meta(
    definition: DatasetDefinition,
    *,
    identifier_type: DataNewtonIdentifierType,
    request_id: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "provider": "datanewton",
        "dataset": definition.name,
        "endpoint": definition.endpoint,
        "status": "unsupported",
        "safe_error_type": "DataNewtonUnsupportedIdentifierError",
        "safe_error_message": reason,
        "identifier_type": identifier_type.value,
        "retryable": False,
        "attempts": 0,
        "request_id": request_id,
    }


def _manifest_summary(meta: dict[str, Any]) -> dict[str, Any]:
    summary_keys = (
        "status",
        "endpoint",
        "status_code",
        "safe_error_type",
        "retryable",
        "attempts",
        "duration_ms",
        "response_hash",
    )
    return {key: meta[key] for key in summary_keys if key in meta}


def _write_safe_json(
    path: Path,
    payload: Any,
    *,
    forbidden_values: Sequence[str],
) -> None:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if _contains_forbidden_value(serialized, forbidden_values):
        raise ProbeFilesystemError("unsafe value detected in probe output")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="x",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(serialized)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _contains_forbidden_value(text: str, values: Sequence[str]) -> bool:
    return any(value and value in text for value in values)


def _configuration_is_complete(settings: Settings) -> bool:
    return bool(
        settings.datanewton_enabled
        and settings.datanewton_base_url.strip()
        and settings.datanewton_api_key
        and settings.datanewton_api_key.strip()
    )


def _is_git_safe_output(run_directory: Path) -> bool:
    try:
        repository = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    if repository.returncode != 0:
        return True
    repository_root = Path(repository.stdout.strip()).resolve(strict=False)
    resolved_run_directory = run_directory.resolve(strict=False)
    if not resolved_run_directory.is_relative_to(repository_root):
        return True
    try:
        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", str(resolved_run_directory)],
            cwd=repository_root,
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return ignored.returncode == 0


def _build_run_id(timestamp: datetime, identifier: str) -> str:
    timestamp_part = timestamp.strftime("%Y%m%dT%H%M%SZ")
    identifier_hash = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:12]
    return f"{timestamp_part}_{identifier_hash}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
