from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo

from .canonical_json import canonical_digest, canonical_json_bytes
from .models import CompanyCardV2Snapshot
from .privacy import assert_public_boundary_safe
from .public_h2_models import (
    BLOCK_ORDER, COVERAGE_BLOCKS, CompanyPublicH2Response, PublicH2Action,
    PublicH2Blocks, PublicH2Breadcrumb, PublicH2ClaimCta, PublicH2CoverageItem,
    PublicH2Identity, PublicH2Limitation, PublicH2Narrative, PublicH2Requisites,
    PublicH2SourceItem,
)

_MOSCOW = ZoneInfo("Europe/Moscow")


def _utc_z(value) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fallback_description(name: str, inn: str) -> str:
    # This is an explicitly deterministic fallback, not an AI generation.  It
    # intentionally contains only validated public identity values and states
    # that gated evidence has not been turned into facts.
    text = (
        f"Карточка организации {name} (ИНН {inn}) сформирована по сохранённому отчёту. "
        "В ней показаны только подтверждённые реквизиты и статус доступности разделов. "
        "Финансовые значения и показатели арбитража в этой версии не публикуются, если их "
        "источник, единица измерения, полнота выборки или границы приватности не подтверждены. "
        "Отсутствие показателя не означает нулевое значение, отсутствие судебных дел или иной "
        "положительный вывод. Для решения о дальнейших действиях используйте исходные документы "
        "и при необходимости подготовьте претензию по реквизитам конкретного обязательства."
    )
    # The normalized public name can be short; append a closed explanatory
    # sentence to meet the contract's deterministic 400-character floor.
    return text if len(text) >= 400 else text + " Дата проверки относится к моменту формирования сохранённого отчёта."


def build_public_h2(snapshot: CompanyCardV2Snapshot) -> CompanyPublicH2Response:
    checked_at = _utc_z(snapshot.generated_at)
    checked_date = snapshot.generated_at.astimezone(_MOSCOW).date().isoformat()
    name = snapshot.counterparty.full_name or snapshot.counterparty.short_name or snapshot.subject_inn
    canonical_path = f"/company/{snapshot.subject_inn}-company"
    limitations = [
        PublicH2Limitation(code=item.code, field_id=item.field, message="Данные недоступны в текущем подтверждённом контуре.")
        for item in (*snapshot.limitations, *snapshot.arbitration_basis.limitations)
    ]
    # Every unavailable leaf has an explicit linked limitation.  Do not reuse
    # private/provider text as a message.
    for block in (*COVERAGE_BLOCKS[2:7], *COVERAGE_BLOCKS[7:12]):
        code = f"{block}_gate_closed"
        limitations.append(PublicH2Limitation(code=code, block_id=block, field_id=None, message="Раздел недоступен до закрытия обязательного evidence gate."))
    # Deduplicate deterministically without accepting conflicting text.
    unique: dict[str, PublicH2Limitation] = {}
    for limitation in limitations:
        unique.setdefault(limitation.code, limitation)
    limitations = sorted(unique.values(), key=lambda item: (COVERAGE_BLOCKS.index(item.block_id) if item.block_id in COVERAGE_BLOCKS else 99, item.field_id or "", item.code))
    narrative_text = _fallback_description(name, snapshot.subject_inn)
    narrative = PublicH2Narrative(
        mode="deterministic_fallback", renderer_version="company_card_v2_fallback_v1",
        description=narrative_text, statement_ids=("identity_saved_report", "gates_closed"),
        render_digest=canonical_digest({"description": narrative_text, "statement_ids": ["identity_saved_report", "gates_closed"]}),
    )
    coverage = []
    for block in COVERAGE_BLOCKS:
        if block == "requisites":
            coverage.append(PublicH2CoverageItem(block_id=block, state="partial", population_scope="not_applicable", limitation_codes=()))
        elif block == "narrative":
            coverage.append(PublicH2CoverageItem(block_id=block, state="available", population_scope="not_applicable", limitation_codes=()))
        elif block == "sources_limitations":
            coverage.append(PublicH2CoverageItem(block_id=block, state="available", population_scope="not_applicable", limitation_codes=()))
        else:
            coverage.append(PublicH2CoverageItem(block_id=block, state="not_requested", population_scope="not_applicable", limitation_codes=(f"{block}_gate_closed",)))
    payload = {
        "contract_version": "company_public_h2_v1", "report_id": snapshot.report_id, "report_version": "3",
        "snapshot_capability": "card_v2", "projection_scope": "latest_unpublished", "canonical_path": canonical_path,
        "indexable": False, "checked_at": checked_at, "checked_date": checked_date, "checked_date_display": checked_date,
        "identity": PublicH2Identity(display_name=name, legal_full_name=name, short_name=snapshot.counterparty.short_name,
            inn=snapshot.counterparty.inn, ogrn=snapshot.counterparty.ogrn, kpp=snapshot.counterparty.kpp,
            registration_date=snapshot.counterparty.registration_date.isoformat() if snapshot.counterparty.registration_date else None,
            dissolution_date=snapshot.counterparty.dissolution_date.isoformat() if snapshot.counterparty.dissolution_date else None).model_dump(mode="json"),
        "narrative": narrative.model_dump(mode="json"), "block_order": BLOCK_ORDER,
        "blocks": PublicH2Blocks(requisites=PublicH2Requisites(address=snapshot.counterparty.address, address_inaccuracy=snapshot.counterparty.address_inaccuracy)).model_dump(mode="json"),
        "coverage": [item.model_dump(mode="json") for item in coverage],
        "sources": [PublicH2SourceItem(dataset=dataset, received_at=checked_at, normalization_version="company_card_v2_v1", evidence_version=snapshot.evidence_version).model_dump(mode="json") for dataset in ("counterparty", "finance", "arbitration")],
        "limitations": [item.model_dump(mode="json") for item in limitations],
        "actions": [PublicH2Action(action_id="check_another_company", label="Проверить другую компанию", path="/company").model_dump(mode="json"), PublicH2Action(action_id="prepare_claim", label="Подготовить претензию", path=f"/claims?report_id={snapshot.report_id}").model_dump(mode="json")],
        "breadcrumbs": [PublicH2Breadcrumb(label="Компании", path="/company", current=False).model_dump(mode="json"), PublicH2Breadcrumb(label=name, path=canonical_path, current=True).model_dump(mode="json")],
        "primary_claim_cta": PublicH2ClaimCta(path=f"/claims?report_id={snapshot.report_id}").model_dump(mode="json"),
    }
    response = CompanyPublicH2Response(**payload, projection_digest=canonical_digest(payload))
    if len(canonical_json_bytes(response.model_dump(mode="json"))) > 524288:
        raise ValueError("public_projection_too_large")
    assert_public_boundary_safe(response.model_dump(mode="json"))
    return response


__all__ = ["build_public_h2"]
