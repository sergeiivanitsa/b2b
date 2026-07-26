from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

TESTS_UNIT = Path(__file__).resolve().parents[1] / "tests_unit"
if str(TESTS_UNIT) not in sys.path:
    sys.path.append(str(TESTS_UNIT))

from company_report_signal_test_helpers import complete_company_report, counterparty_facts
from product_api.company_reports.persistence.models import (
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
    company_report_to_snapshot,
)
from product_api.models import Claim, ClaimEvent
from product_api.settings import get_settings

from .utils import create_company, create_session_cookie, create_user


pytestmark = pytest.mark.asyncio

_PATH = "/claims/handoff/company-reports"


async def _store_final_report(
    engine,
    *,
    inn: str,
    name: str,
    subject_id: UUID | None = None,
) -> tuple[UUID, UUID]:
    now = datetime.now(timezone.utc)
    report_id = uuid4()
    counterparty = counterparty_facts().model_copy(
        update={"inn": inn, "short_name": name, "full_name": name}
    )
    report = complete_company_report(counterparty=counterparty).model_copy(
        update={
            "report_id": report_id,
            "generated_at": now,
            "target_identifier": inn,
        }
    )
    snapshot = company_report_to_snapshot(report)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        if subject_id is None:
            subject = CompanyReportSubject(
                normalized_identifier=inn,
                identifier_type="legal_entity",
            )
            session.add(subject)
            await session.flush()
            subject_id = subject.id
        session.add(
            CompanyReportRecord(
                id=report_id,
                subject_id=subject_id,
                report_version=report.report_version,
                lifecycle_status=report.status.value,
                started_at=now,
                generated_at=now,
                finished_at=now,
                normalized_snapshot=snapshot,
                snapshot_hash=calculate_company_report_snapshot_hash(snapshot),
                completeness_snapshot={},
                freshness_snapshot={},
                warnings_snapshot=[],
                usable_for_public_page=True,
                usable_for_future_scoring=True,
            )
        )
        await session.commit()
    return subject_id, report_id


async def _store_nonfinal_report(engine, *, inn: str, status: str) -> UUID:
    now = datetime.now(timezone.utc)
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        subject = CompanyReportSubject(
            normalized_identifier=inn,
            identifier_type="legal_entity",
        )
        session.add(subject)
        await session.flush()
        record = CompanyReportRecord(
            subject_id=subject.id,
            report_version="v1",
            lifecycle_status=status,
            started_at=now,
            finished_at=now if status == "failed" else None,
            normalized_snapshot=None,
            snapshot_hash=None,
            completeness_snapshot=None,
            freshness_snapshot=None,
            warnings_snapshot=[],
            usable_for_public_page=False,
            usable_for_future_scoring=False,
        )
        session.add(record)
        await session.commit()
        return record.id


async def _member_cookies(engine, *, email: str, company_inn: str) -> dict[str, str]:
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        company = await create_company(
            session,
            name=f"Company {company_inn}",
            inn=company_inn,
        )
        user = await create_user(
            session,
            email=email,
            role="member",
            company_id=company.id,
        )
        raw_cookie = await create_session_cookie(session, user.id)
    return {get_settings().session_cookie_name: raw_cookie}


