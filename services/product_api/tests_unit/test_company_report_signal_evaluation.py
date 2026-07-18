from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import get_type_hints

import pytest
from pydantic import ValidationError

import product_api.company_reports.signals as signals_package
import product_api.company_reports.signals.evaluation as signal_evaluation
import product_api.company_reports.signals.models as signal_models
from company_report_orchestrator_test_helpers import successful_fake_provider
from company_report_signal_test_helpers import (
    arbitration_case,
    arbitration_facts,
    arbitration_source,
    company_report,
    complete_company_report,
    counterparty_facts,
    finance_company_report,
    finance_facts,
    finance_indicator,
    finance_source,
    report_without_finance_facts,
    sample_signal,
)
from product_api.company_reports import (
    ArbitrationRole,
    ArbitrationStatus,
    CompanyReport,
    DatasetReportStatus,
    FinanceForm,
    FinancialPeriod,
    NormalizationWarning,
    build_company_report,
)
from product_api.company_reports.persistence import (
    calculate_company_report_snapshot_hash,
    company_report_from_snapshot,
    company_report_to_snapshot,
)
from product_api.company_reports.persistence.models import (
    CompanyReportDataset,
    CompanyReportProviderRequest,
    CompanyReportRecord,
    CompanyReportSubject,
)
from product_api.company_reports.signals import (
    PredicateExpression,
    PresenceOperator,
    SignalCategory,
    SignalEvaluationBasis,
    SignalEvaluationResult,
    SignalFact,
    SignalWarning,
    canonical_representation,
    evaluate_signals,
)
from product_api.company_reports.signals.arbitration import (
    _evaluate_arbitration_signals,
)
from product_api.company_reports.signals.counterparty import (
    _evaluate_counterparty_signals,
)
from product_api.company_reports.signals.finance import _evaluate_finance_signals


_CATEGORY_ORDER = {
    SignalCategory.LEGAL_STATUS: 0,
    SignalCategory.FINANCIAL: 1,
    SignalCategory.ARBITRATION: 2,
}


def _suppression_warning(
    *,
    dataset: str,
    rule_code: str,
    normalized_path: str | None = None,
) -> SignalWarning:
    fact = SignalFact(
        id="dataset_available",
        normalized_path=normalized_path or f"datasets.{dataset}.available",
        exact_value=None,
    )
    eligibility = PredicateExpression(
        fact_id=fact.id,
        operator=PresenceOperator(),
    )
    return SignalWarning(
        code="dataset_unavailable",
        rule_code=rule_code,
        dataset=dataset,
        message=f"{dataset.capitalize()} dataset is unavailable.",
        evaluation_basis=SignalEvaluationBasis(
            facts=[fact],
            eligibility=eligibility,
            failed_eligibility=[eligibility],
        ),
    )


def _assert_contract_order(result: SignalEvaluationResult) -> None:
    keys = [
        (_CATEGORY_ORDER[signal.category], signal.code)
        for signal in result.signals
    ]
    assert keys == sorted(keys)


def _arbitration_cases():
    previous = [
        arbitration_case(f"R-2024-{index}", year=2024)
        for index in range(3)
    ]
    later = [
        arbitration_case(
            f"R-2025-{index}",
            year=2025,
            roles=(
                [ArbitrationRole.RESPONDENT, ArbitrationRole.APPLICANT]
                if index == 0
                else [ArbitrationRole.RESPONDENT]
            ),
            status=(
                ArbitrationStatus.OPEN
                if index == 0
                else ArbitrationStatus.COMPLETED
            ),
        )
        for index in range(7)
    ]
    return [*previous, *later]


