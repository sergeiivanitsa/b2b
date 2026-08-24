from copy import deepcopy
from types import SimpleNamespace

import pytest

from company_report_signal_test_helpers import complete_company_report, counterparty_facts
from product_api.company_reports.persistence.models import PUBLICATION_POLICY_VERSION
from product_api.company_reports.persistence.serialization import calculate_company_report_snapshot_hash, company_report_to_snapshot
from product_api.company_reports.public_h1_service import (
    PublicH1InvalidInnError,
    PublicH1NotFoundError,
    PublicProjectionInvalidError,
    _inn,
    resolve_public_h1,
    validate_active_publication,
)
from product_api.company_reports.seo import canonical_path


def _pin():
    report = complete_company_report(counterparty=counterparty_facts().model_copy(update={"inn": "0000000000", "full_name": "ООО Тест"}), report_version="2")
    snapshot = company_report_to_snapshot(report)
    digest = calculate_company_report_snapshot_hash(snapshot)
    subject = SimpleNamespace(id="subject", normalized_identifier="0000000000")
    record = SimpleNamespace(id=report.report_id, subject_id=subject.id, report_version="2", lifecycle_status="complete", normalized_snapshot=snapshot, snapshot_hash=digest, generated_at=report.generated_at)
    path = canonical_path("0000000000", "ООО Тест")
    publication = SimpleNamespace(status="active", subject_id=subject.id, report_id=record.id, policy_version=PUBLICATION_POLICY_VERSION, sufficiency_status="sufficient", indexable=True, snapshot_hash=digest, canonical_path=path, canonical_slug=path.rsplit("-", 1)[-1] if False else path[len("/company/0000000000-"):], published_lastmod=report.generated_at)
    return SimpleNamespace(publication=publication, subject=subject, report=record)


def test_resolver_rejects_non_inn_without_database_access():
    with pytest.raises(PublicH1InvalidInnError):
        _inn("invalid")


def test_complete_active_pin_validator_accepts_only_full_matrix():
    dto = validate_active_publication(_pin())
    assert dto.projection_scope == "published"
    assert dto.indexable is True


@pytest.mark.parametrize(
    ("surface", "value"),
    [
        ("publication.subject_id", "other"), ("publication.report_id", "other"),
        ("publication.policy_version", "unknown"), ("publication.sufficiency_status", "thin_content"),
        ("publication.snapshot_hash", "0" * 64), ("publication.canonical_path", "/company/0000000000-wrong"),
        ("publication.canonical_slug", "wrong"), ("publication.published_lastmod", None),
        ("report.subject_id", "other"), ("report.report_version", "1"),
        ("report.lifecycle_status", "failed"), ("report.snapshot_hash", "0" * 64),
        ("subject.normalized_identifier", "1111111111"),
    ],
)
def test_active_pin_matrix_fails_closed(surface, value):
    pin = _pin()
    owner, field = surface.split(".")
    setattr(getattr(pin, owner), field, value)
    with pytest.raises(PublicProjectionInvalidError):
        validate_active_publication(pin)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("report_id",), "00000000-0000-0000-0000-000000000099"),
        (("report_version",), "1"),
        (("status",), "partial"),
        (("generated_at",), "2025-01-01T00:00:00Z"),
        (("target_identifier",), "1111111111"),
        (("counterparty", "inn"), "1111111111"),
    ],
)
def test_active_pin_rejects_semantically_mismatched_but_rehashed_snapshot(path, value):
    pin = _pin()
    node = pin.report.normalized_snapshot
    for segment in path[:-1]:
        node = node[segment]
    node[path[-1]] = value
    digest = calculate_company_report_snapshot_hash(pin.report.normalized_snapshot)
    pin.report.snapshot_hash = digest
    pin.publication.snapshot_hash = digest

    with pytest.raises(PublicProjectionInvalidError):
        validate_active_publication(pin)


