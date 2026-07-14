from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

import product_api.company_reports.signals.counterparty as counterparty_signals
from company_report_signal_test_helpers import (
    RECEIVED_AT,
    company_report,
    counterparty_facts,
    report_without_counterparty_facts,
)
from product_api.company_reports import DatasetReportStatus, NormalizationWarning
from product_api.company_reports.persistence import (
    calculate_company_report_snapshot_hash,
    company_report_to_snapshot,
)
from product_api.company_reports.signals import (
    DatePeriod,
    DateRangePeriod,
    NoPeriod,
    SignalConfidence,
    Signal,
    canonical_representation,
)


def _evaluate(report=None):
    return counterparty_signals._evaluate_counterparty_signals(
        report or company_report()
    )


def _signal(result, code):
    return next(signal for signal in result.signals if signal.code == code)


def _warning(result, rule_code):
    return next(warning for warning in result.warnings if warning.rule_code == rule_code)


def test_active_signal_uses_source_period_and_complete_factual_basis():
    report = company_report()
    result = _evaluate(report)
    signal = _signal(result, "counterparty.active")
    facts = {fact.id: fact.exact_value for fact in signal.factual_basis.facts}

    assert signal.direction == "positive"
    assert signal.strength == "medium"
    assert signal.confidence is SignalConfidence.HIGH
    assert signal.source == [report.counterparty.source]
    assert isinstance(signal.period, NoPeriod)
    assert signal.period.as_of == report.counterparty.source.received_at
    assert facts["dataset_status"] == "available"
    assert facts["is_active"] is True
    assert facts["dissolved_date"] is None
    assert signal.factual_basis.eligibility
    assert signal.factual_basis.trigger
    assert signal.factual_basis.strength_decision.default_strength == "medium"
    assert signal.factual_basis.period_basis.fact_ids == ["source_received_at"]
    assert signal.factual_basis.years == []
    assert signal.factual_basis.case_ids == []


def test_active_false_trigger_creates_no_active_warning():
    result = _evaluate(
        company_report(counterparty=counterparty_facts(is_active=False))
    )

    assert "counterparty.active" not in {signal.code for signal in result.signals}
    assert "counterparty.active" not in {
        warning.rule_code for warning in result.warnings
    }


def test_dissolved_with_date_uses_date_period_without_status_conflict():
    dissolved = date(2025, 12, 20)
    result = _evaluate(
        company_report(
            counterparty=counterparty_facts(
                is_active=False,
                dissolved_date=dissolved,
            )
        )
    )
    signal = _signal(result, "counterparty.dissolved")

    assert signal.direction == "negative"
    assert signal.strength == "critical"
    assert isinstance(signal.period, DatePeriod)
    assert signal.period.value == dissolved
    assert signal.factual_basis.period_basis.fact_ids == ["dissolved_date"]
    assert "counterparty.status_conflict" not in {
        item.code for item in result.signals
    }


def test_dissolved_without_date_uses_source_received_at():
    report = company_report(counterparty=counterparty_facts(is_active=False))
    signal = _signal(_evaluate(report), "counterparty.dissolved")

    assert isinstance(signal.period, NoPeriod)
    assert signal.period.as_of == RECEIVED_AT
    assert signal.factual_basis.period_basis.fact_ids == ["source_received_at"]


def test_exact_status_conflict_suppresses_active_and_dissolved_only():
    report = company_report(
        counterparty=counterparty_facts(
            is_active=True,
            dissolved_date=date(2025, 1, 1),
        )
    )
    result = _evaluate(report)
    codes = {signal.code for signal in result.signals}
    warning_pairs = {(warning.code, warning.rule_code) for warning in result.warnings}

    assert "counterparty.status_conflict" in codes
    assert "counterparty.long_operating_history" in codes
    assert "counterparty.active" not in codes
    assert "counterparty.dissolved" not in codes
    assert ("status_conflict", "counterparty.active") in warning_pairs
    assert ("status_conflict", "counterparty.dissolved") in warning_pairs
    conflict = _signal(result, "counterparty.status_conflict")
    assert conflict.direction == "informational"
    assert conflict.strength == "high"
    assert conflict.warnings == []
    assert isinstance(conflict.period, NoPeriod)


