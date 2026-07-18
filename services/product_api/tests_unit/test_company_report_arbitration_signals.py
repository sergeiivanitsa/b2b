from __future__ import annotations

from itertools import chain

import pytest

import product_api.company_reports.signals as signals_package
import product_api.company_reports.signals.arbitration as arbitration_signals
from company_report_signal_test_helpers import (
    arbitration_case,
    arbitration_company_report,
    arbitration_facts,
    report_without_arbitration_facts,
)
from product_api.company_reports import (
    ArbitrationRole,
    ArbitrationStatus,
    DatasetReportStatus,
    NormalizationWarning,
    RoleSummary,
    StatusSummary,
)
from product_api.company_reports.persistence import (
    calculate_company_report_snapshot_hash,
    company_report_to_snapshot,
)
from product_api.company_reports.signals import (
    NoPeriod,
    SignalConfidence,
    YearPeriod,
    YearRangePeriod,
    canonical_representation,
    referenced_fact_ids,
)


HIGH_RESPONDENT = "arbitration.high_respondent_case_count"
RESPONDENT_GROWTH = "arbitration.respondent_case_growth"
OPEN_CASES = "arbitration.open_cases"
FREQUENT_PLAINTIFF = "arbitration.frequent_plaintiff"
RULE_CODES = {
    HIGH_RESPONDENT,
    RESPONDENT_GROWTH,
    OPEN_CASES,
    FREQUENT_PLAINTIFF,
}


def _evaluate(*, cases=None, facts=None, status=DatasetReportStatus.AVAILABLE):
    normalized_facts = facts if facts is not None else arbitration_facts(cases or [])
    return arbitration_signals._evaluate_arbitration_signals(
        arbitration_company_report(
            arbitration=normalized_facts,
            arbitration_status=status,
        )
    )


def _signal(result, code):
    return next(signal for signal in result.signals if signal.code == code)


def _warning(result, rule_code):
    return next(
        warning for warning in result.warnings if warning.rule_code == rule_code
    )


def _role_cases(
    count,
    *,
    role=ArbitrationRole.RESPONDENT,
    year=2025,
    prefix="CASE",
    status=ArbitrationStatus.COMPLETED,
):
    return [
        arbitration_case(
            f"{prefix}-{index:03d}",
            year=year,
            roles=[role],
            status=status,
        )
        for index in range(count)
    ]


def _respondent_growth_cases(previous_count, later_count, *, years=(2024, 2025)):
    return [
        *_role_cases(
            previous_count,
            year=years[0],
            prefix=f"R-{years[0]}",
        ),
        *_role_cases(
            later_count,
            year=years[1],
            prefix=f"R-{years[1]}",
        ),
    ]


def _frequent_plaintiff_cases(plaintiff_count, respondent_count):
    return [
        *_role_cases(
            plaintiff_count,
            role=ArbitrationRole.PLAINTIFF,
            prefix="P",
        ),
        *_role_cases(respondent_count, prefix="R"),
    ]


def _all_rule_cases():
    respondents = _respondent_growth_cases(3, 7)
    plaintiffs = _role_cases(
        11,
        role=ArbitrationRole.PLAINTIFF,
        year=2025,
        prefix="P-ROLE-WARNING",
    )
    plaintiffs[0] = plaintiffs[0].model_copy(
        update={"normalized_status": ArbitrationStatus.OPEN}
    )
    return [*respondents, *plaintiffs]


def _assert_medium_normalization_signal(signal):
    assert signal.confidence is SignalConfidence.MEDIUM
    assert [warning.code for warning in signal.warnings] == [
        "normalization_warning_present"
    ]
    assert signal.warnings[0].evaluation_basis.failed_eligibility == []


def _assert_role_structural_suppression(result, rule_code):
    suppression = _warning(result, rule_code)
    assert suppression.code == "required_fact_missing"
    assert any(
        "structural_inputs_usable" in referenced_fact_ids(node)
        for node in suppression.evaluation_basis.failed_eligibility
    )
    return suppression


def test_dataset_unavailable_suppresses_all_four_rules_with_full_basis():
    result = _evaluate(status=DatasetReportStatus.DISABLED)

    assert result.signals == []
    assert len(result.warnings) == 4
    assert {warning.rule_code for warning in result.warnings} == RULE_CODES
    assert {warning.code for warning in result.warnings} == {"dataset_unavailable"}
    assert all(warning.dataset == "arbitration" for warning in result.warnings)
    assert all(warning.evaluation_basis.failed_eligibility for warning in result.warnings)


