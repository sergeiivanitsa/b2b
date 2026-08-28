from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from product_api.company_reports.company_card_v2.finance import build_chart_facts
from product_api.company_reports.company_card_v2.models import (
    ArbitrationBasisV1,
    CompanyCardCounterpartyCoreV1,
    CompanyCardV2Snapshot,
    FinanceBasisV1,
)
from product_api.company_reports.company_card_v2.narrative.catalog import (
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
)
from product_api.company_reports.company_card_v2.public_h2 import (
    PublicH2ProjectionBindingV1,
    build_public_h2,
    rebind_public_h2_projection,
)
from product_api.company_reports.company_card_v2.public_h2_models import (
    CompanyPublicH2Response,
    PublicH2Narrative,
)
from product_api.company_reports.company_card_v2 import service as h2_service


class _Narrative:
    narrative = PublicH2Narrative(
        mode="deterministic_fallback",
        renderer_version=FALLBACK_RENDERER_VERSION,
        description=FALLBACK_DESCRIPTION,
        statement_ids=(FALLBACK_PROFILE_ID,),
        render_digest=sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest(),
    )


def _snapshot() -> CompanyCardV2Snapshot:
    basis = FinanceBasisV1()
    return CompanyCardV2Snapshot(
        report_id="00000000-0000-4000-8000-000000000025",
        subject_inn="7701234567",
        target_inn="7701234567",
        rollout_config_generation=1,
        generated_at=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        counterparty=CompanyCardCounterpartyCoreV1(
            inn="7701234567", full_name="Тестовая компания"
        ),
        finance_basis=basis,
        arbitration_basis=ArbitrationBasisV1(),
        chart_facts=build_chart_facts(basis),
        evidence_version="evidence_v1",
        privacy_version="privacy_v1",
    )


def test_explicit_staged_and_active_projection_bindings_are_digest_bound() -> None:
    snapshot = _snapshot()
    default = build_public_h2(snapshot, narrative_binding=_Narrative())
    staged = build_public_h2(
        snapshot,
        narrative_binding=_Narrative(),
        projection_binding=PublicH2ProjectionBindingV1(
            projection_scope="staged_publication",
            canonical_path="/company/7701234567-company",
            indexable=False,
            published_lastmod=None,
        ),
    )
    active = build_public_h2(
        snapshot,
        narrative_binding=_Narrative(),
        projection_binding=PublicH2ProjectionBindingV1(
            projection_scope="active_publication",
            canonical_path="/company/7701234567-company",
            indexable=True,
            published_lastmod=snapshot.generated_at,
        ),
    )

    assert default.projection_scope == "latest_unpublished"
    assert staged.projection_scope == "staged_publication"
    assert active.projection_scope == "active_publication"
    assert active.indexable is True
    assert len({default.projection_digest, staged.projection_digest, active.projection_digest}) == 3


def test_validated_staged_projection_rebind_matches_direct_active_build() -> None:
    snapshot = _snapshot()
    staged = build_public_h2(
        snapshot,
        narrative_binding=_Narrative(),
        projection_binding=PublicH2ProjectionBindingV1(
            projection_scope="staged_publication",
            canonical_path="/company/7701234567-company",
            indexable=False,
            published_lastmod=None,
        ),
    )
    binding = PublicH2ProjectionBindingV1(
        projection_scope="active_publication",
        canonical_path="/company/7701234567-company-alt",
        indexable=True,
        published_lastmod=snapshot.generated_at,
    )
    rebound = rebind_public_h2_projection(
        staged, projection_binding=binding
    )
    direct = build_public_h2(
        snapshot,
        narrative_binding=_Narrative(),
        projection_binding=binding,
    )
    assert rebound == direct


@pytest.mark.parametrize(
    "binding",
    (
        PublicH2ProjectionBindingV1(
            projection_scope="active_publication",
            canonical_path="/company/7701234567-company",
            indexable=False,
            published_lastmod=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        ),
        PublicH2ProjectionBindingV1(
            projection_scope="active_publication",
            canonical_path="/company/7701234567-company-alt",
            indexable=True,
            published_lastmod=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        ),
    ),
)
def test_active_projection_binding_accepts_exact_noindex_or_indexable_shape(
    binding: PublicH2ProjectionBindingV1,
) -> None:
    dto = build_public_h2(
        _snapshot(), narrative_binding=_Narrative(), projection_binding=binding
    )
    assert dto.canonical_path == binding.canonical_path
    assert dto.indexable is binding.indexable


def test_non_active_binding_cannot_be_indexable_or_carry_lastmod() -> None:
    with pytest.raises(ValueError, match="must be noindex"):
        PublicH2ProjectionBindingV1(
            projection_scope="staged_publication",
            canonical_path="/company/7701234567-company",
            indexable=True,
            published_lastmod=None,
        )
    with pytest.raises(ValueError, match="must be noindex"):
        PublicH2ProjectionBindingV1(
            projection_scope="latest_unpublished",
            canonical_path="/company/7701234567-company",
            indexable=False,
            published_lastmod=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        )