@pytest.mark.parametrize(
    (
        "is_active",
        "dissolved_date",
        "parse_failed",
        "expected_signals",
        "expected_warnings",
        "dissolved_confidence",
    ),
    [
        (
            False,
            None,
            False,
            {"counterparty.dissolved"},
            {},
            SignalConfidence.HIGH,
        ),
        (
            False,
            None,
            True,
            {"counterparty.dissolved"},
            {},
            SignalConfidence.MEDIUM,
        ),
        (True, None, False, {"counterparty.active"}, {}, None),
        (
            True,
            None,
            True,
            set(),
            {
                "counterparty.active": "required_fact_missing",
                "counterparty.dissolved": "required_fact_missing",
                "counterparty.status_conflict": "required_fact_missing",
            },
            None,
        ),
        (
            True,
            date(2025, 1, 1),
            False,
            {"counterparty.status_conflict"},
            {
                "counterparty.active": "status_conflict",
                "counterparty.dissolved": "status_conflict",
            },
            None,
        ),
        (
            None,
            date(2025, 1, 1),
            False,
            {"counterparty.dissolved"},
            {
                "counterparty.active": "required_fact_missing",
                "counterparty.status_conflict": "required_fact_missing",
            },
            SignalConfidence.HIGH,
        ),
        (
            None,
            None,
            False,
            set(),
            {
                "counterparty.active": "required_fact_missing",
                "counterparty.dissolved": "required_fact_missing",
                "counterparty.status_conflict": "required_fact_missing",
            },
            None,
        ),
    ],
)
def test_status_rules_distinguish_clean_absence_from_parse_failure(
    is_active,
    dissolved_date,
    parse_failed,
    expected_signals,
    expected_warnings,
    dissolved_confidence,
):
    warnings = (
        [
            NormalizationWarning(
                code="date_parse_failed",
                path="$.company.dissolved_date",
                message="Date value could not be parsed.",
            )
        ]
        if parse_failed
        else []
    )
    result = _evaluate(
        company_report(
            counterparty=counterparty_facts(
                is_active=is_active,
                dissolved_date=dissolved_date,
                warnings=warnings,
            )
        )
    )
    status_codes = {
        "counterparty.active",
        "counterparty.dissolved",
        "counterparty.status_conflict",
    }
    actual_signals = {
        signal.code for signal in result.signals if signal.code in status_codes
    }
    actual_warnings = {
        warning.rule_code: warning.code
        for warning in result.warnings
        if warning.rule_code in status_codes
    }

    assert actual_signals == expected_signals
    assert actual_warnings == expected_warnings
    for signal in result.signals:
        if signal.code in status_codes:
            assert "dissolved_date_usable" in {
                fact.id for fact in signal.factual_basis.facts
            }
    for warning in result.warnings:
        if warning.rule_code in status_codes:
            assert "dissolved_date_usable" in {
                fact.id for fact in warning.evaluation_basis.facts
            }
    assert "counterparty.long_operating_history" in {
        signal.code for signal in result.signals
    }
    if dissolved_confidence is not None:
        assert _signal(result, "counterparty.dissolved").confidence is (
            dissolved_confidence
        )


@pytest.mark.parametrize(
    ("years", "expected"),
    [(4, False), (5, True), (6, True)],
)
def test_long_operating_history_uses_normalized_five_year_threshold(years, expected):
    result = _evaluate(
        company_report(
            counterparty=counterparty_facts(years_from_registration=years)
        )
    )
    matching = [
        signal
        for signal in result.signals
        if signal.code == "counterparty.long_operating_history"
    ]

    assert bool(matching) is expected
    if matching:
        signal = matching[0]
        assert isinstance(signal.period, DateRangePeriod)
        assert signal.period.start == date(2021, 1, 10)
        assert signal.period.end == RECEIVED_AT.date()
        values = {
            fact.id: fact.exact_value for fact in signal.factual_basis.facts
        }
        assert values["years_from_registration"] == years
    else:
        assert "counterparty.long_operating_history" not in {
            warning.rule_code for warning in result.warnings
        }


@pytest.mark.parametrize(
    ("facts", "warning_code"),
    [
        (counterparty_facts(years_from_registration=None), "required_fact_missing"),
        (counterparty_facts(registration_date=None), "required_fact_missing"),
        (
            counterparty_facts(registration_date=date(2026, 1, 11)),
            "required_period_unavailable",
        ),
    ],
)
def test_long_history_missing_or_invalid_period_is_safely_suppressed(
    facts,
    warning_code,
):
    result = _evaluate(company_report(counterparty=facts))
    warning = _warning(result, "counterparty.long_operating_history")

    assert "counterparty.long_operating_history" not in {
        signal.code for signal in result.signals
    }
    assert warning.code == warning_code
    assert warning.evaluation_basis.failed_eligibility


def test_unavailable_dataset_suppresses_every_stage_one_rule():
    result = _evaluate(
        company_report(counterparty_status=DatasetReportStatus.DISABLED)
    )

    assert result.signals == []
    assert len(result.warnings) == 4
    assert {warning.code for warning in result.warnings} == {"dataset_unavailable"}
    assert all(warning.dataset == "counterparty" for warning in result.warnings)
    assert all(warning.evaluation_basis.failed_eligibility for warning in result.warnings)


def test_available_dataset_without_counterparty_facts_is_not_invented():
    result = _evaluate(report_without_counterparty_facts())

    assert result.signals == []
    assert len(result.warnings) == 4
    assert {warning.code for warning in result.warnings} == {
        "required_fact_missing"
    }


def test_present_counterparty_with_missing_status_facts_is_safely_suppressed():
    result = _evaluate(
        company_report(
            counterparty=counterparty_facts(
                is_active=None,
                dissolved_date=None,
            )
        )
    )
    warnings_by_rule = {
        warning.rule_code: warning.code for warning in result.warnings
    }

    assert warnings_by_rule["counterparty.active"] == "required_fact_missing"
    assert warnings_by_rule["counterparty.dissolved"] == "required_fact_missing"
    assert warnings_by_rule["counterparty.status_conflict"] == "required_fact_missing"