def test_available_dataset_without_facts_is_not_interpreted_as_zero_cases():
    result = arbitration_signals._evaluate_arbitration_signals(
        report_without_arbitration_facts()
    )

    assert result.signals == []
    assert len(result.warnings) == 4
    assert {warning.code for warning in result.warnings} == {
        "required_fact_missing"
    }


def test_incomplete_dataset_returns_four_rule_specific_result_warnings():
    cases = [
        *_respondent_growth_cases(3, 7),
        *_role_cases(
            11,
            role=ArbitrationRole.PLAINTIFF,
            prefix="P-INCOMPLETE",
        ),
    ]
    result = _evaluate(facts=arbitration_facts(cases, is_complete=False))

    assert result.signals == []
    assert len(result.warnings) == 4
    assert {warning.rule_code for warning in result.warnings} == RULE_CODES
    assert {warning.code for warning in result.warnings} == {
        "arbitration_incomplete"
    }
    for warning in result.warnings:
        values = {
            fact.id: fact.exact_value
            for fact in warning.evaluation_basis.facts
        }
        assert values["arbitration_is_complete"] is False
        assert warning.evaluation_basis.failed_eligibility


def test_structural_case_warning_does_not_become_zero_aggregate():
    structural = NormalizationWarning(
        code="arbitration_case_invalid",
        path="$.data[0]",
        message="Arbitration case entry must be an object.",
    )
    result = _evaluate(facts=arbitration_facts([], warnings=[structural]))

    assert result.signals == []
    assert {warning.rule_code for warning in result.warnings} == RULE_CODES
    assert {warning.code for warning in result.warnings} == {
        "required_fact_missing"
    }


def test_nonblocking_warning_downgrades_triggered_signals_to_medium():
    nonblocking = NormalizationWarning(
        code="arbitration_documents_invalid",
        path="$.data[0].documents",
        message="Documents block must be an array.",
    )
    cases = _respondent_growth_cases(3, 7)
    result = _evaluate(facts=arbitration_facts(cases, warnings=[nonblocking]))

    assert {signal.code for signal in result.signals} == {
        HIGH_RESPONDENT,
        RESPONDENT_GROWTH,
    }
    for signal in result.signals:
        assert signal.confidence is SignalConfidence.MEDIUM
        assert [warning.code for warning in signal.warnings] == [
            "normalization_warning_present"
        ]
        assert signal.warnings[0].evaluation_basis.failed_eligibility == []


def test_limit_parse_warning_is_nonblocking_for_exact_case_aggregates():
    nonblocking = NormalizationWarning(
        code="integer_parse_failed",
        path="$.limit",
        message="Integer value could not be parsed.",
    )
    result = _evaluate(
        facts=arbitration_facts(
            _respondent_growth_cases(3, 7),
            warnings=[nonblocking],
        )
    )

    assert {signal.code for signal in result.signals} == {
        HIGH_RESPONDENT,
        RESPONDENT_GROWTH,
    }
    assert all(
        signal.confidence is SignalConfidence.MEDIUM
        for signal in result.signals
    )


def test_malformed_plaintiff_entry_suppresses_only_plaintiff_role_rule():
    warning = NormalizationWarning(
        code="arbitration_party_invalid",
        path="$.data[0].plaintiffs[0]",
        message="Party entry must be an object.",
    )
    result = _evaluate(
        facts=arbitration_facts(_all_rule_cases(), warnings=[warning])
    )
    by_code = {signal.code: signal for signal in result.signals}

    assert set(by_code) == {HIGH_RESPONDENT, RESPONDENT_GROWTH, OPEN_CASES}
    suppression = _assert_role_structural_suppression(
        result,
        FREQUENT_PLAINTIFF,
    )
    for signal in by_code.values():
        _assert_medium_normalization_signal(signal)
    high_values = {
        fact.id: fact.exact_value
        for fact in by_code[HIGH_RESPONDENT].factual_basis.facts
    }
    growth_values = {
        fact.id: fact.exact_value
        for fact in by_code[RESPONDENT_GROWTH].factual_basis.facts
    }
    assert high_values["respondent_case_count"] == 10
    assert growth_values["previous_respondent_count"] == 3
    assert growth_values["later_respondent_count"] == 7
    assert warning.path not in suppression.message