async def test_linked_create_is_trusted_idempotent_and_keeps_safe_audit(
    async_client,
    engine,
):
    subject_id, report_id = await _store_final_report(
        engine,
        inn="7700000000",
        name="ООО Вектор",
    )
    cookies = await _member_cookies(
        engine,
        email="handoff-member@example.com",
        company_inn="7800000000",
    )

    preflight = await async_client.get(f"{_PATH}/{report_id}", cookies=cookies)
    assert preflight.status_code == 200
    assert preflight.json() == {
        "report_id": str(report_id),
        "availability": "available",
        "reason": None,
        "prefill": {"debtor_name": "ООО Вектор", "debtor_inn": "7700000000"},
        "prefilled_fields": ["debtor_name", "debtor_inn"],
    }

    request = {
        "headers": {"Idempotency-Key": "same-command-1"},
        "cookies": cookies,
        "json": {"input_text": "Поставка по договору 17 не оплачена"},
    }
    created = await async_client.post(f"{_PATH}/{report_id}", **request)
    repeated = await async_client.post(f"{_PATH}/{report_id}", **request)
    assert created.status_code == repeated.status_code == 200
    first = created.json()
    second = repeated.json()
    assert first["reused"] is False
    assert second["reused"] is True
    assert second["claim_id"] == first["claim_id"]
    assert second["edit_token"] == first["edit_token"]
    assert first["claim"]["source_company_report_id"] == str(report_id)
    assert first["claim"]["normalized_data"]["debtor_name"] == "ООО Вектор"
    assert first["claim"]["normalized_data"]["debtor_inn"] == "7700000000"

    injected = await async_client.post(
        f"{_PATH}/{report_id}",
        headers={"Idempotency-Key": "injection-attempt"},
        cookies=cookies,
        json={
            "input_text": "Факты требования",
            "debtor_name": "Подмена с клиента",
            "scoring": {"level": "high"},
        },
    )
    assert injected.status_code == 422

    conflict = await async_client.post(
        f"{_PATH}/{report_id}",
        headers={"Idempotency-Key": "same-command-1"},
        cookies=cookies,
        json={"input_text": "Другой долг"},
    )
    assert conflict.status_code == 409
    assert "claim_id" not in json.dumps(conflict.json())
    assert "edit_token" not in json.dumps(conflict.json())

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claims = (
            await session.execute(select(Claim).order_by(Claim.id))
        ).scalars().all()
        events = (
            await session.execute(
                select(ClaimEvent).where(ClaimEvent.claim_id == first["claim_id"])
            )
        ).scalars().all()
        assert len(claims) == 1
        assert len(events) == 1
        claim = claims[0]
        assert claim.source_company_report_id == report_id
        assert claim.handoff_idempotency_key_hash != "same-command-1"
        persisted = json.dumps(claim.normalized_data_json, ensure_ascii=False)
        audit = json.dumps(events[0].payload_json, ensure_ascii=False)
        for forbidden in (
            "raw_payload",
            "provider_journal",
            "scoring",
            "signals",
            "ai_explanation",
            "worker",
        ):
            assert forbidden not in persisted
            assert forbidden not in audit

    # A later report for the same subject does not rewrite or break the exact
    # immutable source reference stored on the Claim.
    _, newer_report_id = await _store_final_report(
        engine,
        inn="7700000000",
        name="ООО Вектор — новая выписка",
        subject_id=subject_id,
    )
    assert newer_report_id != report_id
    restored = await async_client.get(
        f"/claims/{first['claim_id']}",
        headers={"X-Claim-Edit-Token": first["edit_token"]},
    )
    assert restored.status_code == 200
    assert restored.json()["source_company_report_id"] == str(report_id)
    assert restored.json()["normalized_data"]["debtor_name"] == "ООО Вектор"


async def test_same_actor_concurrent_command_creates_one_draft_and_event(
    async_client,
    engine,
):
    _, report_id = await _store_final_report(
        engine,
        inn="7711111111",
        name="ООО Конкурентный тест",
    )
    cookies = await _member_cookies(
        engine,
        email="race-member@example.com",
        company_inn="7811111111",
    )

    async def create_once():
        return await async_client.post(
            f"{_PATH}/{report_id}",
            headers={"Idempotency-Key": "concurrent-command"},
            cookies=cookies,
            json={"input_text": "Одинаковые факты"},
        )

    left, right = await asyncio.gather(create_once(), create_once())
    assert left.status_code == right.status_code == 200
    assert left.json()["claim_id"] == right.json()["claim_id"]
    assert left.json()["edit_token"] == right.json()["edit_token"]
    assert sorted((left.json()["reused"], right.json()["reused"])) == [False, True]

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        assert await session.scalar(select(func.count()).select_from(Claim)) == 1
        assert await session.scalar(select(func.count()).select_from(ClaimEvent)) == 1