def test_public_api_signature_exports_and_result_contract():
    signature = inspect.signature(evaluate_signals)
    hints = get_type_hints(evaluate_signals)

    assert signals_package.evaluate_signals is evaluate_signals
    assert list(signature.parameters) == ["report"]
    assert hints == {
        "report": CompanyReport,
        "return": SignalEvaluationResult,
    }
    assert inspect.iscoroutinefunction(evaluate_signals) is False
    assert set(signal_models.__all__).issubset(signals_package.__all__)
    assert signals_package.__all__.count("evaluate_signals") == 1
    assert not {
        "_evaluate_counterparty_signals",
        "_evaluate_finance_signals",
        "_evaluate_arbitration_signals",
    }.intersection(signals_package.__all__)
    for forbidden_name in (
        "SignalSet",
        "build_signal_set",
        "get_signals",
        "calculate_signals",
        "evaluate_company_signals",
    ):
        assert forbidden_name not in signals_package.__all__
        assert not hasattr(signals_package, forbidden_name)

    result = evaluate_signals(complete_company_report())
    assert isinstance(result, SignalEvaluationResult)
    assert result.ruleset_version == "1"
    assert set(SignalEvaluationResult.model_fields) == {
        "ruleset_version",
        "signals",
        "warnings",
    }


def test_composer_calls_each_evaluator_once_and_preserves_outputs(monkeypatch):
    report = complete_company_report()
    counterparty_signal = sample_signal(code="counterparty.mock")
    finance_signal = sample_signal(
        code="finance.mock",
        category=SignalCategory.FINANCIAL,
        source=[finance_source()],
    )
    arbitration_signal = sample_signal(
        code="arbitration.mock",
        category=SignalCategory.ARBITRATION,
        source=[arbitration_source()],
    )
    counterparty_warning = _suppression_warning(
        dataset="counterparty",
        rule_code="counterparty.mock",
    )
    finance_warning = _suppression_warning(
        dataset="finance",
        rule_code="finance.mock",
    )
    arbitration_warning = _suppression_warning(
        dataset="arbitration",
        rule_code="arbitration.mock",
    )
    evaluator_results = {
        "counterparty": SignalEvaluationResult(
            signals=[counterparty_signal],
            warnings=[counterparty_warning],
        ),
        "finance": SignalEvaluationResult(
            signals=[finance_signal],
            warnings=[finance_warning],
        ),
        "arbitration": SignalEvaluationResult(
            signals=[arbitration_signal],
            warnings=[arbitration_warning],
        ),
    }
    before = {
        name: result.model_dump(mode="json")
        for name, result in evaluator_results.items()
    }
    calls: list[tuple[str, CompanyReport]] = []

    def evaluator(name):
        def run(received_report):
            calls.append((name, received_report))
            return evaluator_results[name]

        return run

    monkeypatch.setattr(
        signal_evaluation,
        "_evaluate_counterparty_signals",
        evaluator("counterparty"),
    )
    monkeypatch.setattr(
        signal_evaluation,
        "_evaluate_finance_signals",
        evaluator("finance"),
    )
    monkeypatch.setattr(
        signal_evaluation,
        "_evaluate_arbitration_signals",
        evaluator("arbitration"),
    )

    result = evaluate_signals(report)

    assert [name for name, _report in calls] == [
        "counterparty",
        "finance",
        "arbitration",
    ]
    assert all(received_report is report for _name, received_report in calls)
    assert [signal.code for signal in result.signals] == [
        "counterparty.mock",
        "finance.mock",
        "arbitration.mock",
    ]
    assert {warning.rule_code for warning in result.warnings} == {
        "counterparty.mock",
        "finance.mock",
        "arbitration.mock",
    }
    assert {
        signal.code: signal.model_dump(mode="json")
        for signal in result.signals
    } == {
        signal.code: signal.model_dump(mode="json")
        for signal in (
            counterparty_signal,
            finance_signal,
            arbitration_signal,
        )
    }
    assert {
        name: evaluator_result.model_dump(mode="json")
        for name, evaluator_result in evaluator_results.items()
    } == before


