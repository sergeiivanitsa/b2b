from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from company_report_signal_test_helpers import complete_company_report, counterparty_facts
from product_api.company_reports.persistence.models import (
    PUBLICATION_POLICY_VERSION,
    CompanyReportPublication,
    CompanyReportPublicationBatch,
    CompanyReportPublicationBatchItem,
    CompanyReportPublicationControl,
    CompanyReportPublicationJournal,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.persistence import publications
from product_api.company_reports.persistence.publications import PublicationBatchClaim, PublicationStateConflictError, _validated_publication_report
from product_api.company_reports.persistence.serialization import calculate_company_report_snapshot_hash, company_report_to_snapshot
from product_api.company_reports.persistence.public_h1 import list_report_resolution_records


@pytest.mark.asyncio
async def test_publication_equal_generated_at_uses_id_not_created_at():
    class Result:
        def all(self): return []
    class Session:
        def __init__(self): self.statement = None
        async def execute(self, statement): self.statement = statement; return Result()
    session = Session()
    assert await list_report_resolution_records(session, "0000000000") == []
    order_by = str(session.statement).split("ORDER BY", 1)[1]
    assert "generated_at DESC NULLS LAST" in order_by and "company_reports.id DESC" in order_by
    assert "created_at" not in order_by


def test_publication_schema_has_five_separate_fail_closed_tables():
    assert CompanyReportPublicationControl.__table__.name == "company_report_publication_control"
    assert CompanyReportPublication.__table__.name == "company_report_publications"
    assert CompanyReportPublicationBatch.__table__.name == "company_report_publication_batches"
    assert CompanyReportPublicationBatchItem.__table__.name == "company_report_publication_batch_items"
    assert CompanyReportPublicationJournal.__table__.name == "company_report_publication_journal"
    assert any(index.name == "ix_company_report_publications_sitemap" for index in CompanyReportPublication.__table__.indexes)
    assert str(CompanyReportPublication.__table__.c.indexable.server_default.arg) == "false"
    assert str(CompanyReportPublicationBatch.__table__.c.next_ordinal.server_default.arg) == "0"


def test_publication_reason_constraints_cover_every_policy_outcome():
    item_constraints = {
        str(constraint.name): str(constraint.sqltext)
        for constraint in CompanyReportPublicationBatchItem.__table__.constraints
        if getattr(constraint, "name", None) and hasattr(constraint, "sqltext")
    }
    journal_constraints = {
        str(constraint.name): str(constraint.sqltext)
        for constraint in CompanyReportPublicationJournal.__table__.constraints
        if getattr(constraint, "name", None) and hasattr(constraint, "sqltext")
    }
    item_reason = next(
        value
        for name, value in item_constraints.items()
        if name.endswith("company_report_publication_batch_item_reason")
    )
    journal_reason = next(
        value
        for name, value in journal_constraints.items()
        if name.endswith("company_report_publication_journal_reason")
    )
    for reason in ("report_not_finalized", "report_not_usable"):
        assert reason in item_reason
        assert reason in journal_reason


def _finalization_matrix():
    model = complete_company_report(counterparty=counterparty_facts().model_copy(update={"inn": "0000000000", "full_name": "ООО Тест"}), report_version="2")
    snapshot = company_report_to_snapshot(model)
    digest = calculate_company_report_snapshot_hash(snapshot)
    batch = SimpleNamespace(id="batch", policy_version=PUBLICATION_POLICY_VERSION)
    subject = SimpleNamespace(id="subject", normalized_identifier="0000000000")
    item = SimpleNamespace(batch_id=batch.id, subject_id=subject.id, report_id=model.report_id, snapshot_hash=digest, policy_version=PUBLICATION_POLICY_VERSION)
    report = SimpleNamespace(id=model.report_id, subject_id=subject.id, lifecycle_status="complete", report_version="2", normalized_snapshot=snapshot, snapshot_hash=digest, generated_at=model.generated_at)
    return batch, item, report, subject


def test_publication_pre_upsert_matrix_accepts_exact_identity():
    batch, item, report, subject = _finalization_matrix()
    assert _validated_publication_report(batch=batch, item=item, report=report, subject=subject).report_id == report.id


def _real_finalizer_case():
    batch_id, item_id, token = uuid4(), uuid4(), uuid4()
    model = complete_company_report(
        counterparty=counterparty_facts().model_copy(
            update={"inn": "0000000000", "full_name": "ООО Тест"}
        ),
        report_version="2",
    )
    snapshot = company_report_to_snapshot(model)
    digest = calculate_company_report_snapshot_hash(snapshot)
    subject_id = uuid4()
    batch = SimpleNamespace(
        id=batch_id,
        next_ordinal=0,
        candidate_count=1,
        generation=1,
        state="running",
        completed_at=None,
        claimed_ordinal=None,
        policy_version=PUBLICATION_POLICY_VERSION,
    )
    item = SimpleNamespace(
        id=item_id,
        batch_id=batch_id,
        ordinal=0,
        state="claimed",
        claim_token=token,
        report_id=model.report_id,
        subject_id=subject_id,
        snapshot_hash=digest,
        policy_version=PUBLICATION_POLICY_VERSION,
    )
    report = SimpleNamespace(
        id=model.report_id,
        subject_id=subject_id,
        lifecycle_status="complete",
        report_version="2",
        normalized_snapshot=snapshot,
        snapshot_hash=digest,
        generated_at=model.generated_at,
    )
    subject = SimpleNamespace(
        id=subject_id,
        normalized_identifier="0000000000",
    )
    claim = PublicationBatchClaim(batch_id=batch_id, item_id=item_id, ordinal=0, token=token)
    return SimpleNamespace(
        batch=batch,
        item=item,
        report=report,
        subject=subject,
        subjects={subject.id: subject},
        claim=claim,
    )


def _replace_raw(case, mutate, *, rehash=True):
    raw = deepcopy(case.report.normalized_snapshot)
    mutate(raw)
    case.report.normalized_snapshot = raw
    if rehash:
        digest = calculate_company_report_snapshot_hash(raw)
        case.report.snapshot_hash = digest
        case.item.snapshot_hash = digest


def _apply_finalizer_mismatch(case, name):
    alternate_id = uuid4()
    if name == "claim_batch_lookup":
        case.claim = PublicationBatchClaim(uuid4(), case.claim.item_id, 0, case.claim.token)
    elif name == "claim_item_lookup":
        case.claim = PublicationBatchClaim(case.claim.batch_id, uuid4(), 0, case.claim.token)
    elif name == "batch_cursor":
        case.batch.next_ordinal = 1
    elif name == "item_batch":
        case.item.batch_id = alternate_id
    elif name == "item_ordinal":
        case.item.ordinal = 1
    elif name == "item_state":
        case.item.state = "pending"
        case.item.claim_token = None
    elif name == "item_token":
        case.item.claim_token = uuid4()
    elif name == "item_policy":
        case.item.policy_version = "alternate_policy"
    elif name == "batch_policy":
        case.batch.policy_version = "alternate_policy"
    elif name == "alternate_subject":
        alternate = SimpleNamespace(id=alternate_id, normalized_identifier="1111111111")
        case.subjects[alternate_id] = alternate
        case.item.subject_id = alternate_id
    elif name == "missing_report_lookup":
        case.item.report_id = uuid4()
    elif name == "missing_subject_lookup":
        case.item.subject_id = uuid4()
    elif name == "item_hash":
        case.item.snapshot_hash = "0" * 64
    elif name == "raw_hash":
        _replace_raw(case, lambda raw: raw.__setitem__("target_identifier", "1111111111"), rehash=False)
    elif name == "non_object_snapshot":
        case.report.normalized_snapshot = []
    elif name == "missing_stored_hash":
        case.report.snapshot_hash = None
    elif name == "lifecycle_pending":
        case.report.lifecycle_status = "pending"
    elif name == "lifecycle_failed":
        case.report.lifecycle_status = "failed"
    elif name == "unknown_orm_version":
        case.report.report_version = "unknown"
    elif name == "missing_generated_at":
        case.report.generated_at = None
    elif name == "wrong_subject_identifier":
        case.subject.normalized_identifier = "1111111111"
    elif name == "raw_version_missing":
        _replace_raw(case, lambda raw: raw.pop("report_version"))
    elif name == "raw_version_non_string":
        _replace_raw(case, lambda raw: raw.__setitem__("report_version", 2))
    elif name == "raw_version_unknown":
        _replace_raw(case, lambda raw: raw.__setitem__("report_version", "3"))
    elif name.startswith("raw_v2_missing_"):
        _replace_raw(case, lambda raw: raw.pop(name.removeprefix("raw_v2_missing_")))
    elif name == "raw_v1_contains_v2":
        _replace_raw(case, lambda raw: raw.__setitem__("report_version", "1"))
    elif name == "parsed_report_id":
        _replace_raw(case, lambda raw: raw.__setitem__("report_id", str(uuid4())))
    elif name == "parsed_report_version":
        case.report.report_version = "1"
    elif name == "parsed_status":
        _replace_raw(case, lambda raw: raw.__setitem__("status", "partial"))
    elif name == "parsed_generated_at":
        changed = (case.report.generated_at + timedelta(seconds=1)).isoformat()
        _replace_raw(case, lambda raw: raw.__setitem__("generated_at", changed))
    elif name == "parsed_target":
        _replace_raw(case, lambda raw: raw.__setitem__("target_identifier", "1111111111"))
    elif name == "missing_counterparty":
        _replace_raw(case, lambda raw: raw.__setitem__("counterparty", None))
    elif name == "counterparty_inn":
        _replace_raw(case, lambda raw: raw["counterparty"].__setitem__("inn", "1111111111"))
    elif name == "item_hash_not_null_constraint":
        case.item.snapshot_hash = None
    else:
        raise AssertionError(f"unknown finalizer case: {name}")


_FINALIZER_MISMATCHES = [
    ("claim_batch_lookup", "unit_only: AsyncSession.get exact batch primary key"),
    ("claim_item_lookup", "unit_only: AsyncSession.get exact item primary key"),
    ("batch_cursor", "postgresql"),
    ("item_batch", "postgresql"),
    ("item_ordinal", "postgresql"),
    ("item_state", "postgresql"),
    ("item_token", "postgresql"),
    ("item_policy", "postgresql"),
    ("batch_policy", "postgresql"),
    ("alternate_subject", "postgresql"),
    ("missing_report_lookup", "unit_only: report foreign key"),
    ("missing_subject_lookup", "unit_only: subject foreign key"),
    ("item_hash", "postgresql"),
    ("raw_hash", "postgresql"),
    ("non_object_snapshot", "postgresql"),
    ("missing_stored_hash", "postgresql"),
    ("lifecycle_pending", "postgresql"),
    ("lifecycle_failed", "postgresql"),
    ("unknown_orm_version", "postgresql"),
    ("missing_generated_at", "postgresql"),
    ("wrong_subject_identifier", "postgresql"),
    ("raw_version_missing", "postgresql"),
    ("raw_version_non_string", "postgresql"),
    ("raw_version_unknown", "postgresql"),
    ("raw_v2_missing_optional_datasets", "postgresql"),
    ("raw_v2_missing_tax_info", "postgresql"),
    ("raw_v2_missing_bankruptcy", "postgresql"),
    ("raw_v1_contains_v2", "postgresql"),
    ("parsed_report_id", "postgresql"),
    ("parsed_report_version", "postgresql"),
    ("parsed_status", "postgresql"),
    ("parsed_generated_at", "postgresql"),
    ("parsed_target", "postgresql"),
    ("missing_counterparty", "postgresql"),
    ("counterparty_inn", "postgresql"),
    ("item_hash_not_null_constraint", "unit_only: item snapshot_hash NOT NULL"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mismatch", "protection"),
    _FINALIZER_MISMATCHES,
    ids=[item[0] for item in _FINALIZER_MISMATCHES],
)
async def test_real_finalizer_integrity_matrix_never_reaches_evaluator_or_upsert(
    monkeypatch,
    mismatch,
    protection,
):
    case = _real_finalizer_case()
    _apply_finalizer_mismatch(case, mismatch)

    class Nested:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False

    class Session:
        async def get(self, model, key, **_kwargs):
            if model is CompanyReportPublicationBatch:
                return case.batch if key == case.batch.id else None
            if model is CompanyReportPublicationBatchItem:
                return case.item if key == case.item.id else None
            if model is CompanyReportRecord:
                return case.report if key == case.report.id else None
            if model is CompanyReportSubject:
                return case.subjects.get(key)
            return None
        async def scalar(self, _statement): return None
        async def execute(self, _statement): return SimpleNamespace(rowcount=1)
        def begin_nested(self): return Nested()
        def add(self, _value): pass
        async def flush(self): pass

    calls = {"evaluator": 0, "upsert": 0}

    def forbidden(*_args, **_kwargs):
        calls["evaluator"] += 1
        raise AssertionError("evaluator/upsert must be unreachable")
    async def forbidden_async(*_args, **_kwargs):
        calls["upsert"] += 1
        raise AssertionError("upsert must be unreachable")

    monkeypatch.setattr(publications, "evaluate_publication", forbidden)
    monkeypatch.setattr(publications, "_upsert_publication", forbidden_async)
    if mismatch in {"claim_batch_lookup", "claim_item_lookup", "batch_cursor", "item_batch", "item_ordinal", "item_state", "item_token"}:
        with pytest.raises(PublicationStateConflictError):
            await publications.finalize_batch_claim(Session(), claim=case.claim)
    else:
        result = await publications.finalize_batch_claim(Session(), claim=case.claim)
        assert result is case.batch
        assert case.batch.state == "completed" and case.batch.next_ordinal == 1
    assert calls == {"evaluator": 0, "upsert": 0}
    assert protection == "postgresql" or protection.startswith("unit_only:")


@pytest.mark.asyncio
async def test_real_finalizer_rejects_existing_presentation_assignment_before_policy(
    monkeypatch,
):
    case = _real_finalizer_case()

    class Nested:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False

    class Session:
        def __init__(self):
            self.finalize_statement = None

        async def get(self, model, key, **_kwargs):
            if model is CompanyReportPublicationBatch:
                return case.batch if key == case.batch.id else None
            if model is CompanyReportPublicationBatchItem:
                return case.item if key == case.item.id else None
            if model is CompanyReportRecord:
                return case.report if key == case.report.id else None
            if model is CompanyReportSubject:
                return case.subjects.get(key)
            return None

        async def scalar(self, _statement):
            return SimpleNamespace(id=uuid4())

        async def execute(self, statement):
            self.finalize_statement = statement
            return SimpleNamespace(rowcount=1)

        def begin_nested(self): return Nested()
        def add(self, _value): pass
        async def flush(self): pass

    calls = {"evaluator": 0, "upsert": 0}

    def forbidden(*_args, **_kwargs):
        calls["evaluator"] += 1
        raise AssertionError("evaluator must be unreachable")

    async def forbidden_async(*_args, **_kwargs):
        calls["upsert"] += 1
        raise AssertionError("upsert must be unreachable")

    monkeypatch.setattr(publications, "evaluate_publication", forbidden)
    monkeypatch.setattr(publications, "_upsert_publication", forbidden_async)
    session = Session()

    result = await publications.finalize_batch_claim(session, claim=case.claim)

    assert result is case.batch
    assert calls == {"evaluator": 0, "upsert": 0}
    assert session.finalize_statement.compile().params["state"] == "failed"
    assert session.finalize_statement.compile().params["reason_code"] == "state_conflict"