def test_malformed_respondent_entry_suppresses_all_respondent_role_rules():
    warning = NormalizationWarning(
        code="arbitration_party_invalid",
        path="$.data[0].respondents[0]",
        message="Party entry must be an object.",
    )
    result = _evaluate(
        facts=arbitration_facts(_all_rule_cases(), warnings=[warning])
    )

    assert {signal.code for signal in result.signals} == {OPEN_CASES}
    open_signal = _signal(result, OPEN_CASES)
    _assert_medium_normalization_signal(open_signal)
    open_values = {
        fact.id: fact.exact_value for fact in open_signal.factual_basis.facts
    }
    assert open_values["open_case_count"] == 1
    for rule_code in {HIGH_RESPONDENT, RESPONDENT_GROWTH, FREQUENT_PLAINTIFF}:
        suppression = _assert_role_structural_suppression(result, rule_code)
        assert warning.path not in suppression.message


def test_malformed_applicant_entry_is_nonblocking_for_all_four_rules():
    warning = NormalizationWarning(
        code="arbitration_party_invalid",
        path="$.data[0].applicants[0]",
        message="Party entry must be an object.",
    )
    result = _evaluate(
        facts=arbitration_facts(_all_rule_cases(), warnings=[warning])
    )

    assert {signal.code for signal in result.signals} == RULE_CODES
    assert result.warnings == []
    for signal in result.signals:
        _assert_medium_normalization_signal(signal)


def test_unscoped_role_warning_conservatively_suppresses_role_rules_only():
    warning = NormalizationWarning(
        code="arbitration_party_invalid",
        path="$.data[0]",
        message="Party entry must be an object.",
    )
    result = _evaluate(
        facts=arbitration_facts(_all_rule_cases(), warnings=[warning])
    )

    assert {signal.code for signal in result.signals} == {OPEN_CASES}
    _assert_medium_normalization_signal(_signal(result, OPEN_CASES))
    for rule_code in {HIGH_RESPONDENT, RESPONDENT_GROWTH, FREQUENT_PLAINTIFF}:
        _assert_role_structural_suppression(result, rule_code)


def test_irrelevant_role_warning_permutations_remain_identical():
    role_warning = NormalizationWarning(
        code="arbitration_party_invalid",
        path="$.data[0].applicants[0]",
        message="Party entry must be an object.",
    )
    other_warning = NormalizationWarning(
        code="arbitration_documents_invalid",
        path="$.data[1].documents",
        message="Documents block must be an array.",
    )
    cases = _all_rule_cases()
    left = _evaluate(
        facts=arbitration_facts(
            cases,
            warnings=[role_warning, other_warning],
        )
    )
    right = _evaluate(
        facts=arbitration_facts(
            list(reversed(cases)),
            warnings=[other_warning, role_warning],
        )
    )

    assert left.model_dump(mode="json") == right.model_dump(mode="json")
    assert canonical_representation(left) == canonical_representation(right)


def test_low_confidence_suppresses_only_triggered_rules(monkeypatch):
    monkeypatch.setattr(
        arbitration_signals,
        "_confidence_for",
        lambda _facts: SignalConfidence.LOW,
    )
    result = _evaluate(cases=_respondent_growth_cases(3, 7))

    assert result.signals == []
    insufficient = {
        warning.rule_code
        for warning in result.warnings
        if warning.code == "signal_confidence_insufficient"
    }
    assert insufficient == {HIGH_RESPONDENT, RESPONDENT_GROWTH}


@pytest.mark.parametrize(("count", "triggered"), [(9, False), (10, True)])
def test_high_respondent_exact_threshold(count, triggered):
    result = _evaluate(cases=_role_cases(count))

    matching = [signal for signal in result.signals if signal.code == HIGH_RESPONDENT]
    assert bool(matching) is triggered
    if not triggered:
        assert HIGH_RESPONDENT not in {
            warning.rule_code for warning in result.warnings
        }


