from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from shared.schemas import ChatRequest, ChatResponse

from product_api.company_reports.company_card_v2.narrative.catalog import (
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
    MODEL_PROFILE,
)
from product_api.company_reports.company_card_v2.narrative.models import NarrativeEvidenceEnvelope
from product_api.company_reports.company_card_v2.narrative.prompt import build_narrative_gateway_body
from product_api.company_reports.company_card_v2.narrative.service import (
    NarrativeLimits,
    NarrativePersistenceError,
    PreparedNarrativeDispatch,
    fallback_projection_digest,
    validate_gateway_artifact,
    validate_narrative_report,
)
from product_api.company_reports.company_card_v2.public_h2 import build_public_h2
from product_api.company_reports.company_card_v2.public_h2_models import PublicH2Narrative
from product_api.company_reports.persistence.models import CompanyReportSubject
from product_api.company_reports.persistence.narratives import NarrativeJobLease
from product_api.company_reports.persistence.v3 import (
    calculate_company_card_v2_snapshot_hash,
    company_card_v2_from_snapshot,
    company_card_v2_to_snapshot,
)
from product_api.company_reports.company_card_v2.narrative.validation import NarrativeValidationError


FIXTURES = Path(__file__).parent / "fixtures" / "company_card_v2"
NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)
DISPATCH_ID = UUID("123e4567-e89b-12d3-a456-426614174000")


class _SubjectSession:
    def __init__(self, subject: object) -> None:
        self.subject = subject

    async def get(self, entity, identity, **_kwargs):
        assert entity is CompanyReportSubject
        assert identity == self.subject.id
        return self.subject


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class _PolicySubjectSession(_SubjectSession):
    def __init__(self, subject: object, pins: list[object]) -> None:
        super().__init__(subject)
        self.pins = pins

    async def scalars(self, _statement):
        return _ScalarRows(self.pins)


def _raw_snapshot() -> dict[str, object]:
    return json.loads((FIXTURES / "snapshot_v3_narrative_v2.json").read_text(encoding="utf-8"))


def _record_context():
    raw = _raw_snapshot()
    card = company_card_v2_from_snapshot(raw)
    stored = company_card_v2_to_snapshot(card)
    report_id = UUID(str(raw["report_id"]))
    subject = SimpleNamespace(id=uuid4(), normalized_identifier=raw["subject_inn"])
    record = SimpleNamespace(
        id=report_id,
        subject_id=subject.id,
        report_version="3",
        lifecycle_status="complete",
        snapshot_hash=calculate_company_card_v2_snapshot_hash(stored),
        normalized_snapshot=deepcopy(stored),
        writer_profile=raw["writer_profile"],
        presentation_contract=raw["presentation_contract"],
        rollout_generation=raw["rollout_config_generation"],
    )
    return card, subject, record


async def _validated_report():
    _card, subject, record = _record_context()
    return await validate_narrative_report(_SubjectSession(subject), record=record)


async def _prepared() -> PreparedNarrativeDispatch:
    report = await _validated_report()
    evidence = NarrativeEvidenceEnvelope(
        evidence_registry_version=report.identity.evidence_registry_version,
        primary_activity_label=report.activity_label,
    )
    request = ChatRequest.model_validate(build_narrative_gateway_body(evidence, dispatch_id=DISPATCH_ID))
    lease = NarrativeJobLease(
        job_id=uuid4(),
        report_id=report.record.id,
        snapshot_hash=report.record.snapshot_hash,
        generation_key=report.generation_key,
        lease_token=uuid4(),
        fence_generation=1,
        lease_expires_at=NOW + timedelta(minutes=1),
    )
    return PreparedNarrativeDispatch(lease=lease, report=report, evidence=evidence, request=request)


def _plan_text() -> str:
    return (FIXTURES / "narrative_render_plan_valid.json").read_text(encoding="utf-8").strip()


