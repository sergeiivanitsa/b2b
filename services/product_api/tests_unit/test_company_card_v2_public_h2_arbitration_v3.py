from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path

import pytest

from product_api.company_reports.company_card_v2 import public_h2 as public_h2_module
from product_api.company_reports.company_card_v2 import (
    public_h2_models as public_h2_models_module,
)
from product_api.company_reports.company_card_v2.arbitration_v2 import (
    arbitration_chart_facts_hash,
    build_arbitration_chart_facts,
    empty_arbitration_basis_v2,
)
from product_api.company_reports.company_card_v2.canonical_json import (
    canonical_digest,
    canonical_json_bytes,
)
from product_api.company_reports.company_card_v2.finance import build_chart_facts
from product_api.company_reports.company_card_v2.models import (
    ArbitrationBasisLimitationV2,
    ArbitrationBasisV2,
    ArbitrationCollectionCountersV2,
    ArbitrationPageManifestV2,
    CompanyCardCounterpartyCoreV1,
    CompanyCardV2SnapshotV3,
    FinanceBasisV1,
    NarrativeEvidenceV1,
    PrivateOpponentTokenV2,
    SanitizedArbitrationCaseV2,
)
from product_api.company_reports.company_card_v2.narrative.catalog import (
    FALLBACK_DESCRIPTION,
    FALLBACK_PROFILE_ID,
    FALLBACK_RENDERER_VERSION,
)
from product_api.company_reports.company_card_v2.public_h2 import (
    _finalize_public_h2_payload,
    build_public_h2,
)
from product_api.company_reports.company_card_v2.public_h2_document import (
    render_public_h2_body,
    render_public_h2_document,
)
from product_api.company_reports.company_card_v2.public_h2_asset_manifest import (
    validate_public_h2_asset_manifest,
)
from product_api.company_reports.company_card_v2.public_h2_models import (
    CompanyPublicH2Response,
    PublicH2Narrative,
)


REPORT_ID = "00000000-0000-4000-8000-000000000001"
INN = "7700000000"
RECEIVED_AT = datetime(2026, 8, 27, 1, 2, 3, 123456, tzinfo=timezone.utc)


class _Narrative:
    narrative = PublicH2Narrative(
        mode="deterministic_fallback",
        renderer_version=FALLBACK_RENDERER_VERSION,
        description=FALLBACK_DESCRIPTION,
        statement_ids=(FALLBACK_PROFILE_ID,),
        comments=(),
        render_digest=sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest(),
    )


def _token(value: str) -> PrivateOpponentTokenV2:
    return PrivateOpponentTokenV2(
        key_id="active_2026",
        value=value * 64,
    )


def _basis(
    cases: tuple[SanitizedArbitrationCaseV2, ...],
    *,
    source_total: int | None = None,
    completion_reasons: tuple[str, ...] = ("complete",),
    limitation_codes: tuple[str, ...] = ("arbitration_calendar_unverified",),
    opponent_probe_count: int | None = None,
) -> ArbitrationBasisV2:
    tokens = tuple(token for case in cases for token in case.opponent_tokens)
    groups = len({token.value for token in tokens})
    rows = len(cases)
    source_total = rows if source_total is None else source_total
    return ArbitrationBasisV2(
        source_total=source_total,
        page_manifest=(
            ArbitrationPageManifestV2(
                returned_count=rows,
                accepted_count=rows,
                response_hash="f" * 64,
            ),
        ),
        provider_received_at=RECEIVED_AT,
        counters=ArbitrationCollectionCountersV2(
            pages_requested=1,
            pages_accepted=1,
            rows_observed=rows,
            rows_processed=rows,
            rows_shape_valid=rows,
            unique_case_count=rows,
            opponent_token_count=len(tokens),
            opponent_group_count=groups,
            opponent_group_probe_count=(
                groups if opponent_probe_count is None else opponent_probe_count
            ),
        ),
        completion_reasons=completion_reasons,  # type: ignore[arg-type]
        collection_complete=completion_reasons == ("complete",),
        unknown_year_count=sum(case.year is None for case in cases),
        mask_algorithm_version="opponent_hmac_sha256_v1",
        mask_key_id="active_2026",
        sanitized_cases=cases,
        limitations=tuple(
            ArbitrationBasisLimitationV2(code=code)  # type: ignore[arg-type]
            for code in limitation_codes
        ),
    )


def _snapshot(basis: ArbitrationBasisV2) -> CompanyCardV2SnapshotV3:
    finance = FinanceBasisV1()
    facts = build_arbitration_chart_facts(basis)
    return CompanyCardV2SnapshotV3(
        report_id=REPORT_ID,
        subject_inn=INN,
        target_inn=INN,
        rollout_config_generation=7,
        generated_at=datetime(2026, 8, 27, 1, tzinfo=timezone.utc),
        counterparty=CompanyCardCounterpartyCoreV1(
            inn=INN,
            full_name="Тестовое общество",
            short_name="Тест",
        ),
        finance_basis=finance,
        arbitration_basis=basis,
        chart_facts=build_chart_facts(finance),
        evidence_version="evidence_registry_v1",
        privacy_version="privacy_v1",
        narrative_evidence=NarrativeEvidenceV1(
            limitation_code="primary_activity_not_admitted"
        ),
        arbitration_chart_facts=facts,
        arbitration_chart_facts_hash=arbitration_chart_facts_hash(facts),
    )


def _project(basis: ArbitrationBasisV2) -> CompanyPublicH2Response:
    return build_public_h2(
        _snapshot(basis),
        narrative_binding=_Narrative(),
        finance_enabled=True,
        arbitration_enabled=True,
    )


@pytest.mark.parametrize(
    ("finance_enabled", "arbitration_enabled"),
    ((False, False), (True, False), (False, True)),
)
def test_v3_projection_requires_exact_finance_plus_arbitration_policy(
    finance_enabled: bool,
    arbitration_enabled: bool,
) -> None:
    with pytest.raises(ValueError, match="publication policy"):
        build_public_h2(
            _snapshot(_basis(())),
            narrative_binding=_Narrative(),
            finance_enabled=finance_enabled,
            arbitration_enabled=arbitration_enabled,
        )


def test_frozen_closed_legacy_arbitration_source_remains_accepted() -> None:
    root = Path(__file__).parents[3]
    html = (
        root / "shared/fixtures/company_public_h2_ssr_v1_closed.html"
    ).read_text(encoding="utf-8")
    marker = (
        '<script id="company-public-h2-state" '
        'type="application/json" nonce="fixture-closed-nonce">'
    )
    raw = html.split(marker, 1)[1].split("</script>", 1)[0]

    dto = CompanyPublicH2Response.model_validate_json(raw)

    assert dto.report_version == "3"
    assert dto.snapshot_capability == "card_v2"
    assert dto.sources[-1].dataset == "arbitration"
    assert dto.sources[-1].normalization_version == "company_card_v2_v1"
    assert all(
        getattr(dto.blocks, f"arbitration_a{index}") is None
        for index in range(1, 6)
    )