def test_composer_does_not_use_evaluator_output_order(monkeypatch):
    unsorted_result = SignalEvaluationResult.model_construct(
        ruleset_version="1",
        signals=[
            sample_signal(
                code="arbitration.z",
                category=SignalCategory.ARBITRATION,
                source=[arbitration_source()],
            ),
            sample_signal(code="counterparty.z"),
            sample_signal(
                code="finance.z",
                category=SignalCategory.FINANCIAL,
                source=[finance_source()],
            ),
            sample_signal(code="counterparty.a"),
        ],
        warnings=[
            _suppression_warning(
                dataset="finance",
                rule_code="finance.z",
            ),
            _suppression_warning(
                dataset="counterparty",
                rule_code="counterparty.a",
            ),
        ],
    )
    monkeypatch.setattr(
        signal_evaluation,
        "_evaluate_counterparty_signals",
        lambda _report: unsorted_result,
    )
    monkeypatch.setattr(
        signal_evaluation,
        "_evaluate_finance_signals",
        lambda _report: SignalEvaluationResult(),
    )
    monkeypatch.setattr(
        signal_evaluation,
        "_evaluate_arbitration_signals",
        lambda _report: SignalEvaluationResult(),
    )

    result = evaluate_signals(complete_company_report())

    assert [signal.code for signal in result.signals] == [
        "counterparty.a",
        "counterparty.z",
        "finance.z",
        "arbitration.z",
    ]
    assert [warning.rule_code for warning in result.warnings] == [
        "counterparty.a",
        "finance.z",
    ]


def test_incompatible_internal_ruleset_is_a_contract_error_after_all_calls(
    monkeypatch,
):
    calls: list[str] = []
    incompatible = SignalEvaluationResult.model_construct(
        ruleset_version="2",
        signals=[],
        warnings=[],
    )

    def evaluator(name, result):
        def run(_report):
            calls.append(name)
            return result

        return run

    monkeypatch.setattr(
        signal_evaluation,
        "_evaluate_counterparty_signals",
        evaluator("counterparty", incompatible),
    )
    monkeypatch.setattr(
        signal_evaluation,
        "_evaluate_finance_signals",
        evaluator("finance", SignalEvaluationResult()),
    )
    monkeypatch.setattr(
        signal_evaluation,
        "_evaluate_arbitration_signals",
        evaluator("arbitration", SignalEvaluationResult()),
    )

    with pytest.raises(ValueError, match="incompatible ruleset"):
        evaluate_signals(complete_company_report())

    assert calls == ["counterparty", "finance", "arbitration"]


def test_duplicate_code_from_different_evaluators_is_rejected(monkeypatch):
    duplicate = sample_signal(code="counterparty.duplicate")
    results = iter(
        [
            SignalEvaluationResult(signals=[duplicate]),
            SignalEvaluationResult(signals=[duplicate]),
            SignalEvaluationResult(),
        ]
    )
    for name in (
        "_evaluate_counterparty_signals",
        "_evaluate_finance_signals",
        "_evaluate_arbitration_signals",
    ):
        monkeypatch.setattr(
            signal_evaluation,
            name,
            lambda _report, result=next(results): result,
        )

    with pytest.raises(ValidationError, match="signal codes must be unique"):
        evaluate_signals(complete_company_report())


