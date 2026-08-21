from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from company_report_signal_test_helpers import (
    arbitration_facts,
    company_report,
    complete_company_report,
    counterparty_facts,
    finance_facts,
    finance_indicator,
)
from product_api.company_reports.models import (
    ArbitrationCaseFacts,
    ArbitrationParty,
    ArbitrationResultType,
    ArbitrationStatus,
    CompanyAddress,
    CounterpartyBlockStatus,
    FinanceForm,
)
from product_api.company_reports.public_h1 import (
    ArbitrationClaimAmount,
    BankruptcyBlock,
    BankruptcyTypedCounts,
    CompanyPublicH1Blocks,
    CompanyPublicIdentity,
    CompanyPublicH1Response,
    FinanceBlock,
    FinanceMetric,
    ManagementBlock,
    PublicArbitrationCase,
    PublicBankruptcyPublication,
    PublicInternalLink,
    PublicLimitation,
    PublicManager,
    PublicMoney,
    PublicOwner,
    PublicPercentChange,
    PublicTaxRecord,
    RequisitesBlock,
    TaxBlock,
    build_public_h1,
    canonical_json,
    render_public_h1_html,
)


_BANKRUPTCY_DISCLAIMER = (
    "Наличие публикации не подтверждает, что заявление принято судом, возбуждено "
    "дело, компания признана банкротом или процедура продолжается сейчас."
)


def _counterparty(**updates):
    values = {
        "inn": "0000000000",
        "ogrn": "0000000000000",
        "full_name": "  ООО  Синтетика  ",
        "short_name": "ООО Синтетика",
        "status_code": "UNREVIEWED_ACTIVE",
        "status_text": "raw provider status",
        "legal_form": "raw provider OPF",
    }
    values.update(updates)
    return counterparty_facts().model_copy(update=values)


def test_h1_exact_manifest_default_deny_and_disabled_optional_gates():
    dto = build_public_h1(complete_company_report(counterparty=_counterparty(), report_version="2"), projection_scope="latest_unpublished")

    assert dto.identity.legal_full_name == "ООО Синтетика"
    assert dto.identity.status_code is None and dto.identity.status_label is None
    assert dto.blocks.requisites.legal_form is None
    assert dto.blocks.requisites.legal_address is None
    assert list(dto.blocks.model_dump()) == ["requisites", "finance", "arbitration", "bankruptcy", "tax", "management"]
    assert [item.block_id for item in dto.coverage] == ["requisites", "finance", "arbitration", "bankruptcy", "tax", "management"]
    assert [item.dataset for item in dto.sources] == ["counterparty", "finance", "arbitration"]
    assert dto.sources[-1].normalization_version == "arbitration_normalizer_v2"
    assert dto.blocks.bankruptcy is dto.blocks.tax is dto.blocks.management is None
    assert dto.blocks.finance is None
    assert dto.indexable is False
    assert dto.checked_at.utcoffset().total_seconds() == 0
    codes = {item.code for item in dto.limitations}
    assert {"identity_status_mapping_unknown", "legal_form_mapping_unknown", "address_not_requested"} <= codes
    assert {"tax_schema_gate_not_passed", "bankruptcy_schema_gate_not_passed", "management_privacy_gate_not_passed"} <= codes
    assert dto.actions[1].path.endswith(str(dto.report_id))
    assert canonical_json(dto) == canonical_json(dto)

    quoted = build_public_h1(complete_company_report(counterparty=_counterparty(full_name='ООО "Синтетика"', short_name=None), report_version="2"), projection_scope="latest_unpublished")
    assert quoted.identity.display_name == "ООО «Синтетика»"

    addressed_cp = _counterparty(address=CompanyAddress(line_address="  Москва, улица Тестовая  ", region="Москва", is_inaccuracy=True), block_statuses={"address": CounterpartyBlockStatus.AVAILABLE})
    addressed = build_public_h1(complete_company_report(counterparty=addressed_cp, report_version="2"), projection_scope="latest_unpublished")
    assert addressed.blocks.requisites.legal_address.display_line == "Москва, улица Тестовая"
    assert addressed.blocks.requisites.region.name == "Москва"
    assert "address_marked_inaccurate" in {item.code for item in addressed.limitations}