def test_a1_known_population_requires_a_known_year_bucket() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    a1 = payload["blocks"]["arbitration_a1"]
    a1["buckets"] = [
        bucket for bucket in a1["buckets"] if bucket["year"] is None
    ]
    a1["displayed_start_year"] = None
    a1["displayed_end_year"] = None

    with pytest.raises(ValueError, match="A1 observed bounds"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a1_truncated_year_population_requires_exactly_ten_known_buckets() -> None:
    cases = tuple(
        SanitizedArbitrationCaseV2(
            case_id=f"year-{year}",
            first_number=f"А40-{year}/2025",
            year=year,
            role="plaintiff",
            outcome="unknown",
            amount_state="missing",
            currency_state="missing",
            limitations=(
                "arbitration_amount_missing",
                "arbitration_currency_missing",
            ),
        )
        for year in range(2015, 2026)
    )
    payload = _project(_basis(
        cases,
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    a1 = payload["blocks"]["arbitration_a1"]
    a1["buckets"] = a1["buckets"][1:]
    a1["displayed_start_year"] = a1["buckets"][0]["year"]

    with pytest.raises(ValueError, match="A1 observed bounds"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_private_case_id_can_equal_semantic_fact_without_false_leak() -> None:
    cases = list(_complete_cases())
    cases[0] = cases[0].model_copy(update={"case_id": "plaintiff"})

    dto = _project(_basis(
        tuple(cases),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    ))

    assert dto.blocks.arbitration_a2 is not None
    assert any(
        bar.category_id == "plaintiff"
        for bar in dto.blocks.arbitration_a2.bars
    )


def test_private_identity_scanner_is_path_aware() -> None:
    private_values = frozenset({"plaintiff", "private-case"})

    public_h2_module._assert_no_private_arbitration_identity_at_public_sinks(
        {"role": "plaintiff", "case_number": None},
        private_values=private_values,
    )
    with pytest.raises(ValueError, match="private arbitration identity"):
        public_h2_module._assert_no_private_arbitration_identity_at_public_sinks(
            {"role": "plaintiff", "case_number": "private-case"},
            private_values=private_values,
        )
    with pytest.raises(ValueError, match="private arbitration identity"):
        public_h2_module._assert_no_private_arbitration_identity_at_public_sinks(
            {"limitations": [{"message": "private-case"}]},
            private_values=private_values,
        )


@pytest.mark.parametrize(
    "fixed_message",
    (
        public_h2_models_module.ARBITRATION_PUBLIC_LIMITATION_MESSAGES[
            "arbitration_calendar_unverified"
        ],
        "Часть реквизитов недоступна в текущем подтверждённом контуре.",
    ),
)
def test_private_case_id_can_equal_independent_fixed_limitation_message(
    fixed_message: str,
) -> None:
    cases = list(_complete_cases())
    cases[0] = cases[0].model_copy(update={"case_id": fixed_message})
    cases.sort(key=lambda case: case.case_id)

    dto = _project(_basis(
        tuple(cases),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    ))

    assert any(item.message == fixed_message for item in dto.limitations)


def test_fixed_limitation_message_exemption_requires_its_closed_contract() -> None:
    message = public_h2_models_module.ARBITRATION_PUBLIC_LIMITATION_MESSAGES[
        "arbitration_calendar_unverified"
    ]

    with pytest.raises(ValueError, match="private arbitration identity"):
        public_h2_module._assert_no_private_arbitration_identity_at_public_sinks(
            {
                "limitations": [{
                    "code": "not-the-frozen-arbitration-code",
                    "message": message,
                }]
            },
            private_values=frozenset({message}),
        )


def test_policy_v3_safety_rejects_private_identity_in_limitation_message() -> None:
    basis = _basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )
    snapshot = _snapshot(basis)
    dto = _project(basis)
    limitations = list(dto.limitations)
    limitations[0] = limitations[0].model_copy(
        update={"message": "private-z"}
    )
    tampered = dto.model_copy(update={"limitations": tuple(limitations)})

    with pytest.raises(ValueError, match="private arbitration identity"):
        public_h2_module._assert_policy_v3_projection_safe(
            tampered,
            snapshot,
        )


def test_v3_arbitration_decimal_rejects_negative_zero() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    payload["blocks"]["arbitration_a4"]["currency_groups"][0]["axis"][
        "axis_max_decimal"
    ] = "-0"

    with pytest.raises(ValueError, match="negative zero"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a4_large_decimal_order_is_exact_and_context_independent() -> None:
    smaller = "123456789012345678901234567890.1"
    larger = "123456789012345678901234567890.2"
    cases = (
        SanitizedArbitrationCaseV2(
            case_id="a-context-order",
            first_number="А40-1/2025",
            year=2025,
            role="plaintiff",
            outcome="unknown",
            amount_state="available",
            amount=Decimal(smaller),
            currency_state="rub",
        ),
        SanitizedArbitrationCaseV2(
            case_id="z-context-order",
            first_number="А40-2/2025",
            year=2025,
            role="plaintiff",
            outcome="unknown",
            amount_state="available",
            amount=Decimal(larger),
            currency_state="rub",
        ),
    )
    basis = _basis(cases)

    with localcontext() as context:
        context.prec = 6
        low_precision = _project(basis)
    with localcontext() as context:
        context.prec = 96
        high_precision = _project(basis)

    assert low_precision.model_dump(mode="json") == high_precision.model_dump(
        mode="json"
    )
    group = low_precision.blocks.arbitration_a4.currency_groups[0]
    assert [item.amount.source_decimal for item in group.cases] == [
        larger,
        smaller,
    ]


def test_a4_large_decimal_validator_rejects_reversed_exact_order() -> None:
    cases = tuple(
        SanitizedArbitrationCaseV2(
            case_id=case_id,
            first_number=first_number,
            year=2025,
            role="plaintiff",
            outcome="unknown",
            amount_state="available",
            amount=Decimal(amount),
            currency_state="rub",
        )
        for case_id, first_number, amount in (
            (
                "a-context-order",
                "А40-1/2025",
                "123456789012345678901234567890.1",
            ),
            (
                "z-context-order",
                "А40-2/2025",
                "123456789012345678901234567890.2",
            ),
        )
    )
    payload = _project(_basis(cases)).model_dump(mode="json")
    group = payload["blocks"]["arbitration_a4"]["currency_groups"][0]
    group["cases"].reverse()
    group["case_geometries"].reverse()

    with localcontext() as context:
        context.prec = 6
        with pytest.raises(ValueError, match="A4 case details are not ordered"):
            CompanyPublicH2Response.model_validate(_redigest(payload))


def test_v3_safe_case_dates_require_canonical_iso_form() -> None:
    dto = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    ))
    detail = dto.blocks.arbitration_a4.currency_groups[0].cases[0]
    invalid = detail.model_copy(update={"start_date": "20250102"})

    with pytest.raises(ValueError, match="case date"):
        public_h2_models_module._validate_case_detail(invalid)


def test_v3_safe_case_year_must_match_start_date() -> None:
    dto = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    ))
    detail = dto.blocks.arbitration_a4.currency_groups[0].cases[0]
    invalid = detail.model_copy(update={"year": 2024})

    with pytest.raises(ValueError, match="year/date pairing"):
        public_h2_models_module._validate_case_detail(invalid)


@pytest.mark.parametrize("role", ("other", "unattributed"))
def test_v3_non_party_role_forces_unknown_outcome(role: str) -> None:
    dto = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    ))
    detail = dto.blocks.arbitration_a4.currency_groups[0].cases[0]
    invalid = detail.model_copy(update={"role": role, "outcome": "won"})

    with pytest.raises(ValueError, match="role/outcome pairing"):
        public_h2_models_module._validate_case_detail(invalid)


def _cross_case_number_cases(
    second_first_number: str | None,
    *,
    collision_suppressed: bool = False,
) -> tuple[SanitizedArbitrationCaseV2, ...]:
    common = {
        "year": 2025,
        "role": "plaintiff",
        "outcome": "unknown",
        "amount_state": "missing",
        "currency_state": "missing",
    }
    return (
        SanitizedArbitrationCaseV2(
            case_id="A40-1/2025",
            first_number="A40-2/2025",
            limitations=(
                "arbitration_amount_missing",
                "arbitration_currency_missing",
            ),
            **common,
        ),
        SanitizedArbitrationCaseV2(
            case_id="private-cross-case-number",
            first_number=second_first_number,
            limitations=(
                *(("arbitration_first_number_identity_collision",) if collision_suppressed else ()),
                "arbitration_amount_missing",
                "arbitration_currency_missing",
            ),
            **common,
        ),
    )


def test_basis_rejects_unsuppressed_cross_case_number_identity() -> None:
    with pytest.raises(ValueError, match="identity collision must be suppressed"):
        _basis(
            _cross_case_number_cases("A40-1/2025"),
            limitation_codes=(
                "arbitration_calendar_unverified",
                "arbitration_amount_missing",
                "arbitration_currency_missing",
            ),
        )


