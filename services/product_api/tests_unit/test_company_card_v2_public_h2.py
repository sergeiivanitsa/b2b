from datetime import datetime, timezone
from decimal import Decimal

import pytest

from product_api.company_reports.company_card_v2.canonical_json import canonical_digest
from product_api.company_reports.company_card_v2.finance import build_chart_facts, build_finance_views
from product_api.company_reports.company_card_v2.models import (
    ArbitrationBasisV1, CompanyCardCounterpartyCoreV1, CompanyCardV2Snapshot,
    FinanceBasisV1, FinanceCellV1,
)
from product_api.company_reports.company_card_v2.public_h2 import build_public_h2
from product_api.company_reports.company_card_v2.public_h2_models import (
    BLOCK_ORDER, COVERAGE_BLOCKS, CompanyPublicH2Response, PublicH2Narrative,
)


class _Binding:
    def __init__(self) -> None:
        self.narrative = PublicH2Narrative(
            mode="artifact",
            renderer_version="fixture_v1",
            description="Проверочный текст подтверждённого fixture-only narrative. " * 10,
            statement_ids=("fixture_statement",),
            render_digest="a" * 64,
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