def test_public_h1_v1_matches_fixed_safe_golden_fixture():
    report = company_report(counterparty=counterparty_facts().model_copy(update={"inn": "0000000000", "full_name": "ООО Синтетический эталон"})).model_copy(update={"report_version": "1"})
    dto = build_public_h1(report, projection_scope="latest_unpublished")
    expected = json.loads((Path(__file__).parent / "fixtures" / "company_reports" / "public_h1_v1_expected.json").read_text(encoding="utf-8"))
    assert dto.model_dump(mode="json") == expected
    serialized = json.dumps(expected, ensure_ascii=False)
    for forbidden in ("raw_payload", "authorization", "api_key", "phone", "email", "innfl"):
        assert forbidden not in serialized


def test_finance_maps_exact_form_code_suppresses_conflict_and_uses_unrounded_decimal_yoy():
    finance = finance_facts(indicators=[
        finance_indicator(FinanceForm.FINANCIAL_RESULTS, "2110", values_by_year={2024: Decimal("100"), 2025: Decimal("129.123")}),
        finance_indicator(FinanceForm.BALANCE, "1600", values_by_year={2024: Decimal("-200"), 2025: Decimal("-100")}),
        finance_indicator(FinanceForm.BALANCE, "9999", values_by_year={2024: Decimal("1"), 2025: Decimal("2")}),
    ])
    dto = build_public_h1(complete_company_report(counterparty=_counterparty(), finance=finance, report_version="2"), projection_scope="latest_unpublished")
    metrics = dto.blocks.finance.metrics
    assert [(item.metric_id, item.year) for item in metrics] == [("total_assets", 2025), ("revenue", 2025)]
    assert metrics[0].yoy.exact_percent == "50"
    assert metrics[0].yoy.display_value == "+50,0%"
    assert metrics[1].yoy.exact_percent == "29.123"
    assert metrics[1].yoy.display_value == "+29,1%"
    assert all(item.money is None for item in metrics)
    assert dto.blocks.finance.unit_policy_version is None
    assert "finance_unit_evidence_not_passed" in {item.code for item in dto.limitations}

    conflict = finance.model_copy(update={"indicators": [finance.indicators[0], finance.indicators[0].model_copy()]})
    conflict_dto = build_public_h1(complete_company_report(counterparty=_counterparty(), finance=conflict, report_version="2"), projection_scope="latest_unpublished")
    assert conflict_dto.blocks.finance is None
    assert "finance_series_conflict" in {item.code for item in conflict_dto.limitations}


@pytest.mark.parametrize("previous", [None, Decimal("0")])
def test_finance_hides_yoy_without_nonzero_adjacent_previous(previous):
    finance = finance_facts(indicators=[finance_indicator(FinanceForm.FINANCIAL_RESULTS, "2110", values_by_year={2024: previous, 2025: Decimal("5")})])
    dto = build_public_h1(complete_company_report(counterparty=_counterparty(), finance=finance, report_version="2"), projection_scope="latest_unpublished")
    assert dto.blocks.finance is None


def test_arbitration_one_bucket_amounts_malformed_conflict_and_mixed_sort():
    plaintiff = ArbitrationCaseFacts(
        case_number="A-2", date_start=date(2025, 1, 1), date_update=date(2025, 3, 1),
        claim_amount=Decimal("10.500"), currency="RUB", normalized_status=ArbitrationStatus.OPEN,
        normalized_result_type=ArbitrationResultType.SATISFIED_FULL,
        plaintiffs=[ArbitrationParty(inn="0000000000", ogrn="0000000000000")],
    )
    conflict = ArbitrationCaseFacts(
        case_number="A-1", date_start=date(2025, 1, 1), date_update=date(2025, 3, 1),
        claim_amount=Decimal("2"), currency=None, normalized_status=ArbitrationStatus.COMPLETED,
        normalized_result_type=ArbitrationResultType.REFUSED,
        respondents=[ArbitrationParty(inn="0000000000", ogrn="1111111111111")],
    )
    malformed = ArbitrationCaseFacts(
        case_number="BAD", normalized_status=ArbitrationStatus.UNKNOWN,
        normalized_result_type=ArbitrationResultType.OTHER, party_collections_valid=False,
    )
    facts = arbitration_facts([plaintiff, conflict, malformed], is_complete=False).model_copy(update={"total_cases": 5, "returned_cases": 3})
    dto = build_public_h1(complete_company_report(counterparty=_counterparty(), arbitration=facts, report_version="2"), projection_scope="latest_unpublished")
    block = dto.blocks.arbitration
    assert block.normalized_case_count == 2 and block.malformed_count == 1 and block.returned_cases == 3
    assert sum(block.role_counts.model_dump().values()) + block.unattributed_count == 2
    assert block.role_counts.plaintiff == 1 and block.unattributed_count == 1
    assert block.status_counts.model_dump() == {"open": 1, "completed": 1, "unknown": 0}
    assert [item.case_number for item in block.selected_cases] == ["A-1", "A-2"]
    assert block.claim_amounts == [ArbitrationClaimAmount(role="plaintiff", currency="RUB", exact_decimal="10.5", display_value="10,5 RUB")]
    codes = {item.code for item in dto.limitations}
    assert {"arbitration_identity_conflict", "arbitration_malformed_records", "arbitration_partial_slice"} <= codes
    coverage = next(item for item in dto.coverage if item.block_id == "arbitration")
    assert coverage.state == "partial"
    assert coverage.total == 5 and coverage.returned == 3


