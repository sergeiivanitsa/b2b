"""Seed the five closed Company Card v2 profiles into a disposable database."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from typing import Any
from uuid import UUID


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCT_SOURCE = REPO_ROOT / "services" / "product_api" / "src"
for _path in (PRODUCT_SOURCE, REPO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from tests_support.network_guard import prepare_test_environment

prepare_test_environment(suite="product-integration")

from sqlalchemy import func, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from product_api.company_reports.company_card_v2.arbitration_v2 import (
    arbitration_chart_facts_hash,
    build_arbitration_chart_facts,
)
from product_api.company_reports.company_card_v2.canonical_json import (
    canonical_json_bytes,
)
from product_api.company_reports.company_card_v2.finance import (
    FORM_BY_CODE,
    build_chart_facts,
)
from product_api.company_reports.company_card_v2.models import (
    ArbitrationBasisV2,
    ArbitrationCollectionCountersV2,
    CompanyCardCounterpartyCoreV1,
    FinanceBasisV1,
    FinanceCellV1,
    PrivateOpponentTokenV2,
    SanitizedArbitrationCaseV2,
)
from product_api.company_reports.company_card_v2.narrative.catalog import (
    FALLBACK_CATALOG_VERSION,
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
)
from product_api.company_reports.company_card_v2.narrative.identity import (
    FallbackIdentityV1,
    identity_key,
)
from product_api.company_reports.company_card_v2.public_h2 import (
    PublicH2ProjectionBindingV1,
    build_public_h2,
)
from product_api.company_reports.company_card_v2.public_h2_models import (
    PublicH2Narrative,
)
from product_api.company_reports.company_card_v2.service import (
    _v3_generation_identity,
    build_active_public_h2_for_pin,
    resolve_public_h2,
)
from product_api.company_reports.persistence.models import (
    CompanyCardNarrativeArtifact,
    CompanyCardNarrativeJob,
    CompanyCardNarrativeOutbox,
    CompanyCardV2RolloutDecision,
    CompanyReportPresentation,
    CompanyReportPresentationAssignment,
    CompanyReportPresentationAssignmentJournal,
    CompanyReportPresentationPin,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.presentations import (
    RolloutAssignmentCommand,
    append_presentation_pin,
    append_resolved_h2_pin,
    assign_rollout_pin_cas,
    bind_rollout_decision,
    create_or_reuse_unresolved_h2_pin,
)
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
)
from product_api.company_reports.persistence.v3 import (
    calculate_company_card_v2_snapshot_hash,
    company_card_v2_from_snapshot,
    company_card_v2_to_snapshot,
)
from product_api.company_reports.seo import canonical_path as h1_canonical_path


EXPECTED_HEAD = "0019_company_card_v2_rollout_control"
REGISTRY_PATH = (
    REPO_ROOT
    / "services"
    / "product_api"
    / "tests"
    / "fixtures"
    / "company_card_v2_iteration25"
    / "profile_seed_registry_v1.json"
)
SHARED_REGISTRY_PATH = (
    REPO_ROOT
    / "shared"
    / "fixtures"
    / "company_card_v2_iteration25"
    / "acceptance_profiles_v1.json"
)
V3_TEMPLATE_PATH = (
    REPO_ROOT
    / "services"
    / "product_api"
    / "tests_unit"
    / "fixtures"
    / "company_card_v2"
    / "snapshot_v3_arbitration_v3.json"
)
H1_TEMPLATE_PATH = (
    REPO_ROOT
    / "services"
    / "product_api"
    / "tests_unit"
    / "fixtures"
    / "company_reports"
    / "snapshot_v2_exact.json"
)
PROFILE_IDS = (
    "sks_morphology_complete_v1",
    "sparse_missing_fallback_v1",
    "partial_long_limitations_v1",
    "large_n_signed_masked_v1",
    "lazy_failure_v1",
)
LAZY_HOSTS = (
    "finance-f1",
    "finance-f2",
    "finance-f3",
    "finance-f4",
    "arbitration-a1",
    "arbitration-a2",
    "arbitration-a3",
    "arbitration-a4",
    "arbitration-a5",
)
EXPECTED_LAZY_HOSTS = {
    profile_id: LAZY_HOSTS for profile_id in PROFILE_IDS
}
EXPECTED_LAZY_HOSTS["sparse_missing_fallback_v1"] = LAZY_HOSTS[4:]
RELEASE_SHA = re.compile(r"^[0-9a-f]{40}$")
DATABASE_NAME = re.compile(r"^i25_suite_(?P<suffix>[0-9a-f]{12})$")
DATABASE_USER = re.compile(r"^i24u(?P<suffix>[0-9a-f]{12})$")
DATABASE_PASSWORD = re.compile(r"^i25p(?P<run>[0-9a-f]{32})$")
SAFE_PATH = re.compile(r"^/company/[0-9]{10,12}-[a-z0-9]+(?:-[a-z0-9]+)*$")
DECISION_ID = UUID("25300000-0000-4000-8000-000000000001")


class SeederContractError(RuntimeError):
    pass


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise SeederContractError(f"{label} has unknown or missing keys")


def _load_json(path: Path) -> Any:
    raw = path.read_bytes()
    if not raw or len(raw) > 1_048_576 or raw.startswith(b"\xef\xbb\xbf"):
        raise SeederContractError("fixture JSON is empty, too large or has a BOM")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SeederContractError("fixture JSON is malformed") from exc


def load_profile_registry() -> tuple[dict[str, Any], ...]:
    source = _load_json(REGISTRY_PATH)
    shared = _load_json(SHARED_REGISTRY_PATH)
    if type(source) is not dict or type(shared) is not dict:
        raise SeederContractError("acceptance registries must be objects")
    _exact_keys(source, {"schema_version", "generated_at", "profiles"}, "seed registry")
    _exact_keys(shared, {"schema_version", "profile_ids", "routes", "privacy"}, "shared registry")
    if (
        source["schema_version"] != "company_card_v2_iteration25_seed_registry_v1"
        or source["generated_at"] != "2026-08-28T00:00:00Z"
        or shared["schema_version"]
        != "company_card_v2_iteration25_acceptance_profiles_v1"
        or tuple(shared["profile_ids"]) != PROFILE_IDS
    ):
        raise SeederContractError("acceptance registry identity is invalid")
    profiles = source["profiles"]
    if type(profiles) is not list or len(profiles) != len(PROFILE_IDS):
        raise SeederContractError("acceptance registry must contain five profiles")
    expected_keys = {
        "profile_id",
        "subject_id",
        "h1_report_id",
        "h2_report_id",
        "inn",
        "display_name",
        "canonical_path",
        "wrong_slug_path",
        "expected_indexable",
        "expected_lazy_hosts",
        "expected_visible_text",
        "forbidden_visible_text",
        "lazy_failure_chunk",
    }
    seen_uuid: set[UUID] = set()
    seen_inn: set[str] = set()
    seen_paths: set[str] = set()
    validated: list[dict[str, Any]] = []
    for expected_id, profile in zip(PROFILE_IDS, profiles, strict=True):
        if type(profile) is not dict:
            raise SeederContractError("acceptance profile must be an object")
        _exact_keys(profile, expected_keys, expected_id)
        if profile["profile_id"] != expected_id:
            raise SeederContractError("acceptance profiles are out of order")
        identifiers = tuple(
            UUID(profile[key])
            for key in ("subject_id", "h1_report_id", "h2_report_id")
        )
        if any(str(value) != profile[key] for value, key in zip(
            identifiers,
            ("subject_id", "h1_report_id", "h2_report_id"),
            strict=True,
        )):
            raise SeederContractError("profile UUID is not canonical")
        if seen_uuid.intersection(identifiers):
            raise SeederContractError("profile UUIDs must be unique")
        seen_uuid.update(identifiers)
        inn = profile["inn"]
        if type(inn) is not str or not inn.isascii() or not inn.isdigit() or len(inn) != 10:
            raise SeederContractError("profile INN is invalid")
        if inn in seen_inn:
            raise SeederContractError("profile INNs must be unique")
        seen_inn.add(inn)
        for key in ("canonical_path", "wrong_slug_path"):
            path = profile[key]
            if type(path) is not str or SAFE_PATH.fullmatch(path) is None or path in seen_paths:
                raise SeederContractError("profile path is invalid or duplicated")
            seen_paths.add(path)
        if (
            profile["canonical_path"] != f"/company/{inn}-company"
            or profile["wrong_slug_path"] == profile["canonical_path"]
            or profile["expected_indexable"] is not False
            or tuple(profile["expected_lazy_hosts"])
            != EXPECTED_LAZY_HOSTS[expected_id]
            or type(profile["expected_visible_text"]) is not list
            or not profile["expected_visible_text"]
            or len(set(profile["expected_visible_text"]))
            != len(profile["expected_visible_text"])
            or type(profile["forbidden_visible_text"]) is not list
            or len(set(profile["forbidden_visible_text"]))
            != len(profile["forbidden_visible_text"])
            or (expected_id == "lazy_failure_v1")
            != (profile["lazy_failure_chunk"] in {"finance", "arbitration"})
        ):
            raise SeederContractError("profile browser contract is invalid")
        validated.append(profile)
    return tuple(validated)


def validate_runner_database(raw_url: str, database_name: str) -> URL:
    try:
        target = make_url(raw_url)
    except Exception as exc:
        raise SeederContractError("database URL is malformed") from exc
    database_match = DATABASE_NAME.fullmatch(database_name)
    user_match = DATABASE_USER.fullmatch(target.username or "")
    password_match = DATABASE_PASSWORD.fullmatch(target.password or "")
    if (
        target.drivername != "postgresql+asyncpg"
        or (target.host or "").lower() != "127.0.0.1"
        or target.port is None
        or not 1 <= target.port <= 65535
        or target.database != database_name
        or bool(target.query)
        or database_match is None
        or user_match is None
        or password_match is None
        or database_match.group("suffix") != user_match.group("suffix")
        or not password_match.group("run").startswith(database_match.group("suffix"))
    ):
        raise SeederContractError(
            "database URL must name the iteration-25 runner-owned suite database"
        )
    return target


def validate_manifest_output(path: Path) -> Path:
    if not path.is_absolute() or path.exists():
        raise SeederContractError("manifest output must be a new absolute path")
    parent = path.parent.resolve(strict=True)
    if parent.is_symlink() or not parent.is_dir():
        raise SeederContractError("manifest output parent must be a plain directory")
    return parent / path.name


def build_e2e_manifest(
    profiles: tuple[dict[str, Any], ...], *, release_sha: str
) -> dict[str, Any]:
    if RELEASE_SHA.fullmatch(release_sha) is None:
        raise SeederContractError("release SHA must be exact lowercase 40-hex")
    return {
        "schema_version": "company_card_v2_e2e_manifest_v1",
        "release_sha": release_sha,
        "routes": {
            "robots_path": "/robots.txt",
            "sitemap_index_path": "/sitemaps/index.xml",
        },
        "profiles": [
            {
                "profile_id": profile["profile_id"],
                "canonical_path": profile["canonical_path"],
                "wrong_slug_path": profile["wrong_slug_path"],
                "expected_report_id": profile["h2_report_id"],
                "expected_indexable": profile["expected_indexable"],
                "expected_lazy_hosts": profile["expected_lazy_hosts"],
                "expected_visible_text": profile["expected_visible_text"],
                "forbidden_visible_text": profile["forbidden_visible_text"],
                "lazy_failure_chunk": profile["lazy_failure_chunk"],
            }
            for profile in profiles
        ],
    }


def _finance_basis(profile_id: str) -> FinanceBasisV1:
    if profile_id == "sparse_missing_fallback_v1":
        return FinanceBasisV1()
    values = {
        "1250": "10",
        "1240": "20",
        "1230": "30",
        "1500": "40",
        "1300": "50",
        "1400": "20",
        "1600": "100",
        "2110": "200",
        "2100": "80",
        "2200": "60",
        "2400": "40",
        "1210": "15",
    }
    cells: list[FinanceCellV1] = []
    for year in range(2019, 2026):
        for code, raw_value in values.items():
            state_override = None
            if profile_id == "partial_long_limitations_v1" and (code, year) == (
                "2110", 2024
            ):
                state_override = "missing"
            elif profile_id == "large_n_signed_masked_v1" and (code, year) == (
                "1250", 2019
            ):
                state_override = "missing"
            elif profile_id == "large_n_signed_masked_v1" and (code, year) == (
                "1230", 2020
            ):
                state_override = "zero_unverified"
            if state_override is not None:
                cells.append(
                    FinanceCellV1(
                        form=FORM_BY_CODE[code],
                        code=code,
                        year=year,
                        state=state_override,
                    )
                )
                continue
            value = raw_value
            if (
                profile_id == "large_n_signed_masked_v1"
                and year == 2025
                and code == "1300"
            ):
                value = "-10"
            cells.append(
                FinanceCellV1(
                    form=FORM_BY_CODE[code],
                    code=code,
                    year=year,
                    state="available_nonzero",
                    value=Decimal(value),
                )
            )
    return FinanceBasisV1(cells=tuple(cells))


def _large_arbitration_basis(template: ArbitrationBasisV2) -> ArbitrationBasisV2:
    base_case = template.sanitized_cases[0]
    cases: list[SanitizedArbitrationCaseV2] = []
    for ordinal in range(1, 26):
        token = PrivateOpponentTokenV2(
            key_id=template.mask_key_id or "active_2026",
            value=sha256(f"iteration25-opponent-{ordinal:02d}".encode("ascii")).hexdigest(),
        )
        cases.append(
            SanitizedArbitrationCaseV2.model_validate(
                {
                    **base_case.model_dump(mode="json"),
                    "case_id": f"synthetic-case-{ordinal:04d}",
                    "first_number": f"А40-{1000 + ordinal}/2026",
                    "role": "plaintiff" if ordinal % 2 else "respondent",
                    "outcome": "won" if ordinal % 2 else "returned",
                    "amount": str(ordinal) if ordinal % 3 else f"-{ordinal}",
                    "opponent_tokens": [token.model_dump(mode="json")],
                }
            )
        )
    count = len(cases)
    counters = ArbitrationCollectionCountersV2(
        pages_requested=1,
        pages_accepted=1,
        rows_observed=count,
        rows_processed=count,
        rows_shape_valid=count,
        unique_case_count=count,
        opponent_token_count=count,
        opponent_group_count=count,
        opponent_group_probe_count=count,
    )
    payload = template.model_dump(mode="json")
    payload.update(
        {
            "source_total": count,
            "page_manifest": [
                {
                    **payload["page_manifest"][0],
                    "returned_count": count,
                    "accepted_count": count,
                    "response_hash": sha256(b"iteration25-large-n-page").hexdigest(),
                }
            ],
            "counters": counters.model_dump(mode="json"),
            "sanitized_cases": [case.model_dump(mode="json") for case in cases],
        }
    )
    return ArbitrationBasisV2.model_validate(payload)


def _snapshot(profile: dict[str, Any]):
    raw = _load_json(V3_TEMPLATE_PATH)
    snapshot = company_card_v2_from_snapshot(raw)
    basis = _finance_basis(profile["profile_id"])
    arbitration_basis = (
        _large_arbitration_basis(snapshot.arbitration_basis)
        if profile["profile_id"] == "large_n_signed_masked_v1"
        else snapshot.arbitration_basis
    )
    address = "Синтетический адрес"
    if profile["profile_id"] == "partial_long_limitations_v1":
        address = "Синтетический адрес с ограничением " + ("длинная строка " * 60).strip()
    updated = snapshot.model_copy(
        update={
            "report_id": profile["h2_report_id"],
            "subject_inn": profile["inn"],
            "target_inn": profile["inn"],
            "counterparty": CompanyCardCounterpartyCoreV1(
                inn=profile["inn"],
                full_name=profile["display_name"],
                short_name=profile["display_name"],
                address=address,
                address_inaccuracy=False,
            ),
            "finance_basis": basis,
            "chart_facts": build_chart_facts(basis),
            "arbitration_basis": arbitration_basis,
            "arbitration_chart_facts": build_arbitration_chart_facts(
                arbitration_basis
            ),
            "arbitration_chart_facts_hash": arbitration_chart_facts_hash(
                build_arbitration_chart_facts(arbitration_basis)
            ),
        }
    )
    return type(snapshot).model_validate(updated.model_dump(mode="json"))


def _h1_snapshot(profile: dict[str, Any]) -> dict[str, Any]:
    raw = _load_json(H1_TEMPLATE_PATH)
    generated_at = "2026-08-28T00:00:00Z"
    raw.update(
        {
            "report_id": profile["h1_report_id"],
            "generated_at": generated_at,
            "target_identifier": profile["inn"],
        }
    )
    raw["counterparty"].update(
        {
            "inn": profile["inn"],
            "full_name": profile["display_name"],
        }
    )
    raw["counterparty"]["source"]["received_at"] = generated_at
    raw["datasets"]["counterparty"]["source"] = dict(
        raw["counterparty"]["source"]
    )
    raw["freshness"]["generated_at"] = generated_at
    return raw


def _fallback_binding(report: CompanyReportRecord, snapshot):
    generation_identity = _v3_generation_identity(record=report, snapshot=snapshot)
    generation_key = identity_key(generation_identity)
    rendered_digest = sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest()
    fallback_identity = identity_key(
        FallbackIdentityV1(
            generation_key=generation_key,
            fallback_catalog_version=FALLBACK_CATALOG_VERSION,
            fallback_profile_id=FALLBACK_PROFILE_ID,
            renderer_version=FALLBACK_RENDERER_VERSION,
            rendered_output_bytes_sha256=rendered_digest,
        )
    )
    narrative = PublicH2Narrative(
        mode="deterministic_fallback",
        renderer_version=FALLBACK_RENDERER_VERSION,
        description=FALLBACK_DESCRIPTION,
        statement_ids=(FALLBACK_PROFILE_ID,),
        comments=(),
        render_digest=rendered_digest,
    )
    return generation_identity, generation_key, rendered_digest, fallback_identity, narrative


async def _seed_profile(
    session: AsyncSession,
    *,
    profile: dict[str, Any],
    decision_digest: str,
    release_sha: str,
    target_count: int,
) -> None:
    subject = CompanyReportSubject(
        id=UUID(profile["subject_id"]),
        normalized_identifier=profile["inn"],
        identifier_type="legal_entity_inn",
    )
    session.add(subject)
    await session.flush()
    generated_at = datetime(2026, 8, 28, tzinfo=timezone.utc)

    h1_raw = _h1_snapshot(profile)
    h1 = CompanyReportRecord(
        id=UUID(profile["h1_report_id"]),
        subject_id=subject.id,
        report_version="2",
        writer_profile="h1_legacy_writer_v2",
        presentation_contract="company_public_h1_v1",
        rollout_generation=0,
        lifecycle_status="partial",
        started_at=generated_at,
        generated_at=generated_at,
        finished_at=generated_at,
        normalized_snapshot=h1_raw,
        snapshot_hash=calculate_company_report_snapshot_hash(h1_raw),
        warnings_snapshot=[],
        usable_for_public_page=True,
        usable_for_future_scoring=False,
    )
    session.add(h1)
    await session.flush()
    h1_pin = await append_presentation_pin(
        session,
        subject_id=subject.id,
        report=h1,
        contract="company_public_h1_v1",
        generation=1,
        publication_policy_version="publication_sufficiency_v1",
        canonical_path=h1_canonical_path(
            profile["inn"], profile["display_name"]
        ),
        published_lastmod=generated_at,
        indexable=True,
    )

    snapshot = _snapshot(profile)
    h2_raw = company_card_v2_to_snapshot(snapshot)
    h2 = CompanyReportRecord(
        id=UUID(profile["h2_report_id"]),
        subject_id=subject.id,
        report_version="3",
        writer_profile="company_card_v2_writer_v3",
        presentation_contract="company_public_h2_v1",
        rollout_generation=1,
        lifecycle_status="complete",
        started_at=snapshot.generated_at,
        generated_at=snapshot.generated_at,
        finished_at=snapshot.generated_at,
        normalized_snapshot=h2_raw,
        snapshot_hash=calculate_company_card_v2_snapshot_hash(snapshot),
        completeness_snapshot={},
        freshness_snapshot={},
        warnings_snapshot=[],
        usable_for_public_page=False,
        usable_for_future_scoring=False,
        arbitration_collection_enabled=True,
        arbitration_mask_key_id=snapshot.arbitration_basis.mask_key_id,
    )
    session.add(h2)
    await session.flush()
    session.add(
        CompanyReportPresentation(
            subject_id=subject.id,
            report_id=h2.id,
            presentation_contract="company_public_h2_v1",
            rollout_generation=1,
        )
    )
    await session.flush()
    await create_or_reuse_unresolved_h2_pin(session, report=h2)

    identity, generation_key, rendered_digest, fallback_identity, narrative = (
        _fallback_binding(h2, snapshot)
    )
    job = CompanyCardNarrativeJob(
        report_id=h2.id,
        snapshot_hash=h2.snapshot_hash,
        generation_key=generation_key,
        identity_version="GenerationIdentityV2",
        generation_identity=asdict(identity),
        state="fallback_finalized",
        available_at=snapshot.generated_at,
        validation_codes=["feature_disabled"],
    )
    session.add(job)
    await session.flush()
    artifact = CompanyCardNarrativeArtifact(
        report_id=h2.id,
        snapshot_hash=h2.snapshot_hash,
        generation_key=generation_key,
        binding_kind="fallback",
        binding_key=fallback_identity,
        fallback_identity=fallback_identity,
        rendered_description=FALLBACK_DESCRIPTION,
        rendered_comments=[],
        statement_ids=[FALLBACK_PROFILE_ID],
        evidence_ids=[],
        phrase_trace=[
            {
                "scalar_start": 0,
                "scalar_end": len(FALLBACK_DESCRIPTION),
                "statement_id": FALLBACK_PROFILE_ID,
                "evidence_ids": [],
            }
        ],
        validation_codes=[],
        renderer_version=FALLBACK_RENDERER_VERSION,
        rendered_output_bytes_sha256=rendered_digest,
    )
    session.add(artifact)
    await session.flush()
    job.artifact_id = artifact.id
    session.add(
        CompanyCardNarrativeOutbox(
            report_id=h2.id,
            snapshot_hash=h2.snapshot_hash,
            event_kind="initialize_narrative_v1",
            state="processed",
            available_at=snapshot.generated_at,
            generation_key=generation_key,
            processed_at=snapshot.generated_at,
        )
    )
    staged_projection = build_public_h2(
        snapshot,
        narrative_binding=SimpleNamespace(narrative=narrative),
        projection_binding=PublicH2ProjectionBindingV1(
            projection_scope="staged_publication",
            canonical_path=profile["canonical_path"],
            indexable=False,
            published_lastmod=None,
        ),
        finance_enabled=True,
        arbitration_enabled=True,
    )
    staged_pin, _pointer = await append_resolved_h2_pin(
        session,
        report=h2,
        artifact=artifact,
        projection_digest=staged_projection.projection_digest,
    )
    active_projection = await build_active_public_h2_for_pin(
        session,
        record=h2,
        source_pin=staged_pin,
        expected_subject_id=subject.id,
        expected_inn=profile["inn"],
        canonical_path=profile["canonical_path"],
        indexable=False,
        published_lastmod=snapshot.generated_at,
    )
    outcome = await assign_rollout_pin_cas(
        session,
        command=RolloutAssignmentCommand(
            decision_id=DECISION_ID,
            decision_digest=decision_digest,
            schema_version="company_card_v2_rollout_decision_v1",
            release_commit=release_sha,
            action="activate",
            stage="allowlist",
            h2_indexable=False,
            target_count=target_count,
            reason_code="activate_allowlist",
            subject_id=subject.id,
            inn=profile["inn"],
            expected_assignment_generation=0,
            expected_current_contract=None,
            expected_current_pin_generation=None,
            expected_rollout_generation=h2.rollout_generation,
            target_contract="company_public_h2_v1",
            target_pin_generation=staged_pin.generation + 1,
            source_h2_pin_generation=staged_pin.generation,
            h1_rollback_pin_generation=h1_pin.generation,
            expected_target_projection_digest=active_projection.projection_digest,
        ),
    )
    if outcome.code != "applied":
        raise SeederContractError("profile assignment did not apply")
    resolved = await resolve_public_h2(session, inn=profile["inn"])
    if (
        resolved.report_id != profile["h2_report_id"]
        or resolved.canonical_path != profile["canonical_path"]
        or resolved.indexable is not False
        or resolved.projection_digest != active_projection.projection_digest
    ):
        raise SeederContractError("seeded public projection is inconsistent")


async def seed_database(
    database_url: str,
    profiles: tuple[dict[str, Any], ...],
    *,
    release_sha: str,
) -> dict[str, int]:
    engine = create_async_engine(database_url)
    try:
        async with AsyncSession(bind=engine, expire_on_commit=False) as session:
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != EXPECTED_HEAD:
                raise SeederContractError("database is not at exact iteration-25 head")
            existing = await session.scalar(select(func.count()).select_from(CompanyReportSubject))
            if existing != 0:
                raise SeederContractError("acceptance database must be empty")
            decision_payload = {
                "schema_version": "company_card_v2_rollout_decision_v1",
                "decision_id": str(DECISION_ID),
                "release_commit": release_sha,
                "action": "activate",
                "stage": "allowlist",
                "target_contract": "company_public_h2_v1",
                "h2_indexable": False,
                "profile_ids": list(PROFILE_IDS),
            }
            decision_digest = sha256(canonical_json_bytes(decision_payload)).hexdigest()
            await bind_rollout_decision(
                session,
                decision_id=DECISION_ID,
                decision_digest=decision_digest,
                schema_version="company_card_v2_rollout_decision_v1",
                release_commit=release_sha,
                action="activate",
                stage="allowlist",
                target_contract="company_public_h2_v1",
                h2_indexable=False,
                target_count=len(profiles),
            )
            for profile in profiles:
                await _seed_profile(
                    session,
                    profile=profile,
                    decision_digest=decision_digest,
                    release_sha=release_sha,
                    target_count=len(profiles),
                )
            await session.commit()
            counts: dict[str, int] = {}
            for label, model in (
                ("subjects", CompanyReportSubject),
                ("reports", CompanyReportRecord),
                ("pins", CompanyReportPresentationPin),
                ("assignments", CompanyReportPresentationAssignment),
                ("journal", CompanyReportPresentationAssignmentJournal),
                ("decisions", CompanyCardV2RolloutDecision),
            ):
                counts[label] = int(
                    await session.scalar(select(func.count()).select_from(model)) or 0
                )
            expected = {
                "subjects": 5,
                "reports": 10,
                "pins": 20,
                "assignments": 5,
                "journal": 5,
                "decisions": 1,
            }
            if counts != expected:
                raise SeederContractError("seeded aggregate counts are inconsistent")
            return counts
    except SeederContractError:
        raise
    except Exception as exc:
        raise SeederContractError("disposable database seeding failed") from exc
    finally:
        await engine.dispose()


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    if len(payload) > 1_048_576:
        raise SeederContractError("browser manifest exceeds the technical cap")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise SeederContractError("browser manifest temporary path already exists")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise SeederContractError("browser manifest output already exists") from exc
        temporary.unlink()
    finally:
        if temporary.exists():
            temporary.unlink()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--database-name", required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--manifest-output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        profiles = load_profile_registry()
        target = validate_runner_database(arguments.database_url, arguments.database_name)
        output = validate_manifest_output(arguments.manifest_output)
        manifest = build_e2e_manifest(profiles, release_sha=arguments.release_sha)
        counts = asyncio.run(
            seed_database(
                target.render_as_string(hide_password=False),
                profiles,
                release_sha=arguments.release_sha,
            )
        )
        _write_manifest(output, manifest)
    except SeederContractError as exc:
        print(f"acceptance seeder failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "counts": counts,
                "profiles": [profile["profile_id"] for profile in profiles],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