def test_complete_basis_rejects_unwitnessed_identity_collision_reason() -> None:
    case = SanitizedArbitrationCaseV2(
        case_id="private-no-collision-witness",
        first_number=None,
        year=2025,
        role="plaintiff",
        outcome="unknown",
        amount_state="missing",
        currency_state="missing",
        limitations=(
            "arbitration_first_number_identity_collision",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )

    with pytest.raises(ValueError, match="lacks a case-id witness"):
        _basis(
            (case,),
            limitation_codes=(
                "arbitration_calendar_unverified",
                "arbitration_first_number_identity_collision",
                "arbitration_amount_missing",
                "arbitration_currency_missing",
            ),
        )


def test_v3_snapshot_wire_rejects_unsuppressed_cross_case_number_identity() -> None:
    snapshot = _snapshot(_basis(
        _cross_case_number_cases("A40-3/2025"),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    snapshot["arbitration_basis"]["sanitized_cases"][1]["first_number"] = (
        "A40-1/2025"
    )

    with pytest.raises(ValueError, match="identity collision must be suppressed"):
        CompanyCardV2SnapshotV3.model_validate(snapshot)


def test_suppressed_cross_case_number_identity_projects_safely() -> None:
    dto = _project(_basis(
        _cross_case_number_cases(None, collision_suppressed=True),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_first_number_identity_collision",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    ))

    cases = tuple(
        item
        for bar in dto.blocks.arbitration_a2.bars
        for item in bar.cases
    )
    assert sorted(item.case_number for item in cases if item.case_number is not None) == [
        "A40-2/2025"
    ]
    assert sum(item.case_number is None for item in cases) == 1


def _fully_visible_valid_date_cases() -> tuple[SanitizedArbitrationCaseV2, ...]:
    return tuple(
        SanitizedArbitrationCaseV2(
            case_id=f"date-truth-{index}",
            first_number=f"A40-{index}/2025",
            year=2025,
            role="plaintiff",
            outcome="unknown",
            date_start=date(2025, 1, index),
            date_update=date(2025, 1, index + 1),
            duration_days=1,
            amount_state="available",
            amount=Decimal(index),
            currency_state="rub",
        )
        for index in (1, 2)
    )


def test_full_visible_projection_rejects_impossible_date_limitation_truth() -> None:
    payload = _project(_basis(
        _fully_visible_valid_date_cases()
    )).model_dump(mode="json")
    _append_arbitration_limitation(
        payload,
        code="arbitration_date_invalid",
        root_block=None,
        coverage_blocks=tuple(f"arbitration_a{index}" for index in range(1, 6)),
    )

    with pytest.raises(ValueError, match="invalid-date limitation"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_full_visible_projection_rejects_impossible_year_conflict_truth() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    _append_arbitration_limitation(
        payload,
        code="arbitration_year_conflict",
        root_block=None,
        coverage_blocks=tuple(f"arbitration_a{index}" for index in range(1, 6)),
    )

    with pytest.raises(ValueError, match="year-conflict limitation"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_full_visible_projection_rejects_unwitnessed_date_inversion() -> None:
    payload = _project(_basis(
        _fully_visible_valid_date_cases()
    )).model_dump(mode="json")
    _append_arbitration_limitation(
        payload,
        code="arbitration_date_inversion",
        root_block=None,
        coverage_blocks=tuple(f"arbitration_a{index}" for index in range(1, 6)),
    )

    with pytest.raises(ValueError, match="date-inversion limitation"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


@pytest.mark.parametrize(
    "code",
    (
        "arbitration_first_number_unavailable",
        "arbitration_first_number_identity_collision",
    ),
)
def test_fully_numbered_projection_rejects_unwitnessed_number_limitation(
    code: str,
) -> None:
    payload = _project(_basis(
        _cross_case_number_cases("A40-3/2025"),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    _append_arbitration_limitation(
        payload,
        code=code,
        root_block=None,
        coverage_blocks=tuple(f"arbitration_a{index}" for index in range(1, 6)),
    )

    with pytest.raises(ValueError, match="first-number limitation population"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_one_hidden_number_cannot_explain_both_mutually_exclusive_codes() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    _append_arbitration_limitation(
        payload,
        code="arbitration_first_number_identity_collision",
        root_block=None,
        coverage_blocks=tuple(f"arbitration_a{index}" for index in range(1, 6)),
    )

    with pytest.raises(ValueError, match="first-number limitation population"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


@pytest.mark.parametrize(
    "code",
    ("arbitration_amount_invalid", "arbitration_currency_invalid"),
)
def test_a4_state_limitations_require_disjoint_case_capacity(code: str) -> None:
    payload = _project(_basis(
        _cross_case_number_cases("A40-3/2025"),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    _append_arbitration_limitation(
        payload,
        code=code,
        root_block="arbitration_a4",
        coverage_blocks=("arbitration_a4",),
    )

    with pytest.raises(ValueError, match="A4 limitation population"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def _replace_string(value: object, old: str, new: str) -> object:
    if isinstance(value, dict):
        return {key: _replace_string(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_string(item, old, new) for item in value]
    return new if value == old else value


def test_case_public_ordinal_cannot_exceed_case_population() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    payload = _replace_string(payload, "case_000002", "case_001000")

    with pytest.raises(ValueError, match="public ordinal"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_opponent_public_ordinal_cannot_exceed_group_population() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    payload = _replace_string(
        payload,
        "opponent_000002",
        "opponent_020000",
    )
    payload = _replace_string(
        payload,
        "Сторона скрыта 2",
        "Сторона скрыта 20000",
    )

    with pytest.raises(ValueError, match="public ordinal"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a4_eligible_population_cannot_exceed_unique_cases() -> None:
    cases = tuple(
        SanitizedArbitrationCaseV2(
            case_id=f"a4-cap-{index:02d}",
            first_number=f"А40-{index + 1}/2025",
            year=2025,
            role="plaintiff",
            outcome="unknown",
            amount_state="available",
            amount=Decimal(index + 1),
            currency_state="rub",
        )
        for index in range(20)
    )
    payload = _project(_basis(
        cases,
        limitation_codes=("arbitration_calendar_unverified",),
    )).model_dump(mode="json")
    a4 = payload["blocks"]["arbitration_a4"]
    group = a4["currency_groups"][0]
    group["scope"]["eligible_total"] = 21
    group["scope"]["label"] = "показано 20 из 21 дел"
    coverage = payload["coverage"][10]
    coverage["eligible"] = 21
    coverage["state"] = "partial"
    coverage["limitation_codes"] = ["arbitration_amount_invalid"]
    payload["limitations"].append({
        "code": "arbitration_amount_invalid",
        "block_id": "arbitration_a4",
        "field_id": None,
        "message": "Для части дел цена иска не прошла точную числовую проверку.",
    })

    with pytest.raises(ValueError, match="A4 counters"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


@pytest.mark.parametrize(
    "field",
    ("missing_amount_count", "missing_currency_count"),
)
def test_a4_missing_counter_is_disjoint_from_eligible_population(
    field: str,
) -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    payload["blocks"]["arbitration_a4"][field] = 2

    with pytest.raises(ValueError, match="A4 counters"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a4_visible_amount_case_cannot_be_removed_from_eligible_population() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    payload["blocks"]["arbitration_a4"]["currency_groups"] = []
    payload["coverage"][10]["eligible"] = 0

    with pytest.raises(ValueError, match="A4 visible"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a4_zero_eligible_population_forbids_an_empty_currency_group() -> None:
    payload = _project(_basis(())).model_dump(mode="json")
    payload["blocks"]["arbitration_a4"]["currency_groups"] = [{
        "source_currency_id": "RUB",
        "display_currency": "₽",
        "axis": {
            "axis_min_decimal": "0",
            "axis_max_decimal": "0",
        },
        "case_geometries": [],
        "scope": {
            "population_scope": "complete_collection",
            "source_total": 0,
            "rows_received": 0,
            "eligible_total": 0,
            "shown": 0,
            "cap": 20,
            "label": "показано 0 из 0 дел",
        },
        "cases": [],
    }]

    with pytest.raises(ValueError, match="A4 group is unexpected"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_fully_shown_category_must_include_every_visible_matching_case() -> None:
    cases = (
        SanitizedArbitrationCaseV2(
            case_id="cross-plaintiff",
            first_number="А40-1/2025",
            year=2025,
            role="plaintiff",
            outcome="unknown",
            amount_state="missing",
            currency_state="missing",
            limitations=(
                "arbitration_amount_missing",
                "arbitration_currency_missing",
            ),
        ),
        *(
            SanitizedArbitrationCaseV2(
                case_id=f"cross-respondent-{index:02d}",
                first_number=f"А40-{index + 2}/2025",
                year=2025,
                role="respondent",
                outcome="unknown",
                amount_state="missing",
                currency_state="missing",
                limitations=(
                    "arbitration_amount_missing",
                    "arbitration_currency_missing",
                ),
            )
            for index in range(21)
        ),
    )
    payload = _project(_basis(
        cases,
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")

    visible_ids: set[str] = set()

    def collect_case_ids(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "case_public_id" and isinstance(item, str):
                    visible_ids.add(item)
                else:
                    collect_case_ids(item)
        elif isinstance(value, list):
            for item in value:
                collect_case_ids(item)

    collect_case_ids(payload["blocks"])
    hidden_ids = {
        f"case_{index:06d}" for index in range(1, len(cases) + 1)
    } - visible_ids
    assert len(hidden_ids) == 1
    plaintiff_bar = payload["blocks"]["arbitration_a2"]["bars"][0]
    plaintiff_bar["cases"][0]["case_public_id"] = hidden_ids.pop()

    with pytest.raises(ValueError, match="visible membership"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a5_zero_groups_requires_every_case_to_lack_a_safe_opponent() -> None:
    case = SanitizedArbitrationCaseV2(
        case_id="no-opponent",
        role="other",
        outcome="unknown",
        amount_state="available",
        amount=Decimal("1"),
        currency_state="rub",
        limitations=(
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
        ),
    )
    payload = _project(_basis(
        (case,),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
        ),
    )).model_dump(mode="json")
    payload["blocks"]["arbitration_a5"]["cases_without_safe_opponent"] = 0

    with pytest.raises(ValueError, match="A5 counters"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a5_multi_opponent_count_cannot_include_cases_without_opponents() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    payload["blocks"]["arbitration_a5"]["cases_without_safe_opponent"] = 2

    with pytest.raises(ValueError, match="A5 counters"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a5_nonempty_groups_require_a_case_with_a_safe_opponent() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    a5 = payload["blocks"]["arbitration_a5"]
    a5["cases_without_safe_opponent"] = 2
    a5["multi_opponent_case_count"] = 0

    with pytest.raises(ValueError, match="A5 counters"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a5_visible_duplicate_membership_requires_multi_case_counter() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    payload["blocks"]["arbitration_a5"]["multi_opponent_case_count"] = 0

    with pytest.raises(ValueError, match="A5 counters|visible memberships"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a5_single_group_count_matches_cases_with_safe_opponents() -> None:
    with_opponent = SanitizedArbitrationCaseV2(
        case_id="single-group-a",
        first_number="А40-1/2025",
        year=2025,
        role="plaintiff",
        outcome="unknown",
        amount_state="available",
        amount=Decimal("1"),
        currency_state="rub",
        opponent_tokens=(_token("a"),),
    )
    without_opponent = SanitizedArbitrationCaseV2(
        case_id="single-group-b",
        role="other",
        outcome="unknown",
        amount_state="available",
        amount=Decimal("2"),
        currency_state="rub",
        limitations=(
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
        ),
    )
    payload = _project(_basis(
        (with_opponent, without_opponent),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
        ),
    )).model_dump(mode="json")
    payload["blocks"]["arbitration_a5"]["cases_without_safe_opponent"] = 0

    with pytest.raises(ValueError, match="A5 counters"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def _redigest(payload: dict[str, object]) -> dict[str, object]:
    payload["projection_digest"] = canonical_digest({
        key: value for key, value in payload.items() if key != "projection_digest"
    })
    return payload


def _append_arbitration_limitation(
    payload: dict[str, object],
    *,
    code: str,
    root_block: str | None,
    coverage_blocks: tuple[str, ...],
) -> None:
    payload["limitations"].append({
        "code": code,
        "block_id": root_block,
        "field_id": None,
        "message": public_h2_models_module.ARBITRATION_PUBLIC_LIMITATION_MESSAGES[
            code
        ],
    })
    coverage_order = public_h2_models_module.COVERAGE_BLOCKS
    payload["limitations"].sort(key=lambda item: (
        coverage_order.index(item["block_id"])
        if item["block_id"] in coverage_order else 99,
        item["field_id"] or "",
        item["code"],
    ))
    precedence = public_h2_models_module._ARBITRATION_LIMITATION_PRECEDENCE
    for item in payload["coverage"][7:12]:
        if item["block_id"] in coverage_blocks:
            item["limitation_codes"].append(code)
            item["limitation_codes"].sort(key=precedence.index)


def _rewrite_count_bars(view: dict[str, object], counts: tuple[int, ...]) -> None:
    percentages = public_h2_module._arbitration_percentages(
        counts,
        sum(counts),
    )
    for bar, count, percent in zip(
        view["bars"], counts, percentages, strict=True,
    ):
        bar["count"] = count
        bar["percent_decimal"] = percent
        bar["scope"]["eligible_total"] = count
        bar["scope"]["shown"] = min(count, 20)
        bar["scope"]["label"] = f"показано {min(count, 20)} из {count} дел"


def _large_role_cases(
    *,
    second_role: str,
    plaintiff_outcome: str = "unknown",
    plaintiff_opponents: bool = False,
) -> tuple[SanitizedArbitrationCaseV2, ...]:
    cases: list[SanitizedArbitrationCaseV2] = []
    for index in range(42):
        role = "plaintiff" if index < 21 else second_role
        cases.append(SanitizedArbitrationCaseV2(
            case_id=f"aggregate-{index:02d}",
            first_number=f"А40-{index + 1}/2025",
            year=2025,
            role=role,  # type: ignore[arg-type]
            outcome=(
                plaintiff_outcome if role == "plaintiff" else "unknown"
            ),  # type: ignore[arg-type]
            amount_state="missing",
            currency_state="missing",
            opponent_tokens=(
                (_token("a"),)
                if role == "plaintiff" and plaintiff_opponents
                else ()
            ),
            limitations=(
                "arbitration_amount_missing",
                "arbitration_currency_missing",
            ),
        ))
    return tuple(cases)


def test_visible_date_inversion_requires_exact_limitation_evidence() -> None:
    case = SanitizedArbitrationCaseV2(
        case_id="inverted-private-case",
        first_number="А40-1/2025",
        year=2025,
        role="plaintiff",
        outcome="unknown",
        date_start=date(2025, 2, 1),
        date_update=date(2025, 1, 1),
        amount_state="available",
        amount=Decimal("1"),
        currency_state="rub",
        limitations=("arbitration_date_inversion",),
    )
    payload = _project(_basis(
        (case,),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_date_inversion",
        ),
    )).model_dump(mode="json")
    payload["limitations"] = [
        item
        for item in payload["limitations"]
        if item["code"] != "arbitration_date_inversion"
    ]
    for item in payload["coverage"][7:12]:
        item["limitation_codes"] = [
            code
            for code in item["limitation_codes"]
            if code != "arbitration_date_inversion"
        ]

    with pytest.raises(ValueError, match="date inversion is unexplained"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_visible_hidden_case_number_requires_exact_limitation_evidence() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    payload["limitations"] = [
        item
        for item in payload["limitations"]
        if item["code"] != "arbitration_first_number_unavailable"
    ]
    for item in payload["coverage"][7:12]:
        item["limitation_codes"] = [
            code
            for code in item["limitation_codes"]
            if code != "arbitration_first_number_unavailable"
        ]

    with pytest.raises(ValueError, match="hidden case number is unexplained"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_v3_rejects_arbitration_limitation_message_drift() -> None:
    payload = _project(_basis(())).model_dump(mode="json")
    limitation = next(
        item
        for item in payload["limitations"]
        if item["code"] == "arbitration_calendar_unverified"
    )
    limitation["message"] = "Произвольный публичный текст."

    with pytest.raises(ValueError, match="limitation message"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_v3_rejects_arbitration_root_limitation_order_drift() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    indices = [
        index
        for index, item in enumerate(payload["limitations"])
        if item["code"] in {
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
        }
    ]
    payload["limitations"][indices[0]], payload["limitations"][indices[1]] = (
        payload["limitations"][indices[1]],
        payload["limitations"][indices[0]],
    )

    with pytest.raises(ValueError, match="limitation order"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


@pytest.mark.parametrize("drift", ("order", "matrix"))
def test_v3_rejects_arbitration_coverage_limitation_drift(
    drift: str,
) -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    if drift == "order":
        payload["coverage"][7]["limitation_codes"].reverse()
    else:
        payload["coverage"][8]["limitation_codes"].insert(
            0,
            "arbitration_calendar_unverified",
        )

    with pytest.raises(ValueError, match="coverage linkage"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_v3_rejects_mutually_exclusive_storage_boundaries() -> None:
    payload = _project(_malformed_overflow_basis()).model_dump(mode="json")
    coverage_blocks = tuple(f"arbitration_a{index}" for index in range(1, 5))
    _append_arbitration_limitation(
        payload,
        code="oversized_case",
        root_block=None,
        coverage_blocks=coverage_blocks,
    )
    _append_arbitration_limitation(
        payload,
        code="storage_cap_exhausted",
        root_block=None,
        coverage_blocks=coverage_blocks,
    )

    with pytest.raises(ValueError, match="storage boundary limitations conflict"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_public_summary_row_classes_are_disjoint() -> None:
    payload = _project(_malformed_overflow_basis()).model_dump(mode="json")
    for block_id in (
        "arbitration_a1",
        "arbitration_a2",
        "arbitration_a3",
        "arbitration_a4",
    ):
        payload["blocks"][block_id]["summary"][
            "duplicate_identical_count"
        ] = 1

    with pytest.raises(ValueError, match="public counters"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_storage_boundary_row_is_part_of_public_classification_bound() -> None:
    payload = _project(_malformed_overflow_basis()).model_dump(mode="json")
    _append_arbitration_limitation(
        payload,
        code="oversized_case",
        root_block=None,
        coverage_blocks=tuple(
            f"arbitration_a{index}" for index in range(1, 5)
        ),
    )

    with pytest.raises(ValueError, match="row classification"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_public_row_classification_forbids_unclassified_surplus() -> None:
    payload = _project(_malformed_overflow_basis()).model_dump(mode="json")
    for block_id in (
        "arbitration_a1",
        "arbitration_a2",
        "arbitration_a3",
        "arbitration_a4",
    ):
        summary = payload["blocks"][block_id]["summary"]
        summary["malformed_count"] = 0
        summary["completion_reason"] = "opponent_group_cap_exhausted"
    payload["limitations"] = [
        item
        for item in payload["limitations"]
        if item["code"] != "malformed_rows"
    ]
    for item in payload["coverage"][7:11]:
        item["limitation_codes"] = [
            code
            for code in item["limitation_codes"]
            if code != "malformed_rows"
        ]

    with pytest.raises(ValueError, match="row classification"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a4_limitation_states_require_enough_excluded_cases() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    for code in (
        "arbitration_currency_unidentified",
        "arbitration_currency_invalid",
    ):
        _append_arbitration_limitation(
            payload,
            code=code,
            root_block="arbitration_a4",
            coverage_blocks=("arbitration_a4",),
        )

    with pytest.raises(ValueError, match="A4 limitation population"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a1_and_a2_role_aggregates_reconcile_when_a1_is_complete() -> None:
    payload = _project(_basis(
        _large_role_cases(second_role="respondent"),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    _rewrite_count_bars(
        payload["blocks"]["arbitration_a2"],
        (22, 20, 0, 0),
    )

    with pytest.raises(ValueError, match="A1 and A2 role totals"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_nonparty_roles_require_enough_unknown_outcomes() -> None:
    payload = _project(_basis(
        _large_role_cases(
            second_role="other",
            plaintiff_outcome="won",
        ),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    _rewrite_count_bars(
        payload["blocks"]["arbitration_a3"],
        (22, 0, 0, 20),
    )

    with pytest.raises(ValueError, match="role and outcome totals"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_nonparty_roles_require_enough_cases_without_safe_opponents() -> None:
    payload = _project(_basis(
        _large_role_cases(
            second_role="other",
            plaintiff_outcome="won",
            plaintiff_opponents=True,
        ),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    a5 = payload["blocks"]["arbitration_a5"]
    a5["cases_without_safe_opponent"] = 20
    group = a5["groups"][0]
    group["case_count"] = 22
    group["case_scope"]["eligible_total"] = 22
    group["case_scope"]["label"] = "показано 20 из 22 дел"

    with pytest.raises(ValueError, match="A5 counters"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a5_visible_group_case_must_have_an_opponent_eligible_role() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    payload["blocks"]["arbitration_a5"]["groups"][0]["cases"][0][
        "role"
    ] = "other"

    with pytest.raises(ValueError, match="opponent is not fully masked"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a5_group_count_cannot_exceed_cases_with_safe_opponents() -> None:
    tokens = tuple(
        PrivateOpponentTokenV2(
            key_id="active_2026",
            value=f"{index + 1:064x}",
        )
        for index in range(21)
    )
    cases = tuple(
        SanitizedArbitrationCaseV2(
            case_id=f"group-bound-{index:02d}",
            first_number=f"А40-{index + 1}/2025",
            year=2025,
            role="plaintiff" if index < 21 else "other",
            outcome="unknown",
            amount_state="missing",
            currency_state="missing",
            opponent_tokens=tokens if index < 21 else (),
            limitations=(
                "arbitration_amount_missing",
                "arbitration_currency_missing",
            ),
        )
        for index in range(42)
    )
    payload = _project(_basis(
        cases,
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    group = payload["blocks"]["arbitration_a5"]["groups"][0]
    group["case_count"] = 22
    group["case_scope"]["eligible_total"] = 22
    group["case_scope"]["label"] = "показано 20 из 22 дел"

    with pytest.raises(ValueError, match="opponent is not fully masked"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_a5_truncated_groups_obey_visible_incidence_upper_bound() -> None:
    tokens = tuple(
        PrivateOpponentTokenV2(
            key_id="active_2026",
            value=f"{index + 1:064x}",
        )
        for index in range(21)
    )
    cases = tuple(
        SanitizedArbitrationCaseV2(
            case_id=f"incidence-bound-{index:02d}",
            first_number=f"А40-{index + 1}/2025",
            year=2025,
            role="plaintiff" if index < 21 else "other",
            outcome="unknown",
            amount_state="missing",
            currency_state="missing",
            opponent_tokens=tokens if index < 21 else (),
            limitations=(
                "arbitration_amount_missing",
                "arbitration_currency_missing",
            ),
        )
        for index in range(42)
    )
    payload = _project(_basis(
        cases,
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    payload["blocks"]["arbitration_a5"]["multi_opponent_case_count"] = 20

    with pytest.raises(ValueError, match="A5 counters"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def _empty_basis(reason: str) -> ArbitrationBasisV2:
    if reason in {"provider_error", "provider_binding_invalid"}:
        return empty_arbitration_basis_v2(
            reason,
            pages_requested=1,
            mask_key_id="active_2026",
        )
    return empty_arbitration_basis_v2(reason)


def _complete_cases() -> tuple[SanitizedArbitrationCaseV2, ...]:
    return (
        SanitizedArbitrationCaseV2(
            case_id="private-a",
            role="respondent",
            outcome="returned",
            amount_state="missing",
            currency_state="missing",
            opponent_tokens=(_token("a"), _token("b")),
            limitations=(
                "arbitration_unknown_year",
                "arbitration_first_number_unavailable",
                "arbitration_amount_missing",
                "arbitration_currency_missing",
            ),
        ),
        SanitizedArbitrationCaseV2(
            case_id="private-z",
            first_number="А40-123/2025",
            year=2025,
            role="plaintiff",
            outcome="won",
            date_start=date(2025, 1, 2),
            date_update=date(2025, 1, 5),
            duration_days=3,
            amount_state="available",
            amount=Decimal("-12.3400"),
            currency_state="rub",
            opponent_tokens=(_token("b"),),
        ),
    )


def _overflow_basis() -> ArbitrationBasisV2:
    case = SanitizedArbitrationCaseV2(
        case_id="overflow-private-case",
        first_number="А40-1/2025",
        year=2025,
        role="plaintiff",
        outcome="unknown",
        amount_state="available",
        amount=Decimal("1"),
        currency_state="rub",
    )
    return _basis(
        (case,),
        completion_reasons=("opponent_group_cap_exhausted",),
        limitation_codes=(
            "opponent_group_cap_exhausted",
            "arbitration_calendar_unverified",
        ),
        opponent_probe_count=20_001,
    )


def _malformed_overflow_basis() -> ArbitrationBasisV2:
    payload = _overflow_basis().model_dump(mode="json")
    payload["source_total"] = 2
    payload["page_manifest"][0].update({
        "returned_count": 2,
        "accepted_count": 1,
    })
    payload["counters"].update({
        "rows_observed": 2,
        "rows_processed": 2,
        "rows_shape_valid": 1,
        "malformed_count": 1,
    })
    payload["completion_reasons"] = [
        "malformed_rows",
        "opponent_group_cap_exhausted",
    ]
    payload["limitations"] = [
        {"code": "malformed_rows"},
        {"code": "opponent_group_cap_exhausted"},
        {"code": "arbitration_calendar_unverified"},
    ]
    return ArbitrationBasisV2.model_validate(payload)


def test_a5_overflow_allows_an_earlier_primary_completion_reason() -> None:
    dto = _project(_malformed_overflow_basis())

    assert dto.blocks.arbitration_a1.summary.completion_reason == "malformed_rows"
    assert dto.blocks.arbitration_a5 is None
    a5_coverage = next(
        item for item in dto.coverage if item.block_id == "arbitration_a5"
    )
    assert a5_coverage.limitation_codes == (
        "opponent_group_cap_exhausted",
    )


def test_public_summary_requires_earliest_emitted_completion_reason() -> None:
    payload = _project(_malformed_overflow_basis()).model_dump(mode="json")
    for block_id in (
        "arbitration_a1",
        "arbitration_a2",
        "arbitration_a3",
        "arbitration_a4",
    ):
        payload["blocks"][block_id]["summary"]["completion_reason"] = (
            "opponent_group_cap_exhausted"
        )

    with pytest.raises(ValueError, match="completion precedence"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def _worst_case_basis() -> ArbitrationBasisV2:
    tokens = tuple(
        PrivateOpponentTokenV2(
            key_id="active_2026",
            value=f"{index:064x}",
        )
        for index in range(1, 21)
    )
    roles = ("plaintiff", "respondent", "other", "unattributed")
    outcomes = ("won", "lost", "returned", "unknown")
    years: tuple[int | None, ...] = (*range(2016, 2026), None)
    cases: list[SanitizedArbitrationCaseV2] = []
    ordinal = 0
    for year in years:
        for role in roles:
            for role_index in range(20):
                ordinal += 1
                start = date(year, 1, 1) if year is not None else None
                update = date(year, 12, 31) if year is not None else None
                cases.append(SanitizedArbitrationCaseV2(
                    case_id=f"worst-case-{ordinal:04d}",
                    first_number=f"А123-{ordinal:012d}/{year or 2026}",
                    year=year,
                    role=role,  # type: ignore[arg-type]
                    outcome=(
                        outcomes[role_index % len(outcomes)]
                        if role in {"plaintiff", "respondent"}
                        else "unknown"
                    ),  # type: ignore[arg-type]
                    date_start=start,
                    date_update=update,
                    duration_days=(update - start).days if start is not None and update is not None else None,
                    amount_state="available",
                    amount=Decimal(f"{ordinal}123456789.123456"),
                    currency_state="rub",
                    opponent_tokens=tokens if role in {"plaintiff", "respondent"} else (),
                    limitations=("arbitration_unknown_year",) if year is None else (),
                ))
    return _basis(
        tuple(sorted(cases, key=lambda item: item.case_id)),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
        ),
    )


def _cap_fallback_payload() -> dict[str, object]:
    dto = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    ))
    payload = dto.model_dump(mode="json")
    for index in range(1, 6):
        payload["blocks"][f"arbitration_a{index}"] = None
    for item in payload["coverage"][7:12]:
        item["state"] = "failed"
        item["limitation_codes"] = ["arbitration_public_projection_cap_exhausted"]
    arbitration_codes = {
        "arbitration_calendar_unverified",
        "arbitration_unknown_year",
        "arbitration_first_number_unavailable",
        "arbitration_amount_missing",
        "arbitration_currency_missing",
    }
    payload["limitations"] = [
        item for item in payload["limitations"] if item["code"] not in arbitration_codes
    ]
    payload["limitations"].append({
        "code": "arbitration_public_projection_cap_exhausted",
        "block_id": None,
        "field_id": None,
        "message": "Арбитражные представления не опубликованы из-за предельного размера ответа.",
    })
    return _redigest(payload)


def test_v3_projection_emits_exact_masked_a1_to_a5_and_bound_source() -> None:
    basis = _basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )

    dto = _project(basis)

    assert dto.sources[-1].model_dump(mode="json") == {
        "dataset": "arbitration",
        "received_at": "2026-08-27T01:02:03.123456Z",
        "effective_at": None,
        "period": None,
        "normalization_version": "company_card_arbitration_normalization_v2",
        "evidence_version": "datanewton_arbitration_registry_v2",
    }
    assert dto.blocks.arbitration_a1 is not None
    assert tuple(bucket.year for bucket in dto.blocks.arbitration_a1.buckets) == (2025, None)
    assert dto.blocks.arbitration_a2 is not None
    assert tuple(bar.category_id for bar in dto.blocks.arbitration_a2.bars) == (
        "plaintiff", "respondent", "other", "unattributed"
    )
    assert tuple(bar.percent_decimal for bar in dto.blocks.arbitration_a2.bars) == (
        "50", "50", "0", "0"
    )
    assert dto.blocks.arbitration_a4 is not None
    group = dto.blocks.arbitration_a4.currency_groups[0]
    assert group.axis.axis_min_decimal == "-12.34"
    assert group.axis.axis_max_decimal == "0"
    assert group.cases[0].amount is not None
    assert group.cases[0].amount.display_exact == "−12,34 ₽"
    assert dto.blocks.arbitration_a5 is not None
    assert [item.opponent_public_id for item in dto.blocks.arbitration_a5.groups] == [
        "opponent_000002", "opponent_000001"
    ]
    assert [item.display_name for item in dto.blocks.arbitration_a5.groups] == [
        "Сторона скрыта 2", "Сторона скрыта 1"
    ]
    raw = canonical_json_bytes(dto.model_dump(mode="json"))
    for private in (b"private-a", b"private-z", b"a" * 64, b"b" * 64, b"active_2026"):
        assert private not in raw


def test_projected_case_id_breaks_common_and_a4_raw_key_ties() -> None:
    common = {
        "year": 2025,
        "role": "plaintiff",
        "outcome": "won",
        "date_start": date(2025, 1, 1),
        "date_update": date(2025, 1, 2),
        "duration_days": 1,
        "amount_state": "available",
        "amount": Decimal("10"),
        "currency_state": "rub",
    }
    # Domain persistence is raw-key ordered: the quote precedes ``A``. The
    # frozen CJSON public-order identity deliberately assigns the reverse
    # public ordinals, so a raw-key tie-break would emit 000002 before 000001.
    cases = (
        SanitizedArbitrationCaseV2(
            case_id='"',
            first_number="А40-2/2025",
            **common,
        ),
        SanitizedArbitrationCaseV2(
            case_id="A",
            first_number="А40-1/2025",
            **common,
        ),
    )

    dto = _project(_basis(
        cases,
        limitation_codes=("arbitration_calendar_unverified",),
    ))

    a1_cases = dto.blocks.arbitration_a1.buckets[0].role_details[0].cases
    a2_cases = dto.blocks.arbitration_a2.bars[0].cases
    a3_cases = dto.blocks.arbitration_a3.bars[0].cases
    a4_cases = dto.blocks.arbitration_a4.currency_groups[0].cases
    for details in (a1_cases, a2_cases, a3_cases, a4_cases):
        assert tuple(item.case_public_id for item in details) == (
            "case_000001",
            "case_000002",
        )
        assert tuple(item.case_number for item in details) == (
            "А40-1/2025",
            "А40-2/2025",
        )


def test_exact_complete_zero_is_five_non_null_available_empty_views() -> None:
    dto = _project(_basis(()))

    for index in range(1, 6):
        block_id = f"arbitration_a{index}"
        assert getattr(dto.blocks, block_id) is not None
        coverage = next(item for item in dto.coverage if item.block_id == block_id)
        assert (coverage.state, coverage.total, coverage.returned, coverage.eligible) == (
            "available_empty", 0, 0, 0
        )


@pytest.mark.parametrize(
    ("reason", "state"),
    tuple((reason, state) for reason, state in {
        "operation_gate_closed": "gate_closed",
        "evidence_gate_closed": "gate_closed",
        "privacy_key_unavailable": "failed",
        "provider_error": "failed",
        "provider_binding_invalid": "failed",
    }.items()),
)
def test_source_less_v3_has_one_exact_reason_and_no_arbitration_source(
    reason: str,
    state: str,
) -> None:
    dto = _project(_empty_basis(reason))

    assert tuple(item.dataset for item in dto.sources) == ("counterparty", "finance")
    assert all(getattr(dto.blocks, block) is None for block in (
        "arbitration_a1", "arbitration_a2", "arbitration_a3", "arbitration_a4", "arbitration_a5"
    ))
    items = tuple(item for item in dto.coverage if item.block_id.startswith("arbitration_"))
    assert all(
        item.state == state
        and item.population_scope == "not_applicable"
        and item.total is None
        and item.returned is None
        and item.eligible is None
        and item.limitation_codes == (reason,)
        for item in items
    )
    limitation = next(item for item in dto.limitations if item.code == reason)
    assert limitation.block_id is None and limitation.field_id is None


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload["coverage"][7].update({"total": 0}),
        lambda payload: payload["coverage"][8].update({"state": "gate_closed"}),
        lambda payload: payload["limitations"][-1].update({"block_id": "arbitration_a1"}),
        lambda payload: payload["sources"].append({
            "dataset": "arbitration",
            "received_at": "2026-08-27T01:00:00Z",
            "effective_at": None,
            "period": None,
            "normalization_version": "company_card_v2_v1",
            "evidence_version": "evidence_registry_v1",
        }),
    ),
)
def test_source_less_v3_one_field_mutations_fail_closed(mutation) -> None:
    payload = _project(_empty_basis("provider_error")).model_dump(mode="json")
    mutation(payload)
    payload["projection_digest"] = canonical_digest({
        key: value for key, value in payload.items() if key != "projection_digest"
    })

    with pytest.raises(ValueError):
        CompanyPublicH2Response.model_validate(payload)


def test_bound_lexical_failure_keeps_exact_source_but_no_facts() -> None:
    basis = empty_arbitration_basis_v2(
        "lexical_transport_invalid",
        pages_requested=1,
        mask_key_id="active_2026",
        provider_received_at=RECEIVED_AT,
    )
    dto = _project(basis)

    assert dto.sources[-1].dataset == "arbitration"
    assert all(getattr(dto.blocks, f"arbitration_a{index}") is None for index in range(1, 6))
    assert all(
        item.state == "failed" and item.limitation_codes == ("lexical_transport_invalid",)
        for item in dto.coverage[7:12]
    )


def test_bound_v3_source_requires_report3_card_v2_discriminator() -> None:
    payload = _cap_fallback_payload()
    payload.update({
        "report_version": "2",
        "snapshot_capability": "legacy_read_only",
        "indexable": False,
    })

    with pytest.raises(ValueError, match="branch discriminator"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


@pytest.mark.parametrize("report_version", ("1", "2"))
@pytest.mark.parametrize(
    ("field", "marker"),
    (
        (
            "normalization_version",
            "company_card_arbitration_normalization_v2",
        ),
        ("evidence_version", "datanewton_arbitration_registry_v2"),
    ),
)
def test_legacy_lineage_rejects_each_policy_v3_source_marker(
    report_version: str,
    field: str,
    marker: str,
) -> None:
    root = Path(__file__).parents[3]
    payload = json.loads(
        (root / "shared/fixtures/company_public_h2_contract_v1.json").read_text(
            encoding="utf-8",
        )
    )
    payload.update({
        "report_version": report_version,
        "snapshot_capability": "legacy_read_only",
        "indexable": False,
    })
    payload["sources"][2][field] = marker

    with pytest.raises(ValueError, match="branch discriminator"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_source_less_projection_cap_is_direct_failure_at_plus_one() -> None:
    dto = _project(_empty_basis("provider_error"))
    payload = dto.model_dump(mode="json")
    payload.pop("projection_digest")
    base = deepcopy(payload)
    base["checked_date_display"] = ""
    base_size = len(canonical_json_bytes({
        **base,
        "projection_digest": canonical_digest(base),
    }))
    exact = deepcopy(base)
    exact["checked_date_display"] = "x" * (524_288 - base_size)
    plus_one = deepcopy(exact)
    plus_one["checked_date_display"] += "x"

    assert len(canonical_json_bytes(_finalize_public_h2_payload(
        exact, bound_arbitration=False
    ).model_dump(mode="json"))) == 524_288
    with pytest.raises(ValueError, match="public_projection_too_large"):
        _finalize_public_h2_payload(plus_one, bound_arbitration=False)


@pytest.mark.parametrize("source_total", (1, 3))
def test_complete_v3_rejects_source_total_drift(source_total: int) -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    for index in range(1, 6):
        payload["blocks"][f"arbitration_a{index}"]["summary"]["source_total"] = source_total
        payload["coverage"][6 + index]["total"] = source_total

    with pytest.raises(ValueError, match="source population"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("rows_observed", 1_001),
        ("source_total", 1 << 63),
    ),
)
def test_v3_summary_rejects_wire_counter_bounds(field: str, value: int) -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    payload["blocks"]["arbitration_a1"]["summary"][field] = value

    with pytest.raises(ValueError):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_v3_rejects_observed_bounds_without_known_population() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    for index in range(1, 6):
        summary = payload["blocks"][f"arbitration_a{index}"]["summary"]
        summary["observed_start_year"] = None
        summary["observed_end_year"] = None

    with pytest.raises(ValueError, match="observed bounds"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_complete_v3_rejects_nonconserving_rejection_counters() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    for index in range(1, 6):
        payload["blocks"][f"arbitration_a{index}"]["summary"]["malformed_count"] = 1

    with pytest.raises(ValueError, match="policy-v3 public counters"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_complete_zero_v3_rejects_an_observed_a1_bucket() -> None:
    zero = _project(_basis(())).model_dump(mode="json")
    populated = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    bucket = deepcopy(populated["blocks"]["arbitration_a1"]["buckets"][0])
    bucket.update({
        "plaintiff_count": 0,
        "respondent_count": 0,
        "other_count": 0,
        "unattributed_count": 0,
        "total_count": 0,
    })
    for detail in bucket["role_details"]:
        detail["scope"].update({
            "source_total": 0,
            "rows_received": 0,
            "eligible_total": 0,
            "shown": 0,
            "label": "показано 0 из 0 дел",
        })
        detail["cases"] = []
    zero["blocks"]["arbitration_a1"]["buckets"] = [bucket]
    zero["blocks"]["arbitration_a1"]["displayed_start_year"] = bucket["year"]
    zero["blocks"]["arbitration_a1"]["displayed_end_year"] = bucket["year"]

    with pytest.raises(ValueError):
        CompanyPublicH2Response.model_validate(_redigest(zero))


def test_v3_rejects_a5_group_larger_than_unique_population() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    group = payload["blocks"]["arbitration_a5"]["groups"][0]
    third = deepcopy(group["cases"][0])
    third["case_public_id"] = "case_000003"
    group["case_count"] = 3
    group["case_scope"].update({
        "eligible_total": 3,
        "shown": 3,
        "label": "показано 3 из 3 дел",
    })
    group["cases"].append(third)

    with pytest.raises(ValueError, match="fully masked"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_v3_overflow_rejects_unemitted_earlier_completion_reason() -> None:
    dto = _project(_overflow_basis())
    assert dto.blocks.arbitration_a5 is None
    assert all(
        getattr(dto.blocks, f"arbitration_a{index}") is not None
        for index in range(1, 5)
    )
    overflow_coverage = dto.coverage[11]
    assert (
        overflow_coverage.state,
        overflow_coverage.population_scope,
        overflow_coverage.total,
        overflow_coverage.returned,
        overflow_coverage.eligible,
        overflow_coverage.limitation_codes,
    ) == (
        "failed",
        "returned_slice",
        1,
        1,
        None,
        ("opponent_group_cap_exhausted",),
    )
    assert b"20001" not in canonical_json_bytes(dto.model_dump(mode="json"))
    payload = dto.model_dump(mode="json")
    for index in range(1, 5):
        payload["blocks"][f"arbitration_a{index}"]["summary"]["completion_reason"] = "malformed_rows"

    with pytest.raises(ValueError, match="completion precedence"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_v3_overflow_binds_a5_common_evidence() -> None:
    payload = _project(_overflow_basis()).model_dump(mode="json")
    payload["coverage"][11]["total"] = 0

    with pytest.raises(ValueError, match="A5 overflow evidence"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


@pytest.mark.parametrize("field", ("block_id", "field_id"))
def test_bound_failure_requires_root_limitation_linkage(field: str) -> None:
    basis = empty_arbitration_basis_v2(
        "lexical_transport_invalid",
        pages_requested=1,
        mask_key_id="active_2026",
        provider_received_at=RECEIVED_AT,
    )
    payload = _project(basis).model_dump(mode="json")
    limitation = next(
        item for item in payload["limitations"]
        if item["code"] == "lexical_transport_invalid"
    )
    limitation[field] = "arbitration_a1"

    with pytest.raises(ValueError, match="failed limitation"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


@pytest.mark.parametrize("field", ("block_id", "field_id"))
def test_projection_cap_requires_root_limitation_linkage(field: str) -> None:
    payload = _cap_fallback_payload()
    limitation = next(
        item for item in payload["limitations"]
        if item["code"] == "arbitration_public_projection_cap_exhausted"
    )
    limitation[field] = "arbitration_a1"

    with pytest.raises(ValueError, match="projection-cap limitation"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_projection_cap_requires_nonnull_returned_collection_evidence() -> None:
    payload = _cap_fallback_payload()
    for item in payload["coverage"][7:12]:
        item["returned"] = None

    with pytest.raises(ValueError, match="projection-cap evidence"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("returned", 1_001, "projection-cap evidence"),
        ("total", 1 << 63, "projection-cap evidence"),
        ("eligible", 1_001, "A1-A3 counts"),
    ),
)
def test_projection_cap_bounds_common_arbitration_evidence(
    field: str,
    value: int,
    message: str,
) -> None:
    payload = _cap_fallback_payload()
    targets = payload["coverage"][7:12]
    if field == "eligible":
        targets = targets[:3]
    for item in targets:
        item[field] = value

    with pytest.raises(ValueError, match=message):
        CompanyPublicH2Response.model_validate(_redigest(payload))


@pytest.mark.parametrize(
    ("population_scope", "total", "returned", "eligible", "message"),
    (
        ("returned_slice", None, 2, 2, "projection-cap evidence"),
        ("returned_slice", 1, 2, 2, "projection-cap evidence"),
        ("complete_collection", 3, 2, 2, "projection-cap evidence"),
        ("returned_slice", 3, 2, 3, "projection-cap evidence"),
    ),
)
def test_projection_cap_preserves_exact_candidate_population_relations(
    population_scope: str,
    total: int | None,
    returned: int,
    eligible: int,
    message: str,
) -> None:
    payload = _cap_fallback_payload()
    for item in payload["coverage"][7:12]:
        item["population_scope"] = population_scope
        item["total"] = total
        item["returned"] = returned
    for item in payload["coverage"][7:10]:
        item["eligible"] = eligible

    with pytest.raises(ValueError, match=message):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_projection_cap_rejects_a5_candidate_above_registry_cap() -> None:
    payload = _cap_fallback_payload()
    payload["coverage"][11]["eligible"] = 20_001

    with pytest.raises(ValueError, match="A5 count"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_projection_cap_rejects_opponent_groups_for_zero_case_population() -> None:
    payload = _cap_fallback_payload()
    for item in payload["coverage"][7:10]:
        item["eligible"] = 0
    payload["coverage"][10]["eligible"] = 0
    payload["coverage"][11]["eligible"] = 1

    with pytest.raises(ValueError, match="A5 count"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_nonnull_a5_rejects_eligible_total_above_registry_cap() -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    a5 = payload["blocks"]["arbitration_a5"]
    a5["scope"]["eligible_total"] = 20_001
    a5["scope"]["shown"] = 20
    a5["scope"]["label"] = "показано 20 из 20001 сторон"
    payload["coverage"][11]["eligible"] = 20_001

    with pytest.raises(ValueError, match="registry cap"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_bound_v3_rejects_unknown_arbitration_linked_limitation() -> None:
    payload = _cap_fallback_payload()
    payload["limitations"].append({
        "code": "future_arbitration_note",
        "block_id": "arbitration_a1",
        "field_id": None,
        "message": "Недопустимое расширение закрытого контракта.",
    })

    with pytest.raises(ValueError, match="unknown policy-v3 arbitration limitation"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_bound_v3_rejects_non_v3_coverage_limitation_code() -> None:
    payload = _cap_fallback_payload()
    payload["coverage"][7]["limitation_codes"] = ["requisites_partial"]

    with pytest.raises(ValueError, match="unknown policy-v3 arbitration limitation"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


@pytest.mark.parametrize(
    "code",
    (
        "arbitration_calendar_unverified",
        "arbitration_unknown_year",
        "arbitration_amount_missing",
        "arbitration_currency_missing",
    ),
)
def test_bound_v3_requires_each_inferable_limitation(code: str) -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    payload["limitations"] = [
        item for item in payload["limitations"] if item["code"] != code
    ]
    for item in payload["coverage"][7:12]:
        item["limitation_codes"] = [
            value for value in item["limitation_codes"] if value != code
        ]

    with pytest.raises(ValueError, match="inferred limitation semantics"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


@pytest.mark.parametrize(
    ("code", "invalid_block"),
    (
        ("arbitration_calendar_unverified", None),
        ("arbitration_amount_missing", "arbitration_a1"),
    ),
)
def test_admitted_v3_rejects_limitation_linkage_drift(
    code: str,
    invalid_block: str | None,
) -> None:
    payload = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    )).model_dump(mode="json")
    limitation = next(item for item in payload["limitations"] if item["code"] == code)
    limitation["block_id"] = invalid_block

    with pytest.raises(ValueError, match="limitation linkage"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_complete_projection_cap_rejects_nullable_a5_eligible_count() -> None:
    payload = _cap_fallback_payload()
    payload["coverage"][11]["eligible"] = None

    with pytest.raises(ValueError, match="A5 count"):
        CompanyPublicH2Response.model_validate(_redigest(payload))


def test_bound_projection_cap_allows_exact_and_falls_back_at_plus_one() -> None:
    dto = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    ))
    payload = dto.model_dump(mode="json")
    payload.pop("projection_digest")
    base = deepcopy(payload)
    base["checked_date_display"] = ""
    base_size = len(canonical_json_bytes({
        **base,
        "projection_digest": canonical_digest(base),
    }))
    exact = deepcopy(base)
    exact["checked_date_display"] = "x" * (524_288 - base_size)
    plus_one = deepcopy(exact)
    plus_one["checked_date_display"] += "x"

    admitted = _finalize_public_h2_payload(exact, bound_arbitration=True)
    fallback = _finalize_public_h2_payload(plus_one, bound_arbitration=True)

    assert len(canonical_json_bytes(admitted.model_dump(mode="json"))) == 524_288
    assert all(
        getattr(admitted.blocks, f"arbitration_a{index}") is not None
        for index in range(1, 6)
    )
    assert len(canonical_json_bytes(fallback.model_dump(mode="json"))) < 524_288
    assert all(
        getattr(fallback.blocks, f"arbitration_a{index}") is None
        for index in range(1, 6)
    )
    assert all(
        item.state == "failed"
        and item.limitation_codes
        == ("arbitration_public_projection_cap_exhausted",)
        for item in fallback.coverage[7:12]
    )


def test_oversized_bound_candidate_cannot_launder_invalid_public_identity() -> None:
    dto = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    ))
    payload = dto.model_dump(mode="json")
    payload.pop("projection_digest")
    payload["checked_date_display"] = "x" * 524_288
    payload["blocks"]["arbitration_a5"]["groups"][0]["opponent_public_id"] = (
        "opponent_000000"
    )

    with pytest.raises(ValueError, match="public ordinal"):
        _finalize_public_h2_payload(payload, bound_arbitration=True)


def test_bound_1460_detail_candidate_uses_atomic_whole_response_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    basis = _worst_case_basis()
    snapshot = _snapshot(basis)
    basis_hash_before = canonical_digest(basis.model_dump(mode="json"))
    facts_hash_before = snapshot.arbitration_chart_facts_hash
    captured: dict[str, object] = {}
    original = public_h2_module._finalize_public_h2_payload

    def capture(
        payload: dict[str, object],
        *,
        bound_arbitration: bool,
    ) -> CompanyPublicH2Response:
        captured["payload"] = deepcopy(payload)
        return original(payload, bound_arbitration=bound_arbitration)

    monkeypatch.setattr(public_h2_module, "_finalize_public_h2_payload", capture)
    response = build_public_h2(
        snapshot,
        narrative_binding=_Narrative(),
        finance_enabled=True,
        arbitration_enabled=True,
    )

    candidate_payload = captured["payload"]
    candidate = CompanyPublicH2Response.model_validate(
        {
            **candidate_payload,
            "projection_digest": canonical_digest(candidate_payload),
        },
        context={"skip_public_h2_size_cap": True},
    )
    a1 = candidate.blocks.arbitration_a1
    a2 = candidate.blocks.arbitration_a2
    a3 = candidate.blocks.arbitration_a3
    a4 = candidate.blocks.arbitration_a4
    a5 = candidate.blocks.arbitration_a5
    assert all(value is not None for value in (a1, a2, a3, a4, a5))
    detail_count = (
        sum(
            len(detail.cases)
            for bucket in a1.buckets
            for detail in bucket.role_details
        )
        + sum(len(bar.cases) for bar in a2.bars)
        + sum(len(bar.cases) for bar in a3.bars)
        + sum(len(group.cases) for group in a4.currency_groups)
        + sum(len(group.cases) for group in a5.groups)
    )
    assert detail_count == 1_460
    assert len(canonical_json_bytes(candidate.model_dump(mode="json"))) > 524_288
    assert len(canonical_json_bytes(response.model_dump(mode="json"))) <= 524_288
    assert all(
        getattr(response.blocks, f"arbitration_a{index}") is None
        for index in range(1, 6)
    )
    candidate_coverage = candidate.coverage[7:12]
    fallback_coverage = response.coverage[7:12]
    assert tuple(
        (item.population_scope, item.total, item.returned, item.eligible)
        for item in fallback_coverage
    ) == tuple(
        (item.population_scope, item.total, item.returned, item.eligible)
        for item in candidate_coverage
    )
    assert all(
        item.state == "failed"
        and item.limitation_codes
        == ("arbitration_public_projection_cap_exhausted",)
        for item in fallback_coverage
    )
    assert canonical_digest(basis.model_dump(mode="json")) == basis_hash_before
    assert snapshot.arbitration_chart_facts_hash == facts_hash_before
    assert response.projection_digest == canonical_digest({
        key: value
        for key, value in response.model_dump(mode="json").items()
        if key != "projection_digest"
    })


def test_v3_ssr_emits_five_factual_articles_with_masked_details() -> None:
    dto = _project(_basis(
        _complete_cases(),
        limitation_codes=(
            "arbitration_calendar_unverified",
            "arbitration_unknown_year",
            "arbitration_first_number_unavailable",
            "arbitration_amount_missing",
            "arbitration_currency_missing",
        ),
    ))

    html = render_public_h2_body(dto)

    assert html.count("data-h2-arbitration-article=") == 5
    assert tuple(
        html.index(f'id="arbitration-a{index}"') for index in range(1, 6)
    ) == tuple(sorted(
        html.index(f'id="arbitration-a{index}"') for index in range(1, 6)
    ))
    for title in (
        "Арбитражная активность по годам",
        "Роли компании в делах",
        "Исходы дел",
        "Цена исков в рублях",
        "Противоположные стороны",
    ):
        assert f"<h3>{title}</h3>" in html
    for index in range(1, 6):
        assert f'data-h2-arbitration-coverage="arbitration_a{index}"' in html
        assert f'data-h2-arbitration-enhancement="arbitration-a{index}"' in html
        assert (
            f'aria-label="Ограничения арбитражного представления arbitration_a{index}"'
            in html
        )
    assert "Количество дел по наблюдаемым годам и роли компании" in html
    assert "Распределение дел по роли компании" in html
    assert "Распределение дел по подтверждённому исходу" in html
    assert "Цена иска в рублях по делам" in html
    assert "Скрытые противоположные стороны по количеству дел" in html
    assert 'data-h2-case-public-id="case_000001"' in html
    assert 'data-h2-opponent-public-id="opponent_000001"' in html
    assert "Сторона скрыта 1" in html
    assert "Одно дело может относиться к нескольким скрытым сторонам" in html
    assert 'href="#limitation-arbitration_calendar_unverified"' in html
    for private in ("private-a", "private-z", "a" * 64, "b" * 64, "active_2026"):
        assert private not in html


def test_source_less_v3_ssr_keeps_five_honest_unavailable_articles() -> None:
    html = render_public_h2_body(_project(_empty_basis("provider_error")))

    assert html.count("data-h2-arbitration-article=") == 5
    assert html.count(
        "Подтверждённые арбитражные данные для этого представления не опубликованы."
    ) == 5
    assert html.count('data-h2-arbitration-limitation="provider_error"') == 5
    assert html.count('href="#limitation-provider_error"') >= 5
    assert "Подтверждённая коллекция не содержит дел." not in html


def test_shared_masked_v3_contract_and_ssr_goldens_are_byte_exact() -> None:
    root = Path(__file__).parents[3]
    dto_path = (
        root
        / "shared/fixtures/company_public_h2_contract_v1_arbitration_masked_v3.json"
    )
    metadata_path = (
        root / "shared/fixtures/company_public_h2_ssr_v1_arbitration_v3.json"
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    dto_raw = dto_path.read_bytes()
    dto = CompanyPublicH2Response.model_validate(json.loads(dto_raw))

    assert metadata["profile"] == "finance_arbitration_masked_v3"
    assert metadata["dto_fixture"] == (
        "shared/fixtures/company_public_h2_contract_v1_arbitration_masked_v3.json"
    )
    assert all(
        getattr(dto.blocks, f"arbitration_a{index}") is not None
        for index in range(1, 6)
    )
    assert dto.blocks.arbitration_a5.groups[0].display_kind == "masked_unknown"
    assert b"private-a" not in dto_raw
    assert b"private-z" not in dto_raw
    assert b"active_2026" not in dto_raw
    assert b"a" * 64 not in dto_raw
    assert b"b" * 64 not in dto_raw

    manifest_raw = (
        root
        / "services/product_api/src/product_api/company_reports/company_card_v2/public_h2_asset_manifest.json"
    ).read_bytes().replace(b"\r\n", b"\n")
    manifest = validate_public_h2_asset_manifest(manifest_raw)
    html = render_public_h2_document(
        dto,
        manifest,
        metadata["nonce"],
        metadata["robots"],
    )
    expected = (root / metadata["html_fixture"]).read_bytes()

    assert html.encode("utf-8") == expected
    assert sha256(expected).hexdigest() == metadata["html_sha256"]
    assert html.count("data-h2-arbitration-article=") == 5
    for element_id in metadata["required_ids"]:
        assert f'id="{element_id}"' in html
    for private in ("private-a", "private-z", "a" * 64, "b" * 64, "active_2026"):
        assert private not in html