def test_duplicate_respondent_role_inside_case_counts_once():
    cases = _role_cases(9)
    cases.append(
        arbitration_case(
            "R-DUPLICATE",
            roles=[ArbitrationRole.RESPONDENT, ArbitrationRole.RESPONDENT],
        )
    )
    signal = _signal(_evaluate(cases=cases), HIGH_RESPONDENT)
    values = {fact.id: fact.exact_value for fact in signal.factual_basis.facts}

    assert values["respondent_case_count"] == 10
    assert values["summary_respondent_count"] == 10


def test_high_respondent_summary_conflict_suppresses_only_affected_rule():
    cases = _role_cases(10)
    facts = arbitration_facts(
        cases,
        role_summary=RoleSummary(respondent_count=9),
    )
    result = _evaluate(facts=facts)

    assert HIGH_RESPONDENT not in {signal.code for signal in result.signals}
    assert _warning(result, HIGH_RESPONDENT).code == "arbitration_summary_conflict"


def test_high_respondent_missing_year_is_period_suppression():
    cases = _role_cases(10)
    cases[0] = cases[0].model_copy(update={"year": None})
    result = _evaluate(cases=cases)

    assert HIGH_RESPONDENT not in {signal.code for signal in result.signals}
    warning = _warning(result, HIGH_RESPONDENT)
    assert warning.code == "arbitration_period_unavailable"
    assert warning.evaluation_basis.years == [2025]


def test_high_respondent_period_variants_and_sorted_case_ids():
    one_year_cases = _role_cases(10, year=2025, prefix="Z")
    one_year = _signal(_evaluate(cases=one_year_cases), HIGH_RESPONDENT)
    multiple_year_cases = [
        *_role_cases(5, year=2024, prefix="B"),
        *_role_cases(5, year=2025, prefix="A"),
    ]
    multiple_year = _signal(
        _evaluate(cases=list(reversed(multiple_year_cases))),
        HIGH_RESPONDENT,
    )

    assert isinstance(one_year.period, YearPeriod)
    assert one_year.period.year == 2025
    assert isinstance(multiple_year.period, YearRangePeriod)
    assert multiple_year.period.start_year == 2024
    assert multiple_year.period.end_year == 2025
    assert multiple_year.factual_basis.years == [2024, 2025]
    assert multiple_year.factual_basis.case_ids == sorted(
        case.case_number for case in multiple_year_cases
    )


def test_case_identifier_prefers_case_number_then_internal_id():
    cases = _role_cases(8, prefix="C")
    cases.extend(
        [
            arbitration_case(
                "CASE-NUMBER",
                internal_id="IGNORED-INTERNAL",
            ),
            arbitration_case(None, internal_id="INTERNAL-FALLBACK"),
        ]
    )
    signal = _signal(_evaluate(cases=cases), HIGH_RESPONDENT)

    assert "CASE-NUMBER" in signal.factual_basis.case_ids
    assert "INTERNAL-FALLBACK" in signal.factual_basis.case_ids
    assert "IGNORED-INTERNAL" not in signal.factual_basis.case_ids
    assert signal.factual_basis.case_ids == sorted(signal.factual_basis.case_ids)


def test_missing_both_case_identifiers_suppresses_full_dataset_rule():
    cases = _role_cases(9)
    cases.append(arbitration_case(None, internal_id=None))
    result = _evaluate(cases=cases)

    assert HIGH_RESPONDENT not in {signal.code for signal in result.signals}
    assert _warning(result, HIGH_RESPONDENT).code == "required_fact_missing"


@pytest.mark.parametrize(
    ("previous", "later", "triggered"),
    [(2, 4, False), (2, 5, True), (5, 5, False), (5, 2, False)],
)
def test_respondent_growth_exact_delta_and_direction(previous, later, triggered):
    result = _evaluate(cases=_respondent_growth_cases(previous, later))

    matching = [signal for signal in result.signals if signal.code == RESPONDENT_GROWTH]
    assert bool(matching) is triggered
    if not triggered:
        assert RESPONDENT_GROWTH not in {
            warning.rule_code for warning in result.warnings
        }