def test_normalization_warning_downgrades_sufficient_signals_to_medium():
    warning = NormalizationWarning(
        code="counterparty_block_invalid",
        path="$.company.address",
        message="Requested block has an unexpected type.",
    )
    result = _evaluate(
        company_report(counterparty=counterparty_facts(warnings=[warning]))
    )

    assert result.warnings == []
    assert result.signals
    for signal in result.signals:
        assert signal.confidence is SignalConfidence.MEDIUM
        assert [item.code for item in signal.warnings] == [
            "normalization_warning_present"
        ]
        assert signal.warnings[0].evaluation_basis.failed_eligibility == []


def test_unparseable_dissolved_date_does_not_become_proven_absence():
    parse_warning = NormalizationWarning(
        code="date_parse_failed",
        path="$.company.dissolved_date",
        message="Date value could not be parsed.",
    )
    result = _evaluate(
        company_report(
            counterparty=counterparty_facts(
                is_active=True,
                dissolved_date=None,
                warnings=[parse_warning],
            )
        )
    )

    assert "counterparty.active" not in {signal.code for signal in result.signals}
    assert _warning(result, "counterparty.active").code == "required_fact_missing"
    assert _warning(result, "counterparty.dissolved").code == (
        "required_fact_missing"
    )
    assert _warning(result, "counterparty.status_conflict").code == (
        "required_fact_missing"
    )


def test_false_is_active_remains_sufficient_for_dissolved_with_bad_date():
    parse_warning = NormalizationWarning(
        code="date_parse_failed",
        path="$.company.dissolved_date",
        message="Date value could not be parsed.",
    )
    result = _evaluate(
        company_report(
            counterparty=counterparty_facts(
                is_active=False,
                dissolved_date=None,
                warnings=[parse_warning],
            )
        )
    )
    signal = _signal(result, "counterparty.dissolved")

    assert isinstance(signal.period, NoPeriod)
    assert signal.confidence is SignalConfidence.MEDIUM


def test_low_confidence_suppresses_only_triggered_signals(monkeypatch):
    monkeypatch.setattr(
        counterparty_signals,
        "_confidence_for",
        lambda _facts: SignalConfidence.LOW,
    )
    result = _evaluate(company_report())

    assert result.signals == []
    assert {
        warning.rule_code
        for warning in result.warnings
        if warning.code == "signal_confidence_insufficient"
    } == {"counterparty.active", "counterparty.long_operating_history"}


def test_received_at_is_the_only_clock_for_legal_status_periods():
    source_time = datetime(2024, 6, 1, 5, 30, tzinfo=timezone.utc)
    report = company_report(
        counterparty=counterparty_facts(
            registration_date=date(2019, 6, 1),
            years_from_registration=5,
            received_at=source_time,
        )
    )
    result = _evaluate(report)

    assert _signal(result, "counterparty.active").period.as_of == source_time
    long_history = _signal(result, "counterparty.long_operating_history")
    assert long_history.period.end == source_time.date()
    assert long_history.period.end != report.generated_at.date()

    active = _signal(result, "counterparty.active")
    with pytest.raises(ValidationError):
        Signal.model_validate(
            {
                **active.model_dump(mode="python"),
                "period": NoPeriod(
                    as_of=datetime(2026, 2, 9, tzinfo=timezone.utc)
                ),
            }
        )


def test_warning_and_source_permutations_produce_identical_json():
    first = NormalizationWarning(code="z", path="z", message="safe z")
    second = NormalizationWarning(code="a", path="a", message="safe a")
    left = _evaluate(
        company_report(counterparty=counterparty_facts(warnings=[first, second]))
    )
    right = _evaluate(
        company_report(counterparty=counterparty_facts(warnings=[second, first]))
    )

    assert left.model_dump(mode="json") == right.model_dump(mode="json")
    assert canonical_representation(left) == canonical_representation(right)
    codes = [signal.code for signal in left.signals]
    assert len(codes) == len(set(codes))


def test_evaluation_does_not_change_company_report_snapshot_or_hash():
    report = company_report()
    snapshot_before = company_report_to_snapshot(report)
    hash_before = calculate_company_report_snapshot_hash(report)

    _evaluate(report)

    assert company_report_to_snapshot(report) == snapshot_before
    assert calculate_company_report_snapshot_hash(report) == hash_before
    assert "signals" not in snapshot_before


def test_signals_package_has_no_forbidden_transport_or_persistence_imports():
    package = (
        Path(__file__).parents[1]
        / "src"
        / "product_api"
        / "company_reports"
        / "signals"
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))

    assert "product_api.providers" not in source
    assert "company_reports.persistence" not in source
    assert "sqlalchemy" not in source
    assert "fastapi" not in source
    assert "httpx" not in source
    assert "raw_payload" not in source
