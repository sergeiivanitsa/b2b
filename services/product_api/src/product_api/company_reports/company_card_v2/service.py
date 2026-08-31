from __future__ import annotations

from copy import deepcopy
import hashlib

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from product_api.company_reports.persistence.models import CompanyReportPresentationAssignment, CompanyReportPresentationPin, CompanyReportPresentationStagedPointer, CompanyReportRecord, CompanyReportSubject
from product_api.company_reports.persistence.v3 import calculate_company_card_v2_snapshot_hash, company_card_v2_from_snapshot
from product_api.company_reports.persistence.serialization import calculate_company_report_snapshot_hash, company_report_from_snapshot
from product_api.company_reports.company_card_v2.canonical_json import canonical_digest
from .public_h2 import build_public_h2
from .public_h2_models import (
    BLOCK_ORDER, COVERAGE_BLOCKS, CompanyPublicH2Response, PublicH2Action,
    PublicH2Blocks, PublicH2Breadcrumb, PublicH2ClaimCta, PublicH2CoverageItem,
    PublicH2Identity, PublicH2Limitation, PublicH2Narrative, PublicH2Requisites,
    PublicH2SourceItem,
)


class PublicH2Error(RuntimeError):
    code = "company_public_h2_unavailable"


class PublicH2NotFound(PublicH2Error):
    code = "company_public_h2_not_found"


class PublicH2Invalid(PublicH2Error):
    code = "company_public_h2_invalid"


class PublicH2NotEligible(PublicH2Error):
    code = "report_not_eligible"


def h2_cohort_selected(*, inn: str, settings: object) -> bool:
    """Return the immutable server-side H2 cohort decision.

    No request-controlled input is accepted here.  Bad/missing configuration
    is deliberately a no-H2 decision rather than a permissive fallback.
    """
    try:
        if not getattr(settings, "company_card_v2_presentations_enabled"):
            return False
        generation = getattr(settings, "company_card_v2_rollout_generation")
        allowlist = getattr(settings, "company_card_v2_allowlist_inns")
        percentage = getattr(settings, "company_card_v2_percentage_basis_points")
        if not isinstance(generation, int) or generation <= 0 or not isinstance(percentage, int) or not 0 <= percentage <= 10000:
            return False
        if not isinstance(allowlist, list) or not inn.isascii() or not inn.isdigit() or len(inn) not in {10, 12}:
            return False
        if inn in allowlist:
            return True
        bucket = int.from_bytes(hashlib.sha256(("company-card-v2-cohort-v1\0" + inn).encode("utf-8")).digest()[:8], "big") % 10000
        return bucket < percentage
    except (AttributeError, TypeError, ValueError):
        return False


async def resolve_public_h2(session: AsyncSession, *, inn: str) -> CompanyPublicH2Response:
    subject = await session.scalar(select(CompanyReportSubject).where(CompanyReportSubject.normalized_identifier == inn))
    if subject is None:
        raise PublicH2NotFound("company card v2 was not found")
    for pointer_model in (CompanyReportPresentationAssignment, CompanyReportPresentationStagedPointer):
        pointer = await session.scalar(select(pointer_model).where(pointer_model.subject_id == subject.id))
        if pointer is not None:
            pin = await session.get(CompanyReportPresentationPin, pointer.pin_id)
            if pin is None or pin.subject_id != subject.id or pin.presentation_contract != "company_public_h2_v1":
                raise PublicH2Invalid("company card v2 binding is invalid")
            record = await session.get(CompanyReportRecord, pin.report_id)
            return _resolve_exact_v3(record, expected_hash=pin.snapshot_hash)
    rows = (await session.execute(select(CompanyReportRecord).join(CompanyReportSubject, CompanyReportSubject.id == CompanyReportRecord.subject_id).where(
        CompanyReportSubject.normalized_identifier == inn,
        CompanyReportRecord.writer_profile == "h1_legacy_writer_v2",
        CompanyReportRecord.presentation_contract == "company_public_h1_v1",
        CompanyReportRecord.report_version.in_(("1", "2")),
        CompanyReportRecord.lifecycle_status.in_(("complete", "partial")),
        CompanyReportRecord.normalized_snapshot.is_not(None),
    ).order_by(desc(CompanyReportRecord.generated_at), desc(CompanyReportRecord.id)))).scalars().all()
    if not rows:
        raise PublicH2NotEligible("company card v2 has no eligible binding")
    for record in rows:
        try:
            return _legacy_preview(record, inn)
        except PublicH2Invalid:
            continue
    raise PublicH2Invalid("legacy company report is invalid")


def _resolve_exact_v3(record: CompanyReportRecord | None, *, expected_hash: str) -> CompanyPublicH2Response:
    if record is None:
        raise PublicH2Invalid("company card v2 binding is invalid")
    try:
        snapshot = company_card_v2_from_snapshot(deepcopy(record.normalized_snapshot))
        if record.snapshot_hash != expected_hash or record.snapshot_hash != calculate_company_card_v2_snapshot_hash(snapshot) or snapshot.report_id != str(record.id):
            raise PublicH2Invalid("company card v2 is invalid")
        return build_public_h2(snapshot)
    except PublicH2Error:
        raise
    except Exception as exc:
        raise PublicH2Invalid("company card v2 is invalid") from exc


