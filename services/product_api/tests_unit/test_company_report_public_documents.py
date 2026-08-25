"""Canonical assignment selection has no active/latest fallback once assigned."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from product_api.company_reports.persistence.public_documents import PublicDocumentAssignmentRow
from product_api.company_reports import public_document_service as service


def _row(contract: str | None, *, complete: bool = True) -> PublicDocumentAssignmentRow:
    subject = SimpleNamespace(id="subject", normalized_identifier="7701234567")
    assignment = None if contract is None else SimpleNamespace(subject_id="subject", presentation_contract=contract, pin_generation=7)
    pin = None if not complete else SimpleNamespace(subject_id="subject", presentation_contract=contract, generation=7, report_id="report")
    report = None if not complete else SimpleNamespace(id="report", subject_id="subject")
    return PublicDocumentAssignmentRow(subject, assignment, pin, report)


@pytest.mark.asyncio
async def test_unassigned_row_is_the_only_case_that_uses_legacy_h1(monkeypatch: pytest.MonkeyPatch) -> None:
    async def select(*_args, **_kwargs): return _row(None)
    async def legacy(*_args, **_kwargs): return "legacy"
    monkeypatch.setattr(service, "get_public_document_assignment_row", select)
    monkeypatch.setattr(service, "resolve_public_h1", legacy)
    resolved = await service.resolve_public_document(object(), inn="7701234567")
    assert resolved.dto == "legacy" and resolved.assigned is False


@pytest.mark.asyncio
async def test_assigned_h1_never_calls_active_or_latest_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    async def select(*_args, **_kwargs): return _row("company_public_h1_v1")
    def exact(*_args, **_kwargs): return "pinned-h1"
    async def forbidden(*_args, **_kwargs): raise AssertionError("legacy fallback is forbidden")
    monkeypatch.setattr(service, "get_public_document_assignment_row", select)
    monkeypatch.setattr(service, "validate_assigned_public_h1", exact)
    monkeypatch.setattr(service, "resolve_public_h1", forbidden)
    resolved = await service.resolve_public_document(object(), inn="7701234567")
    assert resolved.dto == "pinned-h1" and resolved.assigned is True


@pytest.mark.asyncio
async def test_exact_injected_h2_assignment_uses_only_captured_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _row("company_public_h2_v1")
    seen = []
    async def select(*_args, **_kwargs): return captured
    async def exact(_session, *, subject, assignment, pin, report):
        seen.append((subject, assignment, pin, report)); return "pinned-h2"
    async def forbidden(*_args, **_kwargs): raise AssertionError("H1 fallback is forbidden")
    monkeypatch.setattr(service, "get_public_document_assignment_row", select)
    monkeypatch.setattr(service, "resolve_exact_assigned_public_h2", exact)
    monkeypatch.setattr(service, "resolve_public_h1", forbidden)
    resolved = await service.resolve_public_document(object(), inn="7701234567")
    assert resolved.dto == "pinned-h2" and resolved.assigned is True
    assert seen == [(captured.subject, captured.assignment, captured.pin, captured.report)]


@pytest.mark.asyncio
async def test_exact_assigned_old_digest_h2_fails_closed_without_h1(monkeypatch: pytest.MonkeyPatch) -> None:
    async def select(*_args, **_kwargs): return _row("company_public_h2_v1")
    async def stale(*_args, **_kwargs): raise ValueError("projection digest mismatch")
    async def forbidden(*_args, **_kwargs): raise AssertionError("H1 fallback is forbidden")
    monkeypatch.setattr(service, "get_public_document_assignment_row", select)
    monkeypatch.setattr(service, "resolve_exact_assigned_public_h2", stale)
    monkeypatch.setattr(service, "resolve_public_h1", forbidden)
    with pytest.raises(service.PublicDocumentInvalid):
        await service.resolve_public_document(object(), inn="7701234567")


@pytest.mark.asyncio
@pytest.mark.parametrize("contract", ["company_public_h1_v1", "company_public_h2_v1", "unknown"])
async def test_assigned_but_incomplete_or_unknown_row_fails_closed(monkeypatch: pytest.MonkeyPatch, contract: str) -> None:
    async def select(*_args, **_kwargs): return _row(contract, complete=False)
    async def forbidden(*_args, **_kwargs): raise AssertionError("fallback is forbidden")
    monkeypatch.setattr(service, "get_public_document_assignment_row", select)
    monkeypatch.setattr(service, "resolve_public_h1", forbidden)
    with pytest.raises(service.PublicDocumentInvalid):
        await service.resolve_public_document(object(), inn="7701234567")