def _response(text: str | None = None, **overrides: object) -> ChatResponse:
    values: dict[str, object] = {
        "text": _plan_text() if text is None else text,
        "model_profile": MODEL_PROFILE,
        "resolved_model": "gpt-test-pinned-v1",
        "gateway_dispatch_id": DISPATCH_ID,
    }
    values.update(overrides)
    return ChatResponse.model_validate(values)


def test_narrative_limits_are_default_closed_and_require_all_positive_controls() -> None:
    assert not NarrativeLimits().permits_dispatch()
    assert not NarrativeLimits(enabled=True, kill_switch=True, daily_limit=1, monthly_limit=1, concurrency=1).permits_dispatch()
    assert NarrativeLimits(enabled=True, kill_switch=False, daily_limit=1, monthly_limit=1, concurrency=1).permits_dispatch()
    with pytest.raises(ValueError, match="non-negative"):
        NarrativeLimits(daily_limit=-1)


@pytest.mark.asyncio
async def test_saved_v2_snapshot_builds_complete_immutable_generation_identity() -> None:
    report = await _validated_report()

    assert report.eligible_for_ai
    assert report.activity_label == "Разработка компьютерного программного обеспечения"
    assert report.identity.snapshot_schema_version == "company_card_v2_snapshot_v2"
    assert report.identity.narrative_evidence_schema_version == "company_card_v2_narrative_evidence_v1"
    assert report.identity.primary_activity_parser_version == "company_card_v2_primary_activity_parser_v1"
    assert report.identity.primary_activity_evidence_version == "company_card_v2_okved_primary_activity_evidence_v1"
    assert report.generation_key
    assert report.record.normalized_snapshot == company_card_v2_to_snapshot(
        company_card_v2_from_snapshot(_raw_snapshot())
    )


def _unresolved_policy_pin(card, subject, record, policy: str):
    return SimpleNamespace(
        subject_id=subject.id,
        report_id=record.id,
        presentation_contract="company_public_h2_v1",
        generation=1,
        snapshot_hash=record.snapshot_hash,
        chart_facts_version=card.chart_facts.version,
        chart_facts_hash=card.chart_facts.hash,
        evidence_registry_version=card.evidence_version,
        publication_policy_version=policy,
        canonical_path=None,
        indexable=False,
        published_lastmod=None,
        projection_digest=None,
        narrative_binding_status="unresolved",
        narrative_binding_kind=None,
        narrative_binding_key=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy",
    (
        "company_public_h2_publication_v1",
        "company_public_h2_publication_v2",
    ),
)
async def test_narrative_uses_the_one_exact_saved_publication_policy(policy: str) -> None:
    card, subject, record = _record_context()
    pin = _unresolved_policy_pin(card, subject, record, policy)

    validated = await validate_narrative_report(
        _PolicySubjectSession(subject, [pin]),
        record=record,
    )

    assert validated.publication_policy_version == policy
    fallback = PublicH2Narrative(
        mode="deterministic_fallback",
        renderer_version=FALLBACK_RENDERER_VERSION,
        description=FALLBACK_DESCRIPTION,
        statement_ids=(FALLBACK_PROFILE_ID,),
        comments=(),
        render_digest=sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest(),
    )
    finance_enabled = policy == "company_public_h2_publication_v2"
    expected = build_public_h2(
        card,
        narrative_binding=SimpleNamespace(narrative=fallback),
        finance_enabled=finance_enabled,
    ).projection_digest
    opposite = build_public_h2(
        card,
        narrative_binding=SimpleNamespace(narrative=fallback),
        finance_enabled=not finance_enabled,
    ).projection_digest
    assert fallback_projection_digest(validated) == expected
    assert expected != opposite


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("corruption", "message"),
    (
        ("missing", "missing or ambiguous"),
        ("ambiguous", "missing or ambiguous"),
        ("snapshot", "predecessor identity"),
        ("chart_version", "predecessor identity"),
        ("evidence", "predecessor identity"),
        ("canonical_path", "predecessor identity"),
        ("binding_status", "predecessor identity"),
        ("unknown_policy", "publication policy"),
    ),
)
async def test_narrative_rejects_missing_ambiguous_or_corrupt_policy_lineage(
    corruption: str,
    message: str,
) -> None:
    card, subject, record = _record_context()
    pin = _unresolved_policy_pin(
        card,
        subject,
        record,
        "company_public_h2_publication_v2",
    )
    pins = [pin]
    if corruption == "missing":
        pins = []
    elif corruption == "ambiguous":
        pins = [pin, deepcopy(pin)]
    elif corruption == "snapshot":
        pin.snapshot_hash = "f" * 64
    elif corruption == "chart_version":
        pin.chart_facts_version = "stale"
    elif corruption == "evidence":
        pin.evidence_registry_version = "stale"
    elif corruption == "canonical_path":
        pin.canonical_path = "/company/should-not-exist"
    elif corruption == "binding_status":
        pin.narrative_binding_status = "resolved"
    elif corruption == "unknown_policy":
        pin.publication_policy_version = "company_public_h2_publication_unknown"

    with pytest.raises(NarrativePersistenceError, match=message):
        await validate_narrative_report(
            _PolicySubjectSession(subject, pins),
            record=record,
        )