def test_empty_signals_keep_full_object_distinct_warnings(monkeypatch):
    first = _suppression_warning(
        dataset="counterparty",
        rule_code="counterparty.mock",
        normalized_path="datasets.counterparty.first",
    )
    identical = first.model_copy()
    different_basis = _suppression_warning(
        dataset="counterparty",
        rule_code="counterparty.mock",
        normalized_path="datasets.counterparty.second",
    )
    finance = _suppression_warning(
        dataset="finance",
        rule_code="finance.mock",
    )
    monkeypatch.setattr(
        signal_evaluation,
        "_evaluate_counterparty_signals",
        lambda _report: SignalEvaluationResult(warnings=[first]),
    )
    monkeypatch.setattr(
        signal_evaluation,
        "_evaluate_finance_signals",
        lambda _report: SignalEvaluationResult(
            warnings=[identical, finance],
        ),
    )
    monkeypatch.setattr(
        signal_evaluation,
        "_evaluate_arbitration_signals",
        lambda _report: SignalEvaluationResult(warnings=[different_basis]),
    )

    result = evaluate_signals(complete_company_report())

    assert result.signals == []
    assert len(result.warnings) == 3
    assert {warning.dataset for warning in result.warnings} == {
        "counterparty",
        "finance",
    }
    counterparty_warnings = [
        warning
        for warning in result.warnings
        if warning.dataset == "counterparty"
    ]
    assert len(counterparty_warnings) == 2
    assert {
        warning.evaluation_basis.facts[0].normalized_path
        for warning in counterparty_warnings
    } == {
        "datasets.counterparty.first",
        "datasets.counterparty.second",
    }


def test_complete_report_composes_all_categories_without_rewriting_basis():
    report = complete_company_report()
    internal_results = (
        _evaluate_counterparty_signals(report),
        _evaluate_finance_signals(report),
        _evaluate_arbitration_signals(report),
    )
    expected_signals = {
        signal.code: signal.model_dump(mode="json")
        for internal_result in internal_results
        for signal in internal_result.signals
    }
    expected_warnings = {
        canonical_representation(warning)
        for internal_result in internal_results
        for warning in internal_result.warnings
    }

    result = evaluate_signals(report)
    actual_signals = {
        signal.code: signal.model_dump(mode="json")
        for signal in result.signals
    }

    assert actual_signals == expected_signals
    assert {
        "counterparty.active",
        "counterparty.long_operating_history",
        "finance.negative_equity",
        "finance.revenue_decline",
        "finance.net_loss",
        "finance.cash_shortfall",
        "finance.high_accounts_payable",
        "arbitration.high_respondent_case_count",
        "arbitration.respondent_case_growth",
        "arbitration.open_cases",
    }.issubset(actual_signals)
    assert len(actual_signals) == len(result.signals)
    assert {
        canonical_representation(warning)
        for warning in result.warnings
    } == expected_warnings
    assert all(signal.source for signal in result.signals)
    assert all(signal.period is not None for signal in result.signals)
    assert all(signal.factual_basis.facts for signal in result.signals)
    assert result.ruleset_version == "1"
    _assert_contract_order(result)


def test_partial_report_preserves_available_signals_and_unavailable_warnings():
    result = evaluate_signals(company_report())

    assert {
        signal.code for signal in result.signals
    } == {
        "counterparty.active",
        "counterparty.long_operating_history",
    }
    assert len(result.warnings) == 9
    assert {warning.dataset for warning in result.warnings} == {
        "finance",
        "arbitration",
    }
    assert {warning.code for warning in result.warnings} == {
        "dataset_unavailable"
    }
    _assert_contract_order(result)


def test_failed_report_returns_rule_specific_warnings_without_signals():
    result = evaluate_signals(
        company_report(counterparty_status=DatasetReportStatus.DISABLED)
    )

    assert result.signals == []
    assert len(result.warnings) == 13
    assert len({warning.rule_code for warning in result.warnings}) == 13
    assert {warning.dataset for warning in result.warnings} == {
        "counterparty",
        "finance",
        "arbitration",
    }
    assert {warning.code for warning in result.warnings} == {
        "dataset_unavailable"
    }
    assert all(
        warning.evaluation_basis.failed_eligibility
        for warning in result.warnings
    )


def test_available_dataset_with_missing_facts_keeps_result_warnings():
    result = evaluate_signals(report_without_finance_facts())
    finance_warnings = [
        warning for warning in result.warnings if warning.dataset == "finance"
    ]

    assert result.signals == []
    assert len(finance_warnings) == 5
    assert {warning.rule_code for warning in finance_warnings} == {
        "finance.negative_equity",
        "finance.revenue_decline",
        "finance.net_loss",
        "finance.cash_shortfall",
        "finance.high_accounts_payable",
    }
    assert {warning.code for warning in finance_warnings} == {
        "required_fact_missing"
    }