def test_arbitration_internal_id_only_counts_and_aggregates_but_is_not_selected():
    case = ArbitrationCaseFacts(
        internal_id="internal-only-safe-id",
        case_number=None,
        claim_amount=Decimal("12.50"),
        currency="RUB",
        normalized_status=ArbitrationStatus.OPEN,
        normalized_result_type=ArbitrationResultType.SATISFIED_FULL,
        plaintiffs=[ArbitrationParty(inn="0000000000", ogrn="0000000000000")],
    )
    dto = build_public_h1(
        complete_company_report(
            counterparty=_counterparty(),
            arbitration=arbitration_facts([case]),
            report_version="2",
        ),
        projection_scope="latest_unpublished",
    )
    block = dto.blocks.arbitration

    assert block is not None
    assert block.normalized_case_count == 1 and block.malformed_count == 0
    assert block.role_counts.plaintiff == 1
    assert block.status_counts.open == 1
    assert block.result_counts.satisfied_full == 1
    assert block.claim_amounts == [
        ArbitrationClaimAmount(
            role="plaintiff",
            currency="RUB",
            exact_decimal="12.5",
            display_value="12,5 RUB",
        )
    ]
    assert block.selected_cases == []
    assert b"internal-only-safe-id" not in canonical_json(dto)
    assert "internal-only-safe-id" not in render_public_h1_html(dto)


def test_arbitration_missing_both_identities_and_invalid_parties_remain_malformed():
    missing_identity = ArbitrationCaseFacts(
        internal_id=None,
        case_number=None,
        normalized_status=ArbitrationStatus.OPEN,
        normalized_result_type=ArbitrationResultType.SATISFIED_FULL,
        plaintiffs=[ArbitrationParty(inn="0000000000")],
    )
    invalid_parties = ArbitrationCaseFacts(
        internal_id="otherwise-valid-id",
        normalized_status=ArbitrationStatus.COMPLETED,
        normalized_result_type=ArbitrationResultType.REFUSED,
        party_collections_valid=False,
    )
    dto = build_public_h1(
        complete_company_report(
            counterparty=_counterparty(),
            arbitration=arbitration_facts([missing_identity, invalid_parties]),
            report_version="2",
        ),
        projection_scope="latest_unpublished",
    )
    block = dto.blocks.arbitration

    assert block is not None
    assert block.normalized_case_count == 0 and block.malformed_count == 2
    assert sum(block.role_counts.model_dump().values()) == 0
    assert sum(block.status_counts.model_dump().values()) == 0
    assert sum(block.result_counts.model_dump().values()) == 0
    assert block.claim_amounts == [] and block.selected_cases == []
    assert "arbitration_malformed_records" in {
        item.code for item in dto.limitations
    }


@pytest.mark.parametrize(
    "metadata",
    [
        {"total_cases": -1},
        {"limit": 0},
        {"limit": -1},
        {"offset": -1},
    ],
)
def test_arbitration_rejects_corrupt_scalar_metadata_instead_of_clamping(metadata):
    facts = arbitration_facts([]).model_copy(update=metadata)
    report = complete_company_report(
        counterparty=_counterparty(), arbitration=facts, report_version="2"
    )

    with pytest.raises(ValueError):
        build_public_h1(report, projection_scope="latest_unpublished")