@pytest.mark.asyncio
async def test_valid_gateway_artifact_is_canonical_grounded_and_has_complete_scalar_trace() -> None:
    artifact = validate_gateway_artifact(await _prepared(), _response())
    draft = artifact.draft

    assert draft.validated_render_plan_cjson == _plan_text().encode("utf-8")
    assert draft.raw_model_output == _plan_text()
    assert draft.statement_ids == (
        "statement_snapshot_scope_v1",
        "statement_primary_activity_v1",
        "statement_missing_is_unknown_v1",
        "statement_neutrality_and_immutability_v1",
    )
    assert draft.evidence_ids == (
        "evidence_snapshot_identity_v1",
        "evidence_primary_activity_v1",
        "evidence_missing_semantics_policy_v1",
        "evidence_neutrality_policy_v1",
    )
    previous_end = -1
    for index, item in enumerate(draft.phrase_trace):
        assert item["scalar_start"] == (0 if index == 0 else previous_end + 1)
        assert draft.rendered_description[item["scalar_start"]:item["scalar_end"]]
        previous_end = item["scalar_end"]
    assert previous_end == len(draft.rendered_description)
    assert len(artifact.projection_digest) == 64


@pytest.mark.asyncio
async def test_duplicate_json_keys_are_rejected_before_model_validation() -> None:
    prepared = await _prepared()
    with pytest.raises(NarrativeValidationError, match="duplicate JSON object key"):
        validate_gateway_artifact(prepared, _response('{"x":1,"x":2}'))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"gateway_dispatch_id": UUID("123e4567-e89b-12d3-a456-426614174001")},
        {"model_profile": "other_profile_v1"},
        {"resolved_model": ""},
        {"resolved_model": "x" * 256},
    ],
)
async def test_gateway_identity_mismatch_is_terminal(overrides: dict[str, object]) -> None:
    with pytest.raises(NarrativeValidationError, match="gateway narrative identity is invalid"):
        validate_gateway_artifact(await _prepared(), _response(**overrides))


@pytest.mark.asyncio
async def test_gateway_response_exact_utf8_byte_cap() -> None:
    prepared = await _prepared()
    raw = _plan_text()
    exact = raw + " " * (16384 - len(raw.encode("utf-8")))
    assert len(exact.encode("utf-8")) == 16384
    validate_gateway_artifact(prepared, _response(exact))

    with pytest.raises(NarrativeValidationError, match="gateway narrative identity is invalid"):
        validate_gateway_artifact(prepared, _response(exact + " "))
