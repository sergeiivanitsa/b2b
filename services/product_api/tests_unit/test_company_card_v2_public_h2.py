from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

import pytest

from product_api.company_reports.company_card_v2.canonical_json import canonical_digest
from product_api.company_reports.company_card_v2.finance import build_chart_facts, build_finance_views
from product_api.company_reports.company_card_v2.models import (
    ArbitrationBasisV1, CompanyCardCounterpartyCoreV1, CompanyCardV2Snapshot,
    FinanceBasisV1, FinanceCellV1,
)
from product_api.company_reports.company_card_v2.narrative.catalog import (
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
)
from product_api.company_reports.company_card_v2.public_h2 import (
    EMPTY_CHART_FACTS_HASH,
    EMPTY_CHART_FACTS_VERSION,
    LegacySnapshotBinding,
    build_legacy_public_h2,
    build_public_h2,
)
from product_api.company_reports.company_card_v2.public_h2_models import (
    BLOCK_ORDER, COVERAGE_BLOCKS, CompanyPublicH2Response, PublicH2Narrative,
)
from product_api.company_reports.persistence.serialization import (
    calculate_company_report_snapshot_hash,
    company_report_from_snapshot,
)


_FIXTURES = Path(__file__).parent / "fixtures"


def _legacy_raw(version: str) -> dict[str, object]:
    raw = json.loads(
        (_FIXTURES / "company_reports" / (
            "snapshot_v1_legacy.json" if version == "1" else "snapshot_v2_exact.json"
        )).read_text(encoding="utf-8")
    )
    report_id = "00000000-0000-4000-8000-000000000001"
    generated_at = "2026-08-24T12:00:00Z"
    source = raw["counterparty"]["source"]
    source["received_at"] = generated_at
    raw.update({
        "report_id": report_id,
        "generated_at": generated_at,
        "target_identifier": "7701234567",
    })
    raw["counterparty"].update({
        "inn": "7701234567",
        "full_name": "Тестовое общество",
        "short_name": "Тест",
        "address": {"line_address": "г. Москва", "is_inaccuracy": False},
    })
    raw["datasets"]["counterparty"]["source"] = dict(source)
    raw["freshness"]["generated_at"] = generated_at
    return raw


class _Binding:
    def __init__(self) -> None:
        self.narrative = PublicH2Narrative(
            mode="artifact",
            renderer_version="fixture_v1",
            description="Проверочный текст подтверждённого fixture-only narrative. " * 10,
            statement_ids=("fixture_statement",),
            render_digest="a" * 64,
        )


class _FallbackBinding:
    narrative = PublicH2Narrative(
        mode="deterministic_fallback",
        renderer_version=FALLBACK_RENDERER_VERSION,
        description=FALLBACK_DESCRIPTION,
        statement_ids=(FALLBACK_PROFILE_ID,),
        comments=(),
        render_digest=sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest(),
    )


def _basis() -> FinanceBasisV1:
    cells = []
    values = {
        "1250": "10", "1240": "20", "1230": "30", "1500": "40",
        "1300": "50", "1400": "20", "1600": "100", "2110": "200",
        "2100": "80", "2200": "60", "2400": "40", "1210": "15",
    }
    for year in range(2019, 2026):
        for code, value in values.items():
            cells.append(FinanceCellV1(form="fixture", code=code, year=year, state="available_nonzero", value=Decimal(value)))
    return FinanceBasisV1(cells=tuple(cells))


def _snapshot() -> CompanyCardV2Snapshot:
    basis = _basis()
    return CompanyCardV2Snapshot(
        report_id="00000000-0000-4000-8000-000000000001", subject_inn="7701234567", target_inn="7701234567",
        rollout_config_generation=1,
        generated_at=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        counterparty=CompanyCardCounterpartyCoreV1(
            inn="7701234567", full_name="Тестовое общество", short_name="Тест",
            address="г. Москва", address_inaccuracy=False,
        ),
        finance_basis=basis, arbitration_basis=ArbitrationBasisV1(),
        chart_facts=build_chart_facts(basis), evidence_version="evidence_v1",
        privacy_version="privacy_v1",
    )


def test_fixture_finance_views_project_to_full_typed_f1_to_f5() -> None:
    snapshot = _snapshot()
    dto = build_public_h2(
        snapshot, narrative_binding=_Binding(),
        fixture_finance_views=build_finance_views(snapshot.finance_basis, anchor_year=2025),
    )
    assert dto.block_order == BLOCK_ORDER
    assert tuple(item.block_id for item in dto.coverage) == COVERAGE_BLOCKS
    assert dto.blocks.finance_f1 is not None
    assert dto.blocks.finance_f2 is not None and len(dto.blocks.finance_f2.periods) == 7
    assert dto.blocks.finance_f3 is not None and len(dto.blocks.finance_f3.points) == 7
    assert dto.blocks.finance_f4 is not None
    assert dto.blocks.finance_f5 is not None and len(dto.blocks.finance_f5.rows) == 9
    assert all(next(item for item in dto.coverage if item.block_id == block).state == "available" for block in COVERAGE_BLOCKS[2:7])
    assert all(getattr(dto.blocks, f"arbitration_a{number}") is None for number in range(1, 6))
    assert all(next(item for item in dto.coverage if item.block_id == f"arbitration_a{number}").state == "gate_closed" for number in range(1, 6))
    digest_payload = dto.model_dump(mode="json")
    digest_payload.pop("projection_digest")
    assert canonical_digest(digest_payload) == dto.projection_digest
    assert dto.chart_facts_version == snapshot.chart_facts.version
    assert dto.chart_facts_hash == snapshot.chart_facts.hash