def test_arbitration_incomplete_target_and_unknown_currency_fail_closed():
    case = ArbitrationCaseFacts(
        case_number="A-3", claim_amount=Decimal("5"), currency="rub",
        normalized_status=ArbitrationStatus.OPEN,
        normalized_result_type=ArbitrationResultType.OTHER,
        plaintiffs=[ArbitrationParty(inn="0000000000", ogrn="0000000000000")],
    )
    # Both party identifiers are present while target OGRN is unavailable:
    # role is not guessed and the amount cannot be attributed.
    dto = build_public_h1(complete_company_report(counterparty=_counterparty(ogrn=None), arbitration=arbitration_facts([case]), report_version="2"), projection_scope="latest_unpublished")
    assert dto.blocks.arbitration.selected_cases[0].attributed_role == "unattributed"
    assert dto.blocks.arbitration.claim_amounts == []
    assert "arbitration_target_identity_incomplete" in {item.code for item in dto.limitations}

    known_target = build_public_h1(complete_company_report(counterparty=_counterparty(), arbitration=arbitration_facts([case]), report_version="2"), projection_scope="latest_unpublished")
    assert known_target.blocks.arbitration.selected_cases[0].attributed_role == "plaintiff"
    assert known_target.blocks.arbitration.claim_amounts == []
    assert "arbitration_unknown_currency" in {item.code for item in known_target.limitations}


@pytest.mark.parametrize(
    ("extra_party", "counterparty_updates", "expected_limitation"),
    [
        (
            ArbitrationParty(inn="0000000000", ogrn="1111111111111"),
            {},
            "arbitration_identity_conflict",
        ),
        (
            ArbitrationParty(inn="0000000000", ogrn="0000000000000"),
            {"ogrn": None},
            "arbitration_target_identity_incomplete",
        ),
    ],
)
def test_arbitration_any_conflict_or_incomplete_identity_overrides_matching_party(
    extra_party,
    counterparty_updates,
    expected_limitation,
):
    matching_party = ArbitrationParty(inn="0000000000")
    case = ArbitrationCaseFacts(
        case_number="A-override",
        claim_amount=Decimal("15"),
        currency="RUB",
        normalized_status=ArbitrationStatus.OPEN,
        normalized_result_type=ArbitrationResultType.OTHER,
        plaintiffs=[matching_party, extra_party],
    )

    dto = build_public_h1(
        complete_company_report(
            counterparty=_counterparty(**counterparty_updates),
            arbitration=arbitration_facts([case]),
            report_version="2",
        ),
        projection_scope="latest_unpublished",
    )

    block = dto.blocks.arbitration
    assert block is not None
    assert block.selected_cases[0].attributed_role == "unattributed"
    assert block.selected_cases[0].claim_amount is None
    assert block.claim_amounts == []
    assert expected_limitation in {item.code for item in dto.limitations}


@pytest.mark.parametrize(
    ("party_field", "expected_role"),
    [
        ("applicants", "applicant"),
        ("creditors", "creditor"),
        ("debtors", "debtor"),
    ],
)
def test_arbitration_non_claim_roles_count_but_never_publish_amount(
    party_field,
    expected_role,
):
    party = ArbitrationParty(inn="0000000000", ogrn="0000000000000")
    case = ArbitrationCaseFacts(
        case_number=f"A-{expected_role}",
        claim_amount=Decimal("20"),
        currency="RUB",
        normalized_status=ArbitrationStatus.COMPLETED,
        normalized_result_type=ArbitrationResultType.RETURNED,
        **{party_field: [party]},
    )
    dto = build_public_h1(
        complete_company_report(
            counterparty=_counterparty(),
            arbitration=arbitration_facts([case]),
            report_version="2",
        ),
        projection_scope="latest_unpublished",
    )

    block = dto.blocks.arbitration
    assert block is not None
    assert getattr(block.role_counts, expected_role) == 1
    assert block.selected_cases[0].attributed_role == expected_role
    assert block.selected_cases[0].claim_amount is None
    assert block.claim_amounts == []
    assert sum(block.status_counts.model_dump().values()) == block.normalized_case_count
    assert sum(block.result_counts.model_dump().values()) == block.normalized_case_count