def test_incomplete_arbitration_does_not_hide_legal_or_financial_results():
    report = complete_company_report(
        arbitration=arbitration_facts(
            _arbitration_cases(),
            is_complete=False,
        )
    )
    result = evaluate_signals(report)

    assert any(
        signal.category is SignalCategory.LEGAL_STATUS
        for signal in result.signals
    )
    assert any(
        signal.category is SignalCategory.FINANCIAL
        for signal in result.signals
    )
    assert not any(
        signal.category is SignalCategory.ARBITRATION
        for signal in result.signals
    )
    arbitration_warnings = [
        warning
        for warning in result.warnings
        if warning.dataset == "arbitration"
    ]
    assert len(arbitration_warnings) == 4
    assert {warning.code for warning in arbitration_warnings} == {
        "arbitration_incomplete"
    }


def test_empty_finance_periods_do_not_create_reporting_absent_or_stop_others():
    report = complete_company_report(finance=finance_facts([]))
    result = evaluate_signals(report)
    finance_warnings = [
        warning for warning in result.warnings if warning.dataset == "finance"
    ]

    assert any(
        signal.category is SignalCategory.LEGAL_STATUS
        for signal in result.signals
    )
    assert any(
        signal.category is SignalCategory.ARBITRATION
        for signal in result.signals
    )
    assert not any(
        signal.category is SignalCategory.FINANCIAL
        for signal in result.signals
    )
    assert len(finance_warnings) == 5
    assert {warning.code for warning in finance_warnings} == {
        "required_period_unavailable"
    }
    assert "finance.reporting_absent" not in canonical_representation(result)


def test_unavailable_counterparty_does_not_hide_available_finance_signal():
    report = finance_company_report(
        finance=finance_facts(
            [FinancialPeriod(year=2025, equity=-1)]
        )
    )
    result = evaluate_signals(report)

    assert "finance.negative_equity" in {
        signal.code for signal in result.signals
    }
    counterparty_warnings = [
        warning
        for warning in result.warnings
        if warning.dataset == "counterparty"
    ]
    assert len(counterparty_warnings) == 4
    assert {warning.code for warning in counterparty_warnings} == {
        "dataset_unavailable"
    }


def test_nested_input_permutations_produce_identical_json():
    first_warning = NormalizationWarning(
        code="first_safe_warning",
        path="$.first",
        message="Safe first warning.",
    )
    second_warning = NormalizationWarning(
        code="second_safe_warning",
        path="$.second",
        message="Safe second warning.",
    )
    periods = [
        FinancialPeriod(year=2024, revenue=200),
        FinancialPeriod(
            year=2025,
            current_assets=100,
            cash_and_equivalents=10,
            equity=-1,
            short_term_liabilities=100,
            accounts_payable=200,
            revenue=100,
            net_profit=-1,
        ),
    ]
    indicators = [
        finance_indicator(
            FinanceForm.BALANCE,
            "1300",
            source_path="$.balances.indicators[0]",
            values_by_year={2025: -1},
        ),
        finance_indicator(
            FinanceForm.FINANCIAL_RESULTS,
            "2110",
            source_path="$.fin_results.indicators[0]",
            values_by_year={2024: 200, 2025: 100},
        ),
    ]
    left_cases = _arbitration_cases()
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
    left = complete_company_report(
        counterparty=counterparty_facts(
            warnings=[first_warning, second_warning],
        ),
        finance=finance_facts(
            periods,
            indicators=indicators,
            warnings=[first_warning, second_warning],
        ),
        arbitration=arbitration_facts(
            left_cases,
            warnings=[first_warning, second_warning],
        ),
    )
    right = complete_company_report(
        counterparty=counterparty_facts(
            warnings=[second_warning, first_warning],
        ),
        finance=finance_facts(
            list(reversed(periods)),
            indicators=list(reversed(indicators)),
            warnings=[second_warning, first_warning],
        ),
        arbitration=arbitration_facts(
            right_cases,
            warnings=[second_warning, first_warning],
        ),
    )

    left_result = evaluate_signals(left)
    right_result = evaluate_signals(right)

    assert left_result.model_dump(mode="json") == right_result.model_dump(
        mode="json"
    )
    assert canonical_representation(left_result) == canonical_representation(
        right_result
    )
    assert canonical_representation(left_result) == canonical_representation(
        evaluate_signals(left)
    )
    _assert_contract_order(left_result)
    assert len({signal.code for signal in left_result.signals}) == len(
        left_result.signals
    )


