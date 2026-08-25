from datetime import datetime, timezone
import json
from pathlib import Path

from product_api.company_reports.company_card_v2.finance import build_chart_facts
from product_api.company_reports.company_card_v2.models import ArbitrationBasisV1, CompanyCardCounterpartyCoreV1, CompanyCardV2Snapshot, FinanceBasisV1
from product_api.company_reports.company_card_v2.public_h2 import build_public_h2
from product_api.company_reports.company_card_v2.public_h2_document import public_h2_security_headers, render_public_h2_document
from product_api.company_reports.company_card_v2.public_h2_models import CompanyPublicH2Response, PublicH2Narrative
from product_api.company_reports.company_card_v2.public_h2_asset_manifest import load_public_h2_asset_manifest
from product_api.company_reports.company_card_v2.narrative.catalog import FALLBACK_DESCRIPTION, FALLBACK_PROFILE_ID, FALLBACK_RENDERER_VERSION
from hashlib import sha256


class _Narrative:
    narrative = PublicH2Narrative(mode="deterministic_fallback", renderer_version=FALLBACK_RENDERER_VERSION, description=FALLBACK_DESCRIPTION, statement_ids=(FALLBACK_PROFILE_ID,), render_digest=sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest())


def _dto():
    basis = FinanceBasisV1()
    snapshot = CompanyCardV2Snapshot(
        report_id="00000000-0000-4000-8000-000000000001", subject_inn="7701234567", target_inn="7701234567", rollout_config_generation=1,
        generated_at=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        counterparty=CompanyCardCounterpartyCoreV1(inn="7701234567", full_name="Тест <компания>"), finance_basis=basis,
        arbitration_basis=ArbitrationBasisV1(), chart_facts=build_chart_facts(basis), evidence_version="evidence_v1", privacy_version="privacy_v1",
    )
    return build_public_h2(snapshot, narrative_binding=_Narrative())


def test_h2_document_has_one_safe_state_and_no_analytics() -> None:
    html = render_public_h2_document(_dto(), load_public_h2_asset_manifest(), "test-nonce")
    assert html.count('id="company-public-h2-state"') == 1
    assert 'nonce="test-nonce"' in html
    assert "Описание деятельности" in html
    assert 'webvisor' not in html.lower()
    assert '/claims?report_id=00000000-0000-4000-8000-000000000001' in html


def test_h2_security_headers_are_no_store_and_nonce_bound() -> None:
    headers = public_h2_security_headers("nonce", "noindex,follow")
    assert headers["Cache-Control"] == "no-store"
    assert "'nonce-nonce'" in headers["Content-Security-Policy"]
    assert headers["X-Robots-Tag"] == "noindex,follow"


def test_shared_ssr_golden_is_byte_exact_and_uses_stable_shell_ids() -> None:
    root = Path(__file__).parents[3]
    fixture = json.loads((root / "shared/fixtures/company_public_h2_ssr_v1.json").read_text(encoding="utf-8"))
    assert fixture["dto_fixture"] == "shared/fixtures/company_public_h2_contract_v1.json"
    dto = CompanyPublicH2Response.model_validate(json.loads((root / fixture["dto_fixture"]).read_text(encoding="utf-8")))
    html = render_public_h2_document(dto, load_public_h2_asset_manifest(), fixture["nonce"], fixture["robots"])
    expected = (root / fixture["html_fixture"]).read_bytes()
    assert html.encode("utf-8") == expected
    assert sha256(html.encode("utf-8")).hexdigest() == fixture["html_sha256"]
    for element_id in fixture["required_ids"]:
        assert f'id="{element_id}"' in html
    for coverage in dto.coverage:
        assert f'data-h2-coverage="{coverage.block_id}"' in html
        for code in coverage.limitation_codes:
            assert f'href="#limitation-{code}"' in html
    for limitation in dto.limitations:
        assert f'id="limitation-{limitation.code}"' in html
    assert all(getattr(dto.blocks, f"finance_f{index}") is not None for index in range(1, 6))
    assert all(getattr(dto.blocks, f"arbitration_a{index}") is not None for index in range(1, 6))


def test_h2_document_uses_fixed_missing_status_text() -> None:
    dto = _dto().model_copy(update={"identity": _dto().identity.model_copy(update={"status": None})})
    html = render_public_h2_document(dto, load_public_h2_asset_manifest(), "test-nonce")
    assert "Статус отчёта: Статус не указан в отчёте" in html
    header = html.split('<header id="hero-status">', 1)[1].split("</header>", 1)[0]
    assert dto.projection_scope not in header