def test_growth_requires_consecutive_years_without_inventing_zero_year():
    result = _evaluate(
        cases=_respondent_growth_cases(2, 5, years=(2023, 2025))
    )

    assert RESPONDENT_GROWTH not in {signal.code for signal in result.signals}
    warning = _warning(result, RESPONDENT_GROWTH)
    assert warning.code == "arbitration_period_unavailable"
    values = {
        fact.id: fact.exact_value for fact in warning.evaluation_basis.facts
    }
    assert values["comparison_years_consecutive"] is False
    assert warning.evaluation_basis.years == [2023, 2025]


def test_growth_selects_two_latest_respondent_years_and_influencing_ids():
    older = _role_cases(12, year=2022, prefix="OLD")
    previous = _role_cases(1, year=2023, prefix="PREVIOUS")
    later = _role_cases(4, year=2024, prefix="LATER")
    signal = _signal(
        _evaluate(cases=[*older, *previous, *later]),
        RESPONDENT_GROWTH,
    )

    assert isinstance(signal.period, YearRangePeriod)
    assert (signal.period.start_year, signal.period.end_year) == (2023, 2024)
    assert signal.factual_basis.years == [2023, 2024]
    expected_ids = sorted(
        case.case_number for case in chain(previous, later)
    )
    assert signal.factual_basis.case_ids == expected_ids
    assert not any(case_id.startswith("OLD") for case_id in expected_ids)


def test_respondent_without_year_suppresses_growth_but_nonrespondent_does_not():
    respondent_cases = _respondent_growth_cases(2, 5)
    missing_respondent_year = arbitration_case(
        "R-NO-YEAR",
        year=None,
        roles=[ArbitrationRole.RESPONDENT],
    )
    suppressed = _evaluate(cases=[*respondent_cases, missing_respondent_year])

    warning = _warning(suppressed, RESPONDENT_GROWTH)
    assert warning.code == (
        "arbitration_period_unavailable"
    )
    assert "R-NO-YEAR" in warning.evaluation_basis.case_ids

    nonrespondent = arbitration_case(
        "P-NO-YEAR",
        year=None,
        roles=[ArbitrationRole.PLAINTIFF],
    )
    signal = _signal(
        _evaluate(cases=[*respondent_cases, nonrespondent]),
        RESPONDENT_GROWTH,
    )
    assert signal.factual_basis.years == [2024, 2025]
    assert "P-NO-YEAR" not in signal.factual_basis.case_ids


def test_growth_summary_conflict_and_missing_influencing_id_are_distinct():
    cases = _respondent_growth_cases(2, 5)
    conflict = _evaluate(
        facts=arbitration_facts(
            cases,
            role_summary=RoleSummary(respondent_count=6),
        )
    )
    assert _warning(conflict, RESPONDENT_GROWTH).code == (
        "arbitration_summary_conflict"
    )

    missing_id_cases = [*cases[:-1], cases[-1].model_copy(update={"case_number": None})]
    missing_id = _evaluate(cases=missing_id_cases)
    assert _warning(missing_id, RESPONDENT_GROWTH).code == "required_fact_missing"


def test_open_cases_zero_is_ordinary_false_trigger():
    result = _evaluate(cases=_role_cases(3))

    assert OPEN_CASES not in {signal.code for signal in result.signals}
    assert OPEN_CASES not in {warning.rule_code for warning in result.warnings}


def test_one_open_case_uses_year_period_and_open_case_id_only():
    completed = arbitration_case(
        "COMPLETED-IGNORED",
        year=2020,
        internal_id="COMPLETED-INTERNAL",
    )
    opened = arbitration_case(
        "OPEN-CASE",
        year=2025,
        status=ArbitrationStatus.OPEN,
    )
    signal = _signal(_evaluate(cases=[completed, opened]), OPEN_CASES)

    assert isinstance(signal.period, YearPeriod)
    assert signal.period.year == 2025
    assert signal.factual_basis.years == [2025]
    assert signal.factual_basis.case_ids == ["OPEN-CASE"]


def test_open_period_uses_only_open_years_and_supports_range():
    cases = [
        arbitration_case(
            "OPEN-2023",
            year=2023,
            status=ArbitrationStatus.OPEN,
        ),
        arbitration_case(
            "OPEN-2025",
            year=2025,
            status=ArbitrationStatus.OPEN,
        ),
        arbitration_case("COMPLETED-2010", year=2010),
    ]
    signal = _signal(_evaluate(cases=cases), OPEN_CASES)

    assert isinstance(signal.period, YearRangePeriod)
    assert (signal.period.start_year, signal.period.end_year) == (2023, 2025)
    assert signal.factual_basis.years == [2023, 2025]
    assert signal.factual_basis.case_ids == ["OPEN-2023", "OPEN-2025"]