def _legacy_preview(record: CompanyReportRecord, inn: str) -> CompanyPublicH2Response:
    try:
        snapshot = deepcopy(record.normalized_snapshot)
        if not isinstance(snapshot, dict) or not record.snapshot_hash or calculate_company_report_snapshot_hash(snapshot) != record.snapshot_hash:
            raise PublicH2Invalid("legacy company report is invalid")
        report = company_report_from_snapshot(snapshot)
        counterparty = report.counterparty
        if counterparty is None or report.report_id != record.id or report.target_identifier != inn or counterparty.inn != inn:
            raise PublicH2Invalid("legacy company report is invalid")
        checked_at = report.generated_at.astimezone(__import__("datetime").timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        name = counterparty.full_name or counterparty.short_name or inn
        path = f"/company/{inn}-company"
        limitation = PublicH2Limitation(code="legacy_unavailable", block_id="sources_limitations", field_id=None, message="Данные новой карточки недоступны для сохранённого legacy-отчёта.")
        narrative_text = (f"Карточка организации {name} (ИНН {inn}) построена как совместимый предварительный просмотр сохранённого отчёта. "
                          "Новые финансовые и арбитражные факты в этом режиме не публикуются: их источники, единицы измерения, полнота и приватностные границы не подтверждены для H2. "
                          "Отсутствие значения не означает ноль, отсутствие судебных дел или положительный вывод. Используйте исходные документы и сведения конкретного обязательства перед подготовкой претензии. "
                          "Дата проверки соответствует времени формирования сохранённого отчёта.")
        narrative = PublicH2Narrative(mode="deterministic_fallback", renderer_version="company_card_v2_fallback_v1", description=narrative_text, statement_ids=("legacy_preview",), render_digest=canonical_digest({"description": narrative_text, "statement_ids": ["legacy_preview"]}))
        coverage = [PublicH2CoverageItem(block_id=item, state="partial" if item in {"requisites", "narrative", "sources_limitations"} else "not_requested", population_scope="not_applicable", limitation_codes=("legacy_unavailable",) if item not in {"requisites", "narrative", "sources_limitations"} else ()) for item in COVERAGE_BLOCKS]
        payload = {"contract_version": "company_public_h2_v1", "report_version": report.report_version, "snapshot_capability": "legacy_read_only", "projection_scope": "latest_unpublished", "report_id": str(record.id), "canonical_path": path, "indexable": False, "checked_at": checked_at, "checked_date": report.generated_at.date().isoformat(), "checked_date_display": report.generated_at.date().isoformat(), "identity": PublicH2Identity(display_name=name, legal_full_name=name, short_name=counterparty.short_name, inn=inn, ogrn=counterparty.ogrn, kpp=counterparty.kpp, registration_date=counterparty.registration_date.isoformat() if counterparty.registration_date else None, dissolution_date=counterparty.dissolved_date.isoformat() if counterparty.dissolved_date else None).model_dump(mode="json"), "narrative": narrative.model_dump(mode="json"), "block_order": BLOCK_ORDER, "blocks": PublicH2Blocks(requisites=PublicH2Requisites(address=counterparty.address.line_address if counterparty.address else None, address_inaccuracy=counterparty.address.is_inaccuracy if counterparty.address else None)).model_dump(mode="json"), "coverage": [item.model_dump(mode="json") for item in coverage], "sources": [PublicH2SourceItem(dataset=dataset, received_at=checked_at, normalization_version="legacy_h1", evidence_version="legacy").model_dump(mode="json") for dataset in ("counterparty", "finance", "arbitration")], "limitations": [limitation.model_dump(mode="json")], "actions": [PublicH2Action(action_id="check_another_company", label="Проверить другую компанию", path="/company").model_dump(mode="json"), PublicH2Action(action_id="prepare_claim", label="Подготовить претензию", path=f"/claims?report_id={record.id}").model_dump(mode="json")], "breadcrumbs": [PublicH2Breadcrumb(label="Компании", path="/company", current=False).model_dump(mode="json"), PublicH2Breadcrumb(label=name, path=path, current=True).model_dump(mode="json")], "primary_claim_cta": PublicH2ClaimCta(path=f"/claims?report_id={record.id}").model_dump(mode="json")}
        return CompanyPublicH2Response(**payload, projection_digest=canonical_digest(payload))
    except PublicH2Error:
        raise
    except Exception as exc:
        raise PublicH2Invalid("legacy company report is invalid") from exc


__all__ = ["PublicH2Error", "PublicH2Invalid", "PublicH2NotEligible", "PublicH2NotFound", "h2_cohort_selected", "resolve_public_h2"]