@pytest.mark.asyncio
async def test_corrupt_active_pin_never_falls_back_to_history(monkeypatch):
    pin = _pin()
    pin.report = None
    calls = {"history": 0}

    async def publication(*_args):
        return pin

    async def history(*_args):
        calls["history"] += 1
        return []

    monkeypatch.setattr("product_api.company_reports.public_h1_service.get_publication_resolution_record", publication)
    monkeypatch.setattr("product_api.company_reports.public_h1_service.list_report_resolution_records", history)
    with pytest.raises(PublicProjectionInvalidError):
        await resolve_public_h1(object(), inn="0000000000")
    assert calls["history"] == 0


@pytest.mark.asyncio
async def test_public_h1_missing_exact_publication_report_is_terminal(monkeypatch):
    pin = _pin()
    pin.report = None
    history_calls = 0

    async def publication(*_args): return pin
    async def history(*_args):
        nonlocal history_calls
        history_calls += 1
        return []

    monkeypatch.setattr("product_api.company_reports.public_h1_service.get_publication_resolution_record", publication)
    monkeypatch.setattr("product_api.company_reports.public_h1_service.list_report_resolution_records", history)
    with pytest.raises(PublicProjectionInvalidError):
        await resolve_public_h1(object(), inn="0000000000")
    assert history_calls == 0


@pytest.mark.asyncio
async def test_public_h1_corrupt_exact_publication_report_is_terminal(monkeypatch):
    pin = _pin()
    pin.report.snapshot_hash = "0" * 64
    history_calls = 0

    async def publication(*_args): return pin
    async def history(*_args):
        nonlocal history_calls
        history_calls += 1
        return []

    monkeypatch.setattr("product_api.company_reports.public_h1_service.get_publication_resolution_record", publication)
    monkeypatch.setattr("product_api.company_reports.public_h1_service.list_report_resolution_records", history)
    with pytest.raises(PublicProjectionInvalidError):
        await resolve_public_h1(object(), inn="0000000000")
    assert history_calls == 0


@pytest.mark.asyncio
async def test_active_h1_read_never_invokes_policy_or_ephemeral_evaluators(monkeypatch):
    pin = _pin()

    async def publication(*_args):
        return pin

    async def forbidden_history(*_args):
        raise AssertionError("active pin must not scan history")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("read path must not evaluate policy, signals or scoring")

    monkeypatch.setattr("product_api.company_reports.public_h1_service.get_publication_resolution_record", publication)
    monkeypatch.setattr("product_api.company_reports.public_h1_service.list_report_resolution_records", forbidden_history)
    monkeypatch.setattr("product_api.company_reports.seo.evaluate_publication", forbidden)
    monkeypatch.setattr("product_api.company_reports.ephemeral_evaluation.evaluate_report_ephemerally", forbidden)
    dto = await resolve_public_h1(object(), inn="0000000000")
    assert dto.indexable is True


@pytest.mark.asyncio
async def test_no_publication_uses_two_phases_and_skips_newer_corrupt_candidate(monkeypatch):
    valid = _pin()
    corrupt = deepcopy(valid.report)
    corrupt.snapshot_hash = "0" * 64
    calls = {"publication": 0, "history": 0}

    async def publication(*_args):
        calls["publication"] += 1
        return None

    async def history(*_args):
        calls["history"] += 1
        return [SimpleNamespace(report=corrupt, subject=valid.subject), SimpleNamespace(report=valid.report, subject=valid.subject)]

    monkeypatch.setattr("product_api.company_reports.public_h1_service.get_publication_resolution_record", publication)
    monkeypatch.setattr("product_api.company_reports.public_h1_service.list_report_resolution_records", history)
    dto = await resolve_public_h1(object(), inn="0000000000")
    assert dto.projection_scope == "latest_unpublished" and dto.indexable is False
    assert calls == {"publication": 1, "history": 1}


@pytest.mark.asyncio
async def test_no_rows_is_exact_not_found(monkeypatch):
    async def none(*_args):
        return None

    async def empty(*_args):
        return []

    monkeypatch.setattr("product_api.company_reports.public_h1_service.get_publication_resolution_record", none)
    monkeypatch.setattr("product_api.company_reports.public_h1_service.list_report_resolution_records", empty)
    with pytest.raises(PublicH1NotFoundError):
        await resolve_public_h1(object(), inn="0000000000")