def test_open_case_missing_year_or_id_is_safely_suppressed():
    missing_year = _evaluate(
        cases=[
            arbitration_case(
                "OPEN-NO-YEAR",
                year=None,
                status=ArbitrationStatus.OPEN,
            )
        ]
    )
    assert _warning(missing_year, OPEN_CASES).code == (
        "arbitration_period_unavailable"
    )

    missing_id = _evaluate(
        cases=[
            arbitration_case(
                None,
                internal_id=None,
                status=ArbitrationStatus.OPEN,
            )
        ]
    )
    assert _warning(missing_id, OPEN_CASES).code == "required_fact_missing"


def test_open_summary_conflict_and_unknown_status_are_suppressed():
    opened = arbitration_case(
        "OPEN",
        status=ArbitrationStatus.OPEN,
    )
    conflict = _evaluate(
        facts=arbitration_facts(
            [opened],
            status_summary=StatusSummary(open_count=0),
        )
    )
    assert _warning(conflict, OPEN_CASES).code == "arbitration_summary_conflict"

    unknown = _evaluate(
        cases=[
            arbitration_case(
                "UNKNOWN-STATUS",
                status=ArbitrationStatus.UNKNOWN,
            )
        ]
    )
    assert _warning(unknown, OPEN_CASES).code == "required_fact_missing"


@pytest.mark.parametrize(
    ("plaintiff", "respondent", "triggered"),
    [(9, 0, False), (10, 10, False), (10, 9, True)],
)
def test_frequent_plaintiff_exact_boundaries(plaintiff, respondent, triggered):
    result = _evaluate(cases=_frequent_plaintiff_cases(plaintiff, respondent))

    matching = [signal for signal in result.signals if signal.code == FREQUENT_PLAINTIFF]
    assert bool(matching) is triggered
    if not triggered:
        assert FREQUENT_PLAINTIFF not in {
            warning.rule_code for warning in result.warnings
        }


def test_case_can_count_once_for_both_roles_and_duplicate_roles_do_not_multiply():
    plaintiff_cases = _role_cases(
        9,
        role=ArbitrationRole.PLAINTIFF,
        prefix="P-BOTH",
    )
    both = arbitration_case(
        "BOTH",
        roles=[
            ArbitrationRole.PLAINTIFF,
            ArbitrationRole.RESPONDENT,
            ArbitrationRole.PLAINTIFF,
            ArbitrationRole.RESPONDENT,
        ],
    )
    respondent_cases = _role_cases(8, prefix="R-BOTH")
    signal = _signal(
        _evaluate(cases=[*plaintiff_cases, both, *respondent_cases]),
        FREQUENT_PLAINTIFF,
    )
    values = {fact.id: fact.exact_value for fact in signal.factual_basis.facts}

    assert values["plaintiff_case_count"] == 10
    assert values["respondent_case_count"] == 9


@pytest.mark.parametrize(
    "summary",
    [
        RoleSummary(plaintiff_count=9, respondent_count=9),
        RoleSummary(plaintiff_count=10, respondent_count=8),
    ],
)
def test_frequent_plaintiff_suppresses_each_summary_conflict(summary):
    cases = _frequent_plaintiff_cases(10, 9)
    result = _evaluate(
        facts=arbitration_facts(cases, role_summary=summary)
    )

    assert FREQUENT_PLAINTIFF not in {signal.code for signal in result.signals}
    assert _warning(result, FREQUENT_PLAINTIFF).code == (
        "arbitration_summary_conflict"
    )


def test_frequent_plaintiff_requires_full_dataset_years_and_period():
    cases = _frequent_plaintiff_cases(10, 9)
    one_year = _signal(_evaluate(cases=cases), FREQUENT_PLAINTIFF)
    assert isinstance(one_year.period, YearPeriod)

    multiple_year_cases = [
        *[
            case.model_copy(update={"year": 2024})
            for case in cases[:5]
        ],
        *cases[5:],
    ]
    multiple_year = _signal(
        _evaluate(cases=multiple_year_cases),
        FREQUENT_PLAINTIFF,
    )
    assert isinstance(multiple_year.period, YearRangePeriod)
    assert multiple_year.factual_basis.years == [2024, 2025]

    missing_year_cases = [
        cases[0].model_copy(update={"year": None}),
        *cases[1:],
    ]
    missing_year = _evaluate(cases=missing_year_cases)
    assert _warning(missing_year, FREQUENT_PLAINTIFF).code == (
        "arbitration_period_unavailable"
    )


