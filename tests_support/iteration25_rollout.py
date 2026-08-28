"""Shared synthetic setup for iteration-25 real-PostgreSQL acceptance tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from product_api.company_reports.company_card_v2.canonical_json import (
    canonical_json_bytes,
)
from product_api.company_reports.company_card_v2.rollout import RolloutRuntimeConfig
from product_api.company_reports.company_card_v2.rollout_models import (
    ParsedRolloutDecisionV1,
    parse_rollout_decision,
)
from product_api.company_reports.company_card_v2.service import (
    build_active_public_h2_for_pin,
)
from product_api.company_reports.persistence.models import (
    CompanyCardV2RolloutDecision,
    CompanyReportPresentationAssignment,
    CompanyReportPresentationAssignmentJournal,
    CompanyReportPresentationPin,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.presentations import (
    H2_ACTIVE_PROJECTION_SCOPE,
    H2_STAGED_PROJECTION_SCOPE,
)


RELEASE_SHA = "a" * 40
H1_CONTRACT = "company_public_h1_v1"
H2_CONTRACT = "company_public_h2_v1"


def load_acceptance_seeder() -> ModuleType:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "seed-iteration25-company-card-v2-acceptance.py"
    spec = importlib.util.spec_from_file_location(
        "iteration25_acceptance_seed_for_postgres", script
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("iteration-25 acceptance seeder is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def prepare_unassigned_acceptance_seed(
    engine: AsyncEngine,
    database_url: str,
) -> tuple[dict[str, Any], ...]:
    """Seed the closed profiles, then remove only rollout bindings.

    Immutable H1, staged H2 and active-noindex H2 pins remain.  This gives the
    operator real reusable targets while preserving an assignment-free start.
    """

    seeder = load_acceptance_seeder()
    profiles = seeder.load_profile_registry()
    await seeder.seed_database(database_url, profiles, release_sha=RELEASE_SHA)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        async with session.begin():
            await session.execute(delete(CompanyReportPresentationAssignmentJournal))
            await session.execute(delete(CompanyReportPresentationAssignment))
            await session.execute(delete(CompanyCardV2RolloutDecision))
    return profiles


async def build_activation_decision(
    engine: AsyncEngine,
    profiles: Iterable[dict[str, Any]],
    *,
    decision_id: str,
    indexable: bool,
) -> tuple[ParsedRolloutDecisionV1, RolloutRuntimeConfig]:
    selected = tuple(sorted(profiles, key=lambda item: item["inn"]))
    if not selected:
        raise ValueError("activation fixture requires at least one profile")
    targets: list[dict[str, Any]] = []
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        for profile in selected:
            subject = await session.scalar(
                select(CompanyReportSubject).where(
                    CompanyReportSubject.id == UUID(profile["subject_id"])
                )
            )
            if subject is None or subject.normalized_identifier != profile["inn"]:
                raise RuntimeError("seeded rollout subject is inconsistent")
            pins = list(
                (
                    await session.scalars(
                        select(CompanyReportPresentationPin)
                        .where(CompanyReportPresentationPin.subject_id == subject.id)
                        .order_by(
                            CompanyReportPresentationPin.presentation_contract,
                            CompanyReportPresentationPin.generation,
                        )
                    )
                ).all()
            )
            h1_pin = next(
                pin for pin in pins if pin.presentation_contract == H1_CONTRACT
            )
            source_pin = next(
                pin
                for pin in pins
                if pin.presentation_contract == H2_CONTRACT
                and pin.projection_scope == H2_STAGED_PROJECTION_SCOPE
                and pin.narrative_binding_status == "resolved"
            )
            report = await session.get(CompanyReportRecord, source_pin.report_id)
            if report is None:
                raise RuntimeError("seeded rollout report is missing")
            projection = await build_active_public_h2_for_pin(
                session,
                record=report,
                source_pin=source_pin,
                expected_subject_id=subject.id,
                expected_inn=profile["inn"],
                canonical_path=profile["canonical_path"],
                indexable=indexable,
                published_lastmod=report.generated_at,
            )
            reusable = next(
                (
                    pin
                    for pin in pins
                    if pin.presentation_contract == H2_CONTRACT
                    and pin.projection_scope == H2_ACTIVE_PROJECTION_SCOPE
                    and pin.projection_digest == projection.projection_digest
                    and pin.canonical_path == projection.canonical_path
                    and pin.indexable is projection.indexable
                    and pin.published_lastmod == report.generated_at
                ),
                None,
            )
            target_generation = (
                reusable.generation
                if reusable is not None
                else max(
                    pin.generation
                    for pin in pins
                    if pin.presentation_contract == H2_CONTRACT
                )
                + 1
            )
            targets.append(
                {
                    "subject_id": str(subject.id),
                    "inn": profile["inn"],
                    "expected_assignment_generation": 0,
                    "expected_current_contract": None,
                    "expected_current_pin_generation": None,
                    "source_h2_pin_generation": source_pin.generation,
                    "expected_active_h2_pin_generation": target_generation,
                    "expected_active_projection_digest": projection.projection_digest,
                    "h1_rollback_pin_generation": h1_pin.generation,
                }
            )
    inns = [profile["inn"] for profile in selected]
    parsed = parse_rollout_decision(
        canonical_json_bytes(
            {
                "schema_version": "company_card_v2_rollout_decision_v1",
                "decision_id": decision_id,
                "authorization_reference": "P3-iteration25-postgres",
                "release_commit": RELEASE_SHA,
                "rollout_generation": 1,
                "action": "activate",
                "stage": "allowlist",
                "target_contract": H2_CONTRACT,
                "h2_indexable": indexable,
                "allowlist_inns": inns,
                "percentage_basis_points": 0,
                "maximum_batch_size": len(targets),
                "observation_window_seconds": 60,
                "abort_policy_reference": "P4-iteration25-postgres",
                "targets": targets,
            }
        )
    )
    return parsed, RolloutRuntimeConfig(
        database_url="",
        product_release_commit=RELEASE_SHA,
        rollout_generation=1,
        allowlist_inns=tuple(inns),
        percentage_basis_points=0,
    )


async def build_rollback_decision(
    engine: AsyncEngine,
    profiles: Iterable[dict[str, Any]],
    *,
    decision_id: str,
) -> ParsedRolloutDecisionV1:
    selected = tuple(sorted(profiles, key=lambda item: item["inn"]))
    targets: list[dict[str, Any]] = []
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        for profile in selected:
            subject_id = UUID(profile["subject_id"])
            assignment = await session.scalar(
                select(CompanyReportPresentationAssignment).where(
                    CompanyReportPresentationAssignment.subject_id == subject_id
                )
            )
            h1_pin = await session.scalar(
                select(CompanyReportPresentationPin).where(
                    CompanyReportPresentationPin.subject_id == subject_id,
                    CompanyReportPresentationPin.presentation_contract == H1_CONTRACT,
                )
            )
            if (
                assignment is None
                or assignment.presentation_contract != H2_CONTRACT
                or h1_pin is None
            ):
                raise RuntimeError("rollback fixture requires an exact H2 assignment")
            targets.append(
                {
                    "subject_id": str(subject_id),
                    "inn": profile["inn"],
                    "expected_assignment_generation": assignment.generation,
                    "expected_current_contract": assignment.presentation_contract,
                    "expected_current_pin_generation": assignment.pin_generation,
                    "h1_target_pin_generation": h1_pin.generation,
                }
            )
    return parse_rollout_decision(
        canonical_json_bytes(
            {
                "schema_version": "company_card_v2_rollout_decision_v1",
                "decision_id": decision_id,
                "authorization_reference": "P3-iteration25-postgres",
                "release_commit": RELEASE_SHA,
                "rollout_generation": None,
                "action": "rollback",
                "stage": "emergency_rollback",
                "target_contract": H1_CONTRACT,
                "h2_indexable": False,
                "allowlist_inns": None,
                "percentage_basis_points": None,
                "maximum_batch_size": len(targets),
                "observation_window_seconds": None,
                "abort_policy_reference": None,
                "targets": targets,
            }
        )
    )


def with_database_url(
    config: RolloutRuntimeConfig, database_url: str
) -> RolloutRuntimeConfig:
    return RolloutRuntimeConfig(
        database_url=database_url,
        product_release_commit=config.product_release_commit,
        rollout_generation=config.rollout_generation,
        allowlist_inns=config.allowlist_inns,
        percentage_basis_points=config.percentage_basis_points,
    )