def test_fixture_finance_input_is_closed_and_runtime_default_stays_gate_closed() -> None:
    snapshot = _snapshot()
    dto = build_public_h2(snapshot, narrative_binding=_Binding())
    assert dto.blocks.finance_f1 is None
    assert next(item for item in dto.coverage if item.block_id == "finance_f1").state == "gate_closed"
    with pytest.raises(ValueError, match="exactly F1..F5"):
        build_public_h2(snapshot, narrative_binding=_Binding(), fixture_finance_views={"F1": None})


def test_public_h2_rejects_wrong_root_cardinality_order_and_block_coverage() -> None:
    dto = build_public_h2(_snapshot(), narrative_binding=_Binding())
    payload = dto.model_dump(mode="json")
    payload["coverage"] = list(reversed(payload["coverage"]))
    with pytest.raises(Exception):
        CompanyPublicH2Response.model_validate(payload)

    payload = dto.model_dump(mode="json")
    payload["coverage"][2]["state"] = "available"
    with pytest.raises(Exception):
        CompanyPublicH2Response.model_validate(payload)

    payload = dto.model_dump(mode="json")
    payload["block_order"] = list(BLOCK_ORDER[:-1])
    with pytest.raises(Exception):
        CompanyPublicH2Response.model_validate(payload)


def test_public_h2_rejects_canonical_payload_larger_than_contract_cap() -> None:
    payload = build_public_h2(_snapshot(), narrative_binding=_Binding()).model_dump(mode="json")
    payload["checked_date_display"] = "x" * 524288
    with pytest.raises(Exception, match="public_projection_too_large"):
        CompanyPublicH2Response.model_validate(payload)


@pytest.mark.parametrize("version", ("1", "2"))
def test_legacy_v1_v2_projection_is_exact_safe_noindex_fallback(version: str) -> None:
    raw = _legacy_raw(version)
    report = company_report_from_snapshot(raw)
    snapshot_hash = calculate_company_report_snapshot_hash(raw)
    expected = json.loads(
        (_FIXTURES / "company_card_v2" / f"public_h2_v{version}_expected.json").read_text(
            encoding="utf-8"
        )
    )

    dto = build_legacy_public_h2(
        report,
        snapshot_binding=LegacySnapshotBinding(
            report_id=str(report.report_id),
            report_version=version,
            inn=report.target_identifier,
            lifecycle_status=report.status.value,
            stored_snapshot_hash=snapshot_hash,
            calculated_snapshot_hash=snapshot_hash,
        ),
        narrative_binding=_FallbackBinding(),
    )

    assert dto.report_version == version
    assert dto.snapshot_capability == "legacy_read_only"
    assert dto.projection_scope == "latest_unpublished"
    assert dto.indexable is False
    assert dto.chart_facts_version == expected["chart_facts_version"] == EMPTY_CHART_FACTS_VERSION
    assert dto.chart_facts_hash == expected["chart_facts_hash"] == EMPTY_CHART_FACTS_HASH
    assert dto.block_order == tuple(expected["block_order"])
    assert [item.model_dump(mode="json") for item in dto.coverage] == expected["coverage"]
    assert [item.model_dump(mode="json") for item in dto.limitations] == expected["limitations"]
    assert dto.narrative == _FallbackBinding.narrative
    assert dto.narrative.comments == ()
    assert all(getattr(dto.blocks, f"finance_f{number}") is None for number in range(1, 6))
    assert all(getattr(dto.blocks, f"arbitration_a{number}") is None for number in range(1, 6))
    digest_payload = dto.model_dump(mode="json")
    digest_payload.pop("projection_digest")
    assert dto.projection_digest == canonical_digest(digest_payload)


def test_legacy_projection_rejects_hash_report_inn_status_and_nonfallback_binding() -> None:
    raw = _legacy_raw("1")
    report = company_report_from_snapshot(raw)
    snapshot_hash = calculate_company_report_snapshot_hash(raw)
    base = {
        "report_id": str(report.report_id),
        "report_version": "1",
        "inn": report.target_identifier,
        "lifecycle_status": report.status.value,
        "stored_snapshot_hash": snapshot_hash,
        "calculated_snapshot_hash": snapshot_hash,
    }
    mutations = {
        "report_id": "00000000-0000-4000-8000-000000000099",
        "report_version": "2",
        "inn": "5001000000",
        "lifecycle_status": "complete",
        "stored_snapshot_hash": "f" * 64,
    }
    for field, value in mutations.items():
        changed = {**base, field: value}
        with pytest.raises(ValueError, match="legacy snapshot binding is invalid"):
            build_legacy_public_h2(
                report,
                snapshot_binding=LegacySnapshotBinding(**changed),
                narrative_binding=_FallbackBinding(),
            )

    with pytest.raises(ValueError, match="saved fallback binding is invalid"):
        build_legacy_public_h2(
            report,
            snapshot_binding=LegacySnapshotBinding(**base),
            narrative_binding=_Binding(),
        )