def test_arbitration_selection_uses_exact_sort_and_ten_case_limit():
    party = ArbitrationParty(inn="0000000000", ogrn="0000000000000")
    cases = [
        ArbitrationCaseFacts(
            case_number=f"A-{number:02d}",
            date_update=date(2025, 1, 1) if number < 11 else None,
            date_start=date(2024, 1, number),
            normalized_status=ArbitrationStatus.UNKNOWN,
            normalized_result_type=ArbitrationResultType.UNDEFINED,
            plaintiffs=[party],
        )
        for number in range(1, 13)
    ]
    dto = build_public_h1(
        complete_company_report(
            counterparty=_counterparty(),
            arbitration=arbitration_facts(cases),
            report_version="2",
        ),
        projection_scope="latest_unpublished",
    )

    block = dto.blocks.arbitration
    assert block is not None
    assert [item.case_number for item in block.selected_cases] == [
        "A-10", "A-09", "A-08", "A-07", "A-06",
        "A-05", "A-04", "A-03", "A-02", "A-01",
    ]


def test_exact_zero_arbitration_is_available_empty_not_missing():
    dto = build_public_h1(complete_company_report(counterparty=_counterparty(), arbitration=arbitration_facts([]), report_version="2"), projection_scope="latest_unpublished")
    coverage = next(item for item in dto.coverage if item.block_id == "arbitration")
    assert coverage.state == "available_empty"
    assert coverage.total == coverage.returned == 0
    assert dto.blocks.arbitration.normalized_case_count == 0
    rendered = render_public_h1_html(dto)
    for field in (
        "total_cases",
        "returned_cases",
        "normalized_case_count",
        "malformed_count",
        "offset",
    ):
        assert (
            f'data-field="arbitration.{field}"><span class="field-label">'
            f'arbitration.{field}</span>: <span class="field-value">0</span>'
        ) in rendered
    assert "available_empty" in rendered


def test_strict_scalar_and_contract_validators_reject_invalid_values():
    with pytest.raises(ValidationError):
        ArbitrationClaimAmount(role="plaintiff", currency="RU", exact_decimal="1", display_value="1 RU")
    with pytest.raises(ValidationError):
        PublicPercentChange(exact_percent="29.1", display_value="+29,1 %", current_year=2025, previous_year=2024, formula_version="finance_yoy_v1")

    dto = build_public_h1(complete_company_report(counterparty=_counterparty(), report_version="2"), projection_scope="latest_unpublished")
    payload = dto.model_dump(mode="python")
    payload["coverage"] = list(reversed(payload["coverage"]))
    with pytest.raises(ValidationError):
        CompanyPublicH1Response.model_validate(payload)


@pytest.mark.parametrize("exact", ["1.00", "-0"])
def test_detached_exact_decimal_strings_must_be_canonical(exact):
    with pytest.raises(ValidationError):
        ArbitrationClaimAmount(
            role="plaintiff",
            currency="RUB",
            exact_decimal=exact,
            display_value=f"{exact.replace('.', ',')} RUB",
        )
    with pytest.raises(ValidationError):
        PublicMoney(
            source_decimal=exact,
            source_unit="thousand_rub",
            rub_decimal="1",
            display_value="1 RUB",
            unit_policy_version="finance_unit_v1",
        )


@pytest.mark.parametrize(
    ("attributed_role", "amount_role"),
    [
        ("applicant", "plaintiff"),
        ("creditor", "plaintiff"),
        ("debtor", "respondent"),
        ("other", "plaintiff"),
        ("unattributed", "respondent"),
        ("plaintiff", "respondent"),
        ("respondent", "plaintiff"),
    ],
)
def test_detached_arbitration_case_rejects_unavailable_or_mismatched_amount(
    attributed_role,
    amount_role,
):
    amount = ArbitrationClaimAmount(
        role=amount_role,
        currency="RUB",
        exact_decimal="1",
        display_value="1 RUB",
    )
    with pytest.raises(ValidationError):
        PublicArbitrationCase(
            case_number="A-1",
            attributed_role=attributed_role,
            claim_amount=amount,
        )