async def test_same_raw_key_is_isolated_between_authenticated_actors(
    async_client,
    engine,
):
    _, report_id = await _store_final_report(
        engine,
        inn="7722222222",
        name="ООО Два пользователя",
    )
    first_cookies = await _member_cookies(
        engine,
        email="first-member@example.com",
        company_inn="7822222222",
    )
    second_cookies = await _member_cookies(
        engine,
        email="second-member@example.com",
        company_inn="7833333333",
    )
    request = {
        "headers": {"Idempotency-Key": "shared-browser-key"},
        "json": {"input_text": "Одинаковые факты"},
    }

    first = await async_client.post(
        f"{_PATH}/{report_id}",
        cookies=first_cookies,
        **request,
    )
    second = await async_client.post(
        f"{_PATH}/{report_id}",
        cookies=second_cookies,
        **request,
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["claim_id"] != second.json()["claim_id"]
    assert first.json()["edit_token"] != second.json()["edit_token"]

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        hashes = (
            await session.execute(
                select(Claim.handoff_idempotency_key_hash).order_by(Claim.id)
            )
        ).scalars().all()
        assert len(hashes) == 2
        assert hashes[0] != hashes[1]
        assert "shared-browser-key" not in hashes


async def test_handoff_requires_auth_and_handles_missing_pending_and_failed_reports(
    async_client,
    engine,
):
    pending_id = await _store_nonfinal_report(
        engine,
        inn="7733333333",
        status="pending",
    )
    failed_id = await _store_nonfinal_report(
        engine,
        inn="7744444444",
        status="failed",
    )
    cookies = await _member_cookies(
        engine,
        email="state-member@example.com",
        company_inn="7844444444",
    )

    unauthenticated = await async_client.get(f"{_PATH}/{pending_id}")
    assert unauthenticated.status_code in {401, 403}

    missing = await async_client.get(f"{_PATH}/{uuid4()}", cookies=cookies)
    assert missing.status_code == 404
    assert missing.json()["detail"] == {"code": "company_report_not_found"}

    pending = await async_client.get(f"{_PATH}/{pending_id}", cookies=cookies)
    failed = await async_client.get(f"{_PATH}/{failed_id}", cookies=cookies)
    assert pending.json()["availability"] == "manual_required"
    assert pending.json()["reason"] == "report_pending"
    assert failed.json()["availability"] == "manual_required"
    assert failed.json()["reason"] == "report_failed"

    rejected = await async_client.post(
        f"{_PATH}/{pending_id}",
        headers={"Idempotency-Key": "pending-command"},
        cookies=cookies,
        json={"input_text": "Факты"},
    )
    assert rejected.status_code == 409
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        assert await session.scalar(select(func.count()).select_from(Claim)) == 0


async def test_swapped_valid_hash_snapshot_is_rejected_without_creating_claim(
    async_client,
    engine,
):
    _, first_report_id = await _store_final_report(
        engine,
        inn="7755555555",
        name="ООО Первая запись",
    )
    _, second_report_id = await _store_final_report(
        engine,
        inn="7766666666",
        name="ООО Вторая запись",
    )
    cookies = await _member_cookies(
        engine,
        email="swap-member@example.com",
        company_inn="7866666666",
    )

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        first = await session.get(CompanyReportRecord, first_report_id)
        second = await session.get(CompanyReportRecord, second_report_id)
        assert first is not None and second is not None
        swapped = deepcopy(second.normalized_snapshot)
        assert isinstance(swapped, dict)
        first.normalized_snapshot = swapped
        first.snapshot_hash = calculate_company_report_snapshot_hash(swapped)
        await session.commit()

    preflight = await async_client.get(
        f"{_PATH}/{first_report_id}",
        cookies=cookies,
    )
    assert preflight.status_code == 200
    assert preflight.json()["availability"] == "manual_required"
    assert preflight.json()["reason"] == "invalid_report"
    assert preflight.json()["prefill"] == {}

    create = await async_client.post(
        f"{_PATH}/{first_report_id}",
        headers={"Idempotency-Key": "swapped-command"},
        cookies=cookies,
        json={"input_text": "Факты"},
    )
    assert create.status_code == 409
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        assert await session.scalar(select(func.count()).select_from(Claim)) == 0