def test_evaluation_preserves_company_report_snapshot_hash_and_old_snapshot():
    report = complete_company_report()
    report_dump_before = report.model_dump(mode="json")
    snapshot_before = company_report_to_snapshot(report)
    hash_before = calculate_company_report_snapshot_hash(report)

    result = evaluate_signals(report)

    assert report.model_dump(mode="json") == report_dump_before
    assert company_report_to_snapshot(report) == snapshot_before
    assert calculate_company_report_snapshot_hash(report) == hash_before
    assert company_report_from_snapshot(snapshot_before) == report
    assert "signals" not in snapshot_before
    assert snapshot_before["report_version"] == "1"
    assert result is not report


@pytest.mark.asyncio
async def test_orchestrator_success_path_does_not_evaluate_signals_automatically(
    monkeypatch,
):
    called = False

    def unexpected_evaluation(_report):
        nonlocal called
        called = True
        raise AssertionError("orchestrator must not evaluate signals")

    monkeypatch.setattr(
        signals_package,
        "evaluate_signals",
        unexpected_evaluation,
    )
    monkeypatch.setattr(
        signal_evaluation,
        "evaluate_signals",
        unexpected_evaluation,
    )

    report = await build_company_report(
        "0000000000",
        provider=successful_fake_provider(),
    )

    assert called is False
    assert "signals" not in report.model_dump(mode="json")


def test_no_automatic_persistence_or_signal_columns():
    company_reports_root = Path(signal_evaluation.__file__).parents[1]
    persistence_root = company_reports_root / "persistence"
    persistence_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(persistence_root.glob("*.py"))
    )
    orchestrator_source = (
        company_reports_root / "orchestrator.py"
    ).read_text(encoding="utf-8")

    assert "company_reports.signals" not in persistence_source
    assert "signals.evaluation" not in persistence_source
    assert "evaluate_signals" not in persistence_source
    assert "evaluate_signals" not in orchestrator_source
    for model in (
        CompanyReportSubject,
        CompanyReportRecord,
        CompanyReportDataset,
        CompanyReportProviderRequest,
    ):
        assert "signals" not in model.__table__.columns


def test_result_is_private_scope_safe_and_evaluation_has_no_side_effect_imports():
    result = evaluate_signals(complete_company_report())
    serialized = json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
    )
    production_source = Path(signal_evaluation.__file__).read_text(
        encoding="utf-8"
    )

    assert "raw_payload" not in serialized
    assert "api-secret" not in serialized
    assert "0000000000" not in serialized
    assert "finance.reporting_absent" not in serialized
    assert set(SignalEvaluationResult.model_fields).isdisjoint(
        {
            "score",
            "verdict",
            "probability",
            "recommendation",
        }
    )
    for forbidden_import in (
        "fastapi",
        "httpx",
        "sqlalchemy",
        "company_reports.persistence",
        "product_api.providers",
    ):
        assert forbidden_import not in production_source
    for forbidden_runtime in (
        "datetime.now",
        "date.today",
        "random",
        "uuid",
        "os.environ",
        "getenv",
        "open(",
    ):
        assert forbidden_runtime not in production_source