def test_nullable_leaf_topology_remains_detached_and_structurally_usable():
    identity = CompanyPublicIdentity(
        legal_full_name="ООО Структура",
        display_name="ООО Структура",
        inn="0000000000",
        status_code="ACTIVE",
        status_label="Действует",
        status_effective_at=date(2025, 1, 2),
    )
    requisites = RequisitesBlock(legal_form="Общество с ограниченной ответственностью")
    blocks = CompanyPublicH1Blocks(
        requisites=None,
        finance=None,
        arbitration=None,
        bankruptcy=None,
        tax=None,
        management=None,
    )
    limitation = PublicLimitation(
        code="arbitration_partial_slice",
        block_id=None,
        field_id=None,
        message="Безопасное структурное сообщение",
    )
    empty_metric = FinanceMetric(metric_id="revenue", year=2025)

    assert identity.status_code == "ACTIVE"
    assert requisites.legal_form is not None
    assert blocks.requisites is None
    assert limitation.block_id is None
    assert empty_metric.money is empty_metric.yoy is None
    with pytest.raises(ValidationError):
        FinanceBlock(metrics=[empty_metric])
    populated_block = FinanceBlock(
        metrics=[
            empty_metric,
            FinanceMetric(
                metric_id="net_profit",
                year=2025,
                yoy=PublicPercentChange(
                    exact_percent="25",
                    display_value="+25,0%",
                    current_year=2025,
                    previous_year=2024,
                    formula_version="finance_yoy_v1",
                ),
            ),
        ]
    )
    assert populated_block.metrics[0] == empty_metric


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CompanyPublicIdentity(
            legal_full_name="ООО Структура",
            display_name="ООО Структура",
            inn="0000000000",
            status_code="\x00unsafe",
        ),
        lambda: RequisitesBlock(legal_form=" \t "),
        lambda: PublicLimitation(
            code="arbitration_partial_slice",
            block_id=None,
            message="\x00unsafe",
        ),
    ],
)
def test_nullable_structural_leaf_values_still_reject_unsafe_text(factory):
    with pytest.raises(ValidationError):
        factory()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload["identity"].update({"status_code": "ACTIVE"}),
        lambda payload: payload["blocks"]["requisites"].update(
            {"legal_form": "ООО"}
        ),
        lambda payload: payload["blocks"].update({"requisites": None}),
        lambda payload: payload["limitations"][0].update(
            {"message": "Безопасное, но не каталожное сообщение"}
        ),
        lambda payload: payload["limitations"][0].update({"block_id": None}),
    ],
)
def test_root_rejects_disabled_status_legal_form_requisites_and_catalog_gates(mutate):
    dto = build_public_h1(
        complete_company_report(counterparty=_counterparty(), report_version="2"),
        projection_scope="latest_unpublished",
    )
    payload = dto.model_dump(mode="python")
    mutate(payload)

    with pytest.raises(ValidationError):
        CompanyPublicH1Response.model_validate(payload)


@pytest.mark.parametrize(
    ("block_id", "mutation"),
    [
        ("bankruptcy", {"state": "available_empty"}),
        ("tax", {"limitation_codes": ["tax_schema_gate_not_passed"]}),
        ("management", {"offset": 0}),
    ],
)
def test_root_enforces_disabled_optional_coverage_and_exact_gate_codes(
    block_id,
    mutation,
):
    dto = build_public_h1(
        complete_company_report(counterparty=_counterparty(), report_version="2"),
        projection_scope="latest_unpublished",
    )
    payload = dto.model_dump(mode="python")
    coverage = next(item for item in payload["coverage"] if item["block_id"] == block_id)
    coverage.update(mutation)

    with pytest.raises(ValidationError):
        CompanyPublicH1Response.model_validate(payload)


def test_root_rejects_finance_metric_without_an_enabled_runtime_fact():
    finance = finance_facts(
        indicators=[
            finance_indicator(
                FinanceForm.FINANCIAL_RESULTS,
                "2110",
                values_by_year={2024: Decimal("100"), 2025: Decimal("125")},
            )
        ]
    )
    dto = build_public_h1(
        complete_company_report(
            counterparty=_counterparty(), finance=finance, report_version="2"
        ),
        projection_scope="latest_unpublished",
    )
    payload = dto.model_dump(mode="python")
    payload["blocks"]["finance"]["metrics"][0]["yoy"] = None

    with pytest.raises(ValidationError):
        CompanyPublicH1Response.model_validate(payload)


