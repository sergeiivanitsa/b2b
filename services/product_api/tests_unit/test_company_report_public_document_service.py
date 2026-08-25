from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from product_api.company_reports import public_document_service as service
from product_api.company_reports.company_card_v2 import service as h2_service
from product_api.company_reports.persistence.public_documents import PublicDocumentAssignmentRow


def _row(contract: str, *, report_subject: str = "subject") -> PublicDocumentAssignmentRow:
    subject = SimpleNamespace(id="subject", normalized_identifier="7701234567")
    assignment = SimpleNamespace(subject_id="subject", presentation_contract=contract, pin_generation=3)
    pin = SimpleNamespace(subject_id="subject", presentation_contract=contract, generation=3, report_id="report")
    report = SimpleNamespace(id="report", subject_id=report_subject)
    return PublicDocumentAssignmentRow(subject, assignment, pin, report)


@pytest.mark.asyncio
@pytest.mark.parametrize("contract", ["company_public_h1_v1", "company_public_h2_v1"])
async def test_assigned_corruption_never_uses_legacy_fallback(monkeypatch: pytest.MonkeyPatch, contract: str) -> None:
    async def select(*_args, **_kwargs): return _row(contract, report_subject="wrong")
    async def legacy(*_args, **_kwargs): raise AssertionError("legacy fallback must not run")
    monkeypatch.setattr(service, "get_public_document_assignment_row", select)
    monkeypatch.setattr(service, "resolve_public_h1", legacy)
    if contract == "company_public_h1_v1":
        def invalid(*_args, **_kwargs):
            raise service.PublicH1Error("invalid")
        monkeypatch.setattr(service, "validate_assigned_public_h1", invalid)
    with pytest.raises(service.PublicDocumentInvalid):
        await service.resolve_public_document(object(), inn="7701234567")


@pytest.mark.asyncio
async def test_exact_h2_storage_failure_is_not_reclassified_as_binding_corruption(monkeypatch: pytest.MonkeyPatch) -> None:
    async def select(*_args, **_kwargs):
        return _row("company_public_h2_v1")
    async def unavailable(*_args, **_kwargs):
        raise OperationalError("select", {}, RuntimeError("database unavailable"))
    monkeypatch.setattr(service, "get_public_document_assignment_row", select)
    monkeypatch.setattr(service, "resolve_exact_assigned_public_h2", unavailable)
    with pytest.raises(OperationalError):
        await service.resolve_public_document(object(), inn="7701234567")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lifecycle_status", "error_type", "code"),
    (
        ("pending", h2_service.PublicH2Pending, "report_pending"),
        ("failed", h2_service.PublicH2Failed, "report_failed"),
    ),
)
async def test_exact_h2_preserves_nonready_lifecycle_class(
    lifecycle_status: str, error_type: type[Exception], code: str,
) -> None:
    record = SimpleNamespace(lifecycle_status=lifecycle_status)
    with pytest.raises(error_type) as caught:
        await h2_service._resolve_exact_v3(
            object(), record, pin=object(), expected_subject_id="subject", expected_inn="7701234567"
        )
    assert getattr(caught.value, "code") == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    (
        service.PublicH2Pending("pending"),
        service.PublicH2Failed("failed"),
        service.PublicH2NotEligible("not eligible"),
    ),
)
async def test_public_document_service_preserves_exact_h2_nonready_class(
    monkeypatch: pytest.MonkeyPatch, error: Exception,
) -> None:
    async def select(*_args, **_kwargs):
        return _row("company_public_h2_v1")

    async def nonready(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(service, "get_public_document_assignment_row", select)
    monkeypatch.setattr(service, "resolve_exact_assigned_public_h2", nonready)
    with pytest.raises(type(error)) as caught:
        await service.resolve_public_document(object(), inn="7701234567")
    assert caught.value is error