def test_permutations_produce_identical_full_and_canonical_json():
    first_warning = NormalizationWarning(
        code="arbitration_documents_invalid",
        path="$.data[0].documents",
        message="Documents block must be an array.",
    )
    second_warning = NormalizationWarning(
        code="date_parse_failed",
        path="$.data[1].date_update",
        message="Date value could not be parsed.",
    )
    respondents = _respondent_growth_cases(3, 7)
    plaintiffs = _role_cases(
        11,
        role=ArbitrationRole.PLAINTIFF,
        year=2025,
        prefix="P-DETERMINISTIC",
    )
    plaintiffs[0] = plaintiffs[0].model_copy(
        update={
            "company_roles": [
                ArbitrationRole.PLAINTIFF,
                ArbitrationRole.APPLICANT,
            ],
            "normalized_status": ArbitrationStatus.OPEN,
        }
    )
    left_cases = [*respondents, *plaintiffs]
    right_cases = list(reversed(left_cases))
    dual_role_index = next(
        index
        for index, case in enumerate(right_cases)
        if len(case.company_roles) == 2
    )
    right_cases[dual_role_index] = right_cases[dual_role_index].model_copy(
        update={
            "company_roles": list(
                reversed(right_cases[dual_role_index].company_roles)
            )
        }
    )
    left = _evaluate(
        facts=arbitration_facts(
            left_cases,
            warnings=[first_warning, second_warning],
        )
    )
    right = _evaluate(
        facts=arbitration_facts(
            right_cases,
            warnings=[second_warning, first_warning],
        )
    )

    assert {signal.code for signal in left.signals} == RULE_CODES
    by_code = {signal.code: signal for signal in left.signals}
    assert (by_code[HIGH_RESPONDENT].direction, by_code[HIGH_RESPONDENT].strength) == (
        "negative",
        "high",
    )
    assert (by_code[RESPONDENT_GROWTH].direction, by_code[RESPONDENT_GROWTH].strength) == (
        "negative",
        "medium",
    )
    assert (by_code[OPEN_CASES].direction, by_code[OPEN_CASES].strength) == (
        "negative",
        "medium",
    )
    assert (
        by_code[FREQUENT_PLAINTIFF].direction,
        by_code[FREQUENT_PLAINTIFF].strength,
    ) == ("positive", "medium")
    assert all(signal.category == "arbitration" for signal in left.signals)
    assert all(signal.source for signal in left.signals)
    assert left.ruleset_version == "1"
    assert left.model_dump(mode="json") == right.model_dump(mode="json")
    assert canonical_representation(left) == canonical_representation(right)
    codes = [signal.code for signal in left.signals]
    assert len(codes) == len(set(codes))
    assert all(not isinstance(signal.period, NoPeriod) for signal in left.signals)


def test_warning_messages_are_static_and_case_ids_stay_in_structured_basis():
    cases = _role_cases(9)
    cases.append(arbitration_case(None, internal_id=None))
    warning = _warning(_evaluate(cases=cases), HIGH_RESPONDENT)

    assert "CASE-000" not in warning.message
    assert "0000000000" not in warning.message
    assert warning.evaluation_basis.case_ids


def test_internal_evaluator_does_not_change_report_snapshot_or_public_api():
    report = arbitration_company_report(
        arbitration=arbitration_facts(_respondent_growth_cases(3, 7))
    )
    snapshot_before = company_report_to_snapshot(report)
    hash_before = calculate_company_report_snapshot_hash(report)

    arbitration_signals._evaluate_arbitration_signals(report)

    assert company_report_to_snapshot(report) == snapshot_before
    assert calculate_company_report_snapshot_hash(report) == hash_before
    assert "signals" not in snapshot_before
    assert "_evaluate_arbitration_signals" not in signals_package.__all__
    assert not hasattr(signals_package, "SignalSet")