def test_reserved_dto_leaves_are_strict_but_detached_and_structurally_usable():
    money = PublicMoney(
        source_decimal="1.25",
        source_unit="thousand_rub",
        rub_decimal="1250",
        display_value="1 250 RUB",
        unit_policy_version="finance_unit_v1",
    )
    publication = PublicBankruptcyPublication(
        safe_reference="SYNTH-1",
        publication_date=date(2025, 1, 2),
        kind="debtor_intention",
        message="Опубликовано намерение должника обратиться в суд с заявлением о банкротстве.",
        participant_role="debtor",
    )
    bankruptcy = BankruptcyBlock(
        total=1,
        returned=1,
        limit=10,
        offset=0,
        typed_counts=BankruptcyTypedCounts(
            debtor_intention=1,
            creditor_intention=0,
            unknown=0,
        ),
        publications=[publication],
        disclaimer=_BANKRUPTCY_DISCLAIMER,
    )
    tax_record = PublicTaxRecord(
        record_type="synthetic-tax-record",
        document_date=date(2025, 1, 3),
        period="2025-Q1",
        amount=money,
    )
    tax = TaxBlock(
        unpaid_debt_indicator=False,
        message="Признак неоплаченной налоговой задолженности не установлен.",
        as_of_date=date(2025, 1, 3),
        records=[tax_record],
    )
    manager = PublicManager(name="Synthetic Manager", role="director")
    owner = PublicOwner(name_or_org="Synthetic Owner", owner_type="person")
    management = ManagementBlock(managers=[manager], owners=[owner])
    link = PublicInternalLink(
        label="Related company",
        path="/company/0000000000-related-company",
        relation="related_company",
    )

    assert bankruptcy.publications == [publication]
    assert tax.records == [tax_record]
    assert management.managers == [manager] and management.owners == [owner]
    assert link.path.startswith("/")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ManagementBlock(),
        lambda: PublicTaxRecord(record_type=" \t "),
        lambda: PublicManager(name="Manager", role="\x00unsafe"),
        lambda: PublicInternalLink(label="Related", path="https://example.test/x", relation="related"),
        lambda: PublicInternalLink(label="Related", path="//example.test/x", relation="related"),
        lambda: PublicInternalLink(label="Related", path="/unsafe path", relation="related"),
        lambda: PublicInternalLink(label=" ", path="/safe", relation="related"),
        lambda: PublicBankruptcyPublication(
            kind="creditor_intention",
            message="Опубликовано намерение должника обратиться в суд с заявлением о банкротстве.",
            participant_role="creditor",
        ),
    ],
)
def test_reserved_dto_structural_guards_reject_empty_or_unsafe_values(factory):
    with pytest.raises(ValidationError):
        factory()


@pytest.mark.parametrize(
    ("flag", "message"),
    [
        (False, "Источник передал признак неоплаченной налоговой задолженности."),
        (True, "Признак неоплаченной налоговой задолженности не установлен."),
    ],
)
def test_tax_boolean_message_catalog_cannot_be_crossed(flag, message):
    with pytest.raises(ValidationError):
        TaxBlock(unpaid_debt_indicator=flag, message=message)


@pytest.mark.parametrize("field", ["bankruptcy", "tax", "management", "internal_links"])
def test_root_contract_still_rejects_reserved_optional_emission(field):
    dto = build_public_h1(
        complete_company_report(counterparty=_counterparty(), report_version="2"),
        projection_scope="latest_unpublished",
    )
    payload = dto.model_dump(mode="python")
    if field == "bankruptcy":
        payload["blocks"][field] = BankruptcyBlock(
            total=0,
            returned=0,
            limit=1,
            offset=0,
            typed_counts=BankruptcyTypedCounts(
                debtor_intention=0,
                creditor_intention=0,
                unknown=0,
            ),
            disclaimer=_BANKRUPTCY_DISCLAIMER,
        ).model_dump(mode="python")
    elif field == "tax":
        payload["blocks"][field] = TaxBlock(
            unpaid_debt_indicator=False,
            message="Признак неоплаченной налоговой задолженности не установлен.",
        ).model_dump(mode="python")
    elif field == "management":
        payload["blocks"][field] = ManagementBlock(
            managers=[PublicManager(name="Manager", role="director")]
        ).model_dump(mode="python")
    else:
        payload[field] = [
            PublicInternalLink(
                label="Related",
                path="/company/0000000000-related",
                relation="related",
            ).model_dump(mode="python")
        ]
    with pytest.raises(ValidationError):
        CompanyPublicH1Response.model_validate(payload)


def test_ssr_is_complete_dto_only_and_escapes_every_public_scalar():
    dto = build_public_h1(complete_company_report(counterparty=_counterparty(full_name='<script>alert("x")</script>', short_name=None), report_version="2"), projection_scope="latest_unpublished")
    rendered = render_public_h1_html(dto)
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    for marker in ("Реквизиты", "Арбитраж", "Покрытие", "Источники", "Ограничения", "Действия"):
        assert marker in rendered
    assert "raw provider status" not in rendered