def test_active_binding_requires_aware_immutable_lastmod() -> None:
    with pytest.raises(ValueError, match="lastmod"):
        PublicH2ProjectionBindingV1(
            projection_scope="active_publication",
            canonical_path="/company/7701234567-company",
            indexable=True,
            published_lastmod=None,
        )
    with pytest.raises(ValueError, match="lastmod"):
        PublicH2ProjectionBindingV1(
            projection_scope="active_publication",
            canonical_path="/company/7701234567-company",
            indexable=True,
            published_lastmod=datetime(2026, 8, 24, 12),
        )


def test_persisted_active_binding_requires_publication_policy_v3() -> None:
    pin = SimpleNamespace(
        projection_scope="active_publication",
        publication_policy_version="company_public_h2_publication_v2",
        narrative_binding_status="resolved",
        canonical_path="/company/7701234567-company",
        indexable=False,
        published_lastmod=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="active public H2 pin shape"):
        h2_service._projection_binding_for_pin(pin, expected_inn="7701234567")


@pytest.mark.asyncio
async def test_active_pin_planning_requires_exact_report_generated_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated_at = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    record = SimpleNamespace(generated_at=generated_at)
    source_pin = SimpleNamespace(
        projection_scope="staged_publication",
        indexable=False,
        canonical_path=None,
        published_lastmod=None,
    )

    async def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid lastmod must fail before saved-result reads")

    monkeypatch.setattr(h2_service, "_resolve_exact_v3", forbidden)
    with pytest.raises(h2_service.PublicH2Invalid, match="source binding"):
        await h2_service.build_active_public_h2_for_pin(
            object(),
            record=record,
            source_pin=source_pin,
            expected_subject_id="subject",
            expected_inn="7701234567",
            canonical_path="/company/7701234567-company",
            indexable=True,
            published_lastmod=datetime(2026, 8, 24, 13, tzinfo=timezone.utc),
        )


def _indexable_v3_projection() -> CompanyPublicH2Response:
    root = Path(__file__).resolve().parents[3]
    fixture = json.loads(
        (
            root
            / "shared"
            / "fixtures"
            / "company_public_h2_contract_v1_arbitration_masked_v3.json"
        ).read_text(encoding="utf-8")
    )
    staged = rebind_public_h2_projection(
        CompanyPublicH2Response.model_validate(fixture),
        projection_binding=PublicH2ProjectionBindingV1(
            projection_scope="staged_publication",
            canonical_path="/company/7700000000-company",
            indexable=False,
            published_lastmod=None,
        ),
    )
    return rebind_public_h2_projection(
        staged,
        projection_binding=PublicH2ProjectionBindingV1(
            projection_scope="active_publication",
            canonical_path="/company/7700000000-company",
            indexable=True,
            published_lastmod=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        ),
    )


def test_indexable_v3_projection_requires_all_bound_source_families() -> None:
    projection = _indexable_v3_projection()
    h2_service._validate_indexable_public_h2(projection)

    without_arbitration_source = projection.model_copy(
        update={"sources": projection.sources[:-1]}
    )
    with pytest.raises(ValueError, match="identity"):
        h2_service._validate_indexable_public_h2(without_arbitration_source)


@pytest.mark.parametrize(
    "state",
    ("failed", "conflict", "gate_closed", "legacy_unavailable", "not_requested"),
)
def test_indexable_v3_projection_rejects_unsafe_or_unverified_coverage(
    state: str,
) -> None:
    projection = _indexable_v3_projection()
    finance = next(
        item for item in projection.coverage if item.block_id == "finance_f1"
    )
    coverage = tuple(
        finance.model_copy(update={"state": state})
        if item.block_id == finance.block_id
        else item
        for item in projection.coverage
    )
    unsafe = projection.model_copy(update={"coverage": coverage})

    with pytest.raises(ValueError, match="coverage|gate"):
        h2_service._validate_indexable_public_h2(unsafe)


@pytest.mark.asyncio
async def test_active_indexable_planning_rejects_structurally_valid_gate_closed_dto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated_at = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    staged = build_public_h2(
        _snapshot(),
        narrative_binding=_Narrative(),
        projection_binding=PublicH2ProjectionBindingV1(
            projection_scope="staged_publication",
            canonical_path="/company/7701234567-company",
            indexable=False,
            published_lastmod=None,
        ),
    )

    async def staged_result(*_args: object, **_kwargs: object) -> object:
        return staged

    monkeypatch.setattr(h2_service, "_resolve_exact_v3", staged_result)
    with pytest.raises(h2_service.PublicH2Invalid, match="active projection"):
        await h2_service.build_active_public_h2_for_pin(
            object(),
            record=SimpleNamespace(generated_at=generated_at),
            source_pin=SimpleNamespace(
                projection_scope="staged_publication",
                indexable=False,
                canonical_path=None,
                published_lastmod=None,
            ),
            expected_subject_id="subject",
            expected_inn="7701234567",
            canonical_path="/company/7701234567-company",
            indexable=True,
            published_lastmod=generated_at,
        )
