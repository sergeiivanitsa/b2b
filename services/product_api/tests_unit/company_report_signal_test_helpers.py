from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from product_api.company_reports import (
    ArbitrationCaseFacts,
    ArbitrationFacts,
    ArbitrationResultType,
    ArbitrationRole,
    ArbitrationStatus,
    CompanyReport,
    CompanyReportCompleteness,
    CompanyReportStatus,
    CounterpartyFacts,
    DatasetReport,
    DatasetReportStatus,
    FinanceFacts,
    FinanceForm,
    FinancialIndicatorSeries,
    FinancialPeriod,
    NormalizationWarning,
    ReportFreshness,
    ResultSummary,
    RoleSummary,
    SafeDatasetError,
    SourceMetadata,
    StatusSummary,
)
from product_api.company_reports.signals import (
    EqualityOperator,
    LiteralOperand,
    PredicateExpression,
    PresenceOperator,
    Signal,
    SignalCategory,
    SignalConfidence,
    SignalDirection,
    SignalFact,
    SignalFactualBasis,
    SignalPeriodBasis,
    SignalPeriodOperation,
    SignalStrength,
    SignalStrengthDecision,
    YearPeriod,
)
from product_api.providers.datanewton import DataNewtonIdentifierType


RECEIVED_AT = datetime(2026, 1, 10, 12, 30, tzinfo=timezone.utc)


def signal_source(
    *,
    warnings: list[NormalizationWarning] | None = None,
    received_at: datetime = RECEIVED_AT,
) -> SourceMetadata:
    return SourceMetadata(
        provider="datanewton",
        dataset="counterparty",
        endpoint="/v1/counterparty",
        response_hash="a" * 64,
        received_at=received_at,
        request_id="safe-request",
        status_code=200,
        attempts=1,
        duration_ms=Decimal("1.25"),
        warnings=warnings or [],
    )


def arbitration_source(
    *,
    warnings: list[NormalizationWarning] | None = None,
    received_at: datetime = RECEIVED_AT,
) -> SourceMetadata:
    return SourceMetadata(
        provider="datanewton",
        dataset="arbitration_cases",
        endpoint="/v1/arbitration-cases",
        response_hash="c" * 64,
        received_at=received_at,
        request_id="safe-arbitration-request",
        status_code=200,
        attempts=1,
        duration_ms=Decimal("2.50"),
        warnings=warnings or [],
    )


def finance_source(
    *,
    warnings: list[NormalizationWarning] | None = None,
    received_at: datetime = RECEIVED_AT,
) -> SourceMetadata:
    return SourceMetadata(
        provider="datanewton",
        dataset="finance",
        endpoint="/v1/finance",
        response_hash="f" * 64,
        received_at=received_at,
        request_id="safe-finance-request",
        status_code=200,
        attempts=1,
        duration_ms=Decimal("1.75"),
        warnings=warnings or [],
    )


def finance_facts(
    periods: list[FinancialPeriod] | None = None,
    *,
    indicators: list[FinancialIndicatorSeries] | None = None,
    warnings: list[NormalizationWarning] | None = None,
) -> FinanceFacts:
    normalized_periods = periods or []
    normalized_warnings = warnings or []
    years = sorted({period.year for period in normalized_periods})
    return FinanceFacts(
        source=finance_source(warnings=normalized_warnings),
        years=years,
        latest_year=years[-1] if years else None,
        indicators=indicators or [],
        periods=normalized_periods,
        warnings=normalized_warnings,
    )


def finance_indicator(
    form: FinanceForm,
    code: str,
    *,
    source_path: str | None = None,
    source_paths: list[str] | None = None,
    values_by_year: dict[int, Decimal | None] | None = None,
    name: str | None = None,
) -> FinancialIndicatorSeries:
    return FinancialIndicatorSeries(
        form=form,
        code=code,
        name=name,
        values_by_year=values_by_year or {},
        source_paths=(
            source_paths
            if source_paths is not None
            else [source_path]
            if source_path is not None
            else []
        ),
    )


def arbitration_case(
    case_id: str | None,
    *,
    internal_id: str | None = None,
    year: int | None = 2025,
    roles: list[ArbitrationRole] | None = None,
    status: ArbitrationStatus = ArbitrationStatus.COMPLETED,
) -> ArbitrationCaseFacts:
    return ArbitrationCaseFacts(
        internal_id=internal_id,
        case_number=case_id,
        year=year,
        normalized_status=status,
        normalized_result_type=ArbitrationResultType.OTHER,
        company_roles=(
            [ArbitrationRole.RESPONDENT]
            if roles is None
            else roles
        ),
    )


def _role_summary(cases: list[ArbitrationCaseFacts]) -> RoleSummary:
    counts = {
        ArbitrationRole.PLAINTIFF: 0,
        ArbitrationRole.RESPONDENT: 0,
        ArbitrationRole.APPLICANT: 0,
        ArbitrationRole.CREDITOR: 0,
        ArbitrationRole.DEBTOR: 0,
    }
    other_count = 0
    unknown_count = 0
    for case in cases:
        roles = set(case.company_roles)
        for role in counts:
            if role in roles:
                counts[role] += 1
        if roles.intersection(
            {
                ArbitrationRole.THIRD_PARTY,
                ArbitrationRole.INTERESTED_PERSON,
                ArbitrationRole.OTHER,
            }
        ):
            other_count += 1
        if not roles or roles == {ArbitrationRole.UNKNOWN}:
            unknown_count += 1
    return RoleSummary(
        plaintiff_count=counts[ArbitrationRole.PLAINTIFF],
        respondent_count=counts[ArbitrationRole.RESPONDENT],
        applicant_count=counts[ArbitrationRole.APPLICANT],
        creditor_count=counts[ArbitrationRole.CREDITOR],
        debtor_count=counts[ArbitrationRole.DEBTOR],
        other_count=other_count,
        unknown_count=unknown_count,
    )


def _status_summary(cases: list[ArbitrationCaseFacts]) -> StatusSummary:
    return StatusSummary(
        open_count=sum(
            case.normalized_status is ArbitrationStatus.OPEN for case in cases
        ),
        completed_count=sum(
            case.normalized_status is ArbitrationStatus.COMPLETED for case in cases
        ),
        unknown_count=sum(
            case.normalized_status is ArbitrationStatus.UNKNOWN for case in cases
        ),
    )


def arbitration_facts(
    cases: list[ArbitrationCaseFacts] | None = None,
    *,
    is_complete: bool = True,
    role_summary: RoleSummary | None = None,
    status_summary: StatusSummary | None = None,
    warnings: list[NormalizationWarning] | None = None,
) -> ArbitrationFacts:
    normalized_cases = cases or []
    normalized_warnings = warnings or []
    return ArbitrationFacts(
        source=arbitration_source(warnings=normalized_warnings),
        total_cases=len(normalized_cases),
        returned_cases=len(normalized_cases),
        offset=0,
        limit=max(len(normalized_cases), 1),
        is_complete=is_complete,
        cases=normalized_cases,
        role_summary=role_summary or _role_summary(normalized_cases),
        status_summary=status_summary or _status_summary(normalized_cases),
        result_summary=ResultSummary(other_count=len(normalized_cases)),
        warnings=normalized_warnings,
    )


def counterparty_facts(
    *,
    is_active: bool | None = True,
    dissolved_date: date | None = None,
    registration_date: date | None = date(2021, 1, 10),
    years_from_registration: int | None = 5,
    warnings: list[NormalizationWarning] | None = None,
    received_at: datetime = RECEIVED_AT,
) -> CounterpartyFacts:
    normalized_warnings = warnings or []
    source = signal_source(warnings=normalized_warnings, received_at=received_at)
    return CounterpartyFacts(
        source=source,
        is_active=is_active,
        dissolved_date=dissolved_date,
        registration_date=registration_date,
        years_from_registration=years_from_registration,
        warnings=normalized_warnings,
    )


def _unavailable_dataset(dataset: str) -> DatasetReport:
    return DatasetReport(
        dataset=dataset,
        status=DatasetReportStatus.DISABLED,
        error=SafeDatasetError(
            error_type="disabled",
            message="Dataset is disabled.",
        ),
    )


def company_report(
    *,
    counterparty: CounterpartyFacts | None = None,
    counterparty_status: DatasetReportStatus = DatasetReportStatus.AVAILABLE,
) -> CompanyReport:
    facts = counterparty if counterparty is not None else counterparty_facts()
    if counterparty_status is DatasetReportStatus.AVAILABLE:
        counterparty_dataset = DatasetReport(
            dataset="counterparty",
            status=counterparty_status,
            source=facts.source,
        )
        available_count = 1
        report_status = CompanyReportStatus.PARTIAL
    else:
        counterparty_dataset = DatasetReport(
            dataset="counterparty",
            status=counterparty_status,
            error=SafeDatasetError(
                error_type=counterparty_status.value,
                message="Counterparty dataset is unavailable.",
            ),
        )
        available_count = 0
        report_status = CompanyReportStatus.FAILED
    datasets = {
        "counterparty": counterparty_dataset,
        "finance": _unavailable_dataset("finance"),
        "arbitration": _unavailable_dataset("arbitration"),
    }
    return CompanyReport(
        report_id=UUID("00000000-0000-0000-0000-000000000001"),
        generated_at=RECEIVED_AT,
        target_identifier="0000000000",
        target_identifier_type=DataNewtonIdentifierType.LEGAL_ENTITY_INN,
        status=report_status,
        counterparty=facts if counterparty_status is DatasetReportStatus.AVAILABLE else None,
        datasets=datasets,
        completeness=CompanyReportCompleteness(
            required_datasets=("counterparty", "finance", "arbitration"),
            available_datasets=["counterparty"] if available_count else [],
            missing_datasets=["finance", "arbitration"],
            unavailable_datasets=(
                ["finance", "arbitration"]
                if available_count
                else ["counterparty", "finance", "arbitration"]
            ),
            available_count=available_count,
            required_count=3,
            ratio=Decimal(available_count) / Decimal(3),
            percent=33 if available_count else 0,
            identity_available=bool(available_count),
            financial_data_available=False,
            arbitration_data_available=False,
        ),
        freshness=ReportFreshness(generated_at=RECEIVED_AT),
        usable_for_public_page=bool(available_count),
        usable_for_future_scoring=False,
    )


def report_without_counterparty_facts() -> CompanyReport:
    report = company_report()
    return CompanyReport.model_validate(
        {**report.model_dump(mode="python"), "counterparty": None}
    )


def arbitration_company_report(
    *,
    arbitration: ArbitrationFacts | None = None,
    arbitration_status: DatasetReportStatus = DatasetReportStatus.AVAILABLE,
) -> CompanyReport:
    facts = arbitration if arbitration is not None else arbitration_facts()
    if arbitration_status is DatasetReportStatus.AVAILABLE:
        arbitration_dataset = DatasetReport(
            dataset="arbitration",
            status=arbitration_status,
            source=facts.source,
        )
        available_count = 1
        report_status = CompanyReportStatus.PARTIAL
    else:
        arbitration_dataset = DatasetReport(
            dataset="arbitration",
            status=arbitration_status,
            error=SafeDatasetError(
                error_type=arbitration_status.value,
                message="Arbitration dataset is unavailable.",
            ),
        )
        available_count = 0
        report_status = CompanyReportStatus.FAILED
    datasets = {
        "counterparty": _unavailable_dataset("counterparty"),
        "finance": _unavailable_dataset("finance"),
        "arbitration": arbitration_dataset,
    }
    return CompanyReport(
        report_id=UUID("00000000-0000-0000-0000-000000000002"),
        generated_at=RECEIVED_AT,
        target_identifier="0000000000",
        target_identifier_type=DataNewtonIdentifierType.LEGAL_ENTITY_INN,
        status=report_status,
        arbitration=(
            facts if arbitration_status is DatasetReportStatus.AVAILABLE else None
        ),
        datasets=datasets,
        completeness=CompanyReportCompleteness(
            required_datasets=("counterparty", "finance", "arbitration"),
            available_datasets=["arbitration"] if available_count else [],
            missing_datasets=["counterparty", "finance"],
            unavailable_datasets=(
                ["counterparty", "finance"]
                if available_count
                else ["counterparty", "finance", "arbitration"]
            ),
            available_count=available_count,
            required_count=3,
            ratio=Decimal(available_count) / Decimal(3),
            percent=33 if available_count else 0,
            identity_available=False,
            financial_data_available=False,
            arbitration_data_available=bool(available_count),
        ),
        freshness=ReportFreshness(generated_at=RECEIVED_AT),
        usable_for_public_page=False,
        usable_for_future_scoring=False,
    )


def report_without_arbitration_facts() -> CompanyReport:
    report = arbitration_company_report()
    return CompanyReport.model_validate(
        {**report.model_dump(mode="python"), "arbitration": None}
    )


def finance_company_report(
    *,
    finance: FinanceFacts | None = None,
    finance_status: DatasetReportStatus = DatasetReportStatus.AVAILABLE,
) -> CompanyReport:
    facts = finance if finance is not None else finance_facts()
    if finance_status is DatasetReportStatus.AVAILABLE:
        finance_dataset = DatasetReport(
            dataset="finance",
            status=finance_status,
            source=facts.source,
        )
        available_count = 1
        report_status = CompanyReportStatus.PARTIAL
    else:
        finance_dataset = DatasetReport(
            dataset="finance",
            status=finance_status,
            error=SafeDatasetError(
                error_type=finance_status.value,
                message="Finance dataset is unavailable.",
            ),
        )
        available_count = 0
        report_status = CompanyReportStatus.FAILED
    datasets = {
        "counterparty": _unavailable_dataset("counterparty"),
        "finance": finance_dataset,
        "arbitration": _unavailable_dataset("arbitration"),
    }
    return CompanyReport(
        report_id=UUID("00000000-0000-0000-0000-000000000003"),
        generated_at=RECEIVED_AT,
        target_identifier="0000000000",
        target_identifier_type=DataNewtonIdentifierType.LEGAL_ENTITY_INN,
        status=report_status,
        finance=facts if finance_status is DatasetReportStatus.AVAILABLE else None,
        datasets=datasets,
        completeness=CompanyReportCompleteness(
            required_datasets=("counterparty", "finance", "arbitration"),
            available_datasets=["finance"] if available_count else [],
            missing_datasets=["counterparty", "arbitration"],
            unavailable_datasets=(
                ["counterparty", "arbitration"]
                if available_count
                else ["counterparty", "finance", "arbitration"]
            ),
            available_count=available_count,
            required_count=3,
            ratio=Decimal(available_count) / Decimal(3),
            percent=33 if available_count else 0,
            identity_available=False,
            financial_data_available=bool(available_count),
            arbitration_data_available=False,
        ),
        freshness=ReportFreshness(generated_at=RECEIVED_AT),
        usable_for_public_page=False,
        usable_for_future_scoring=False,
    )


def complete_company_report(
    *,
    counterparty: CounterpartyFacts | None = None,
    finance: FinanceFacts | None = None,
    arbitration: ArbitrationFacts | None = None,
) -> CompanyReport:
    normalized_counterparty = counterparty or counterparty_facts()
    normalized_finance = finance or finance_facts(
        [
            FinancialPeriod(
                year=2024,
                revenue=Decimal("200"),
            ),
            FinancialPeriod(
                year=2025,
                current_assets=Decimal("100"),
                cash_and_equivalents=Decimal("10"),
                equity=Decimal("-1"),
                short_term_liabilities=Decimal("100"),
                accounts_payable=Decimal("200"),
                revenue=Decimal("100"),
                net_profit=Decimal("-1"),
            ),
        ]
    )
    arbitration_cases = [
        *[
            arbitration_case(f"R-2024-{index}", year=2024)
            for index in range(3)
        ],
        *[
            arbitration_case(
                f"R-2025-{index}",
                year=2025,
                status=(
                    ArbitrationStatus.OPEN
                    if index == 0
                    else ArbitrationStatus.COMPLETED
                ),
            )
            for index in range(7)
        ],
    ]
    normalized_arbitration = arbitration or arbitration_facts(arbitration_cases)
    datasets = {
        "counterparty": DatasetReport(
            dataset="counterparty",
            status=DatasetReportStatus.AVAILABLE,
            source=normalized_counterparty.source,
        ),
        "finance": DatasetReport(
            dataset="finance",
            status=DatasetReportStatus.AVAILABLE,
            source=normalized_finance.source,
        ),
        "arbitration": DatasetReport(
            dataset="arbitration",
            status=DatasetReportStatus.AVAILABLE,
            source=normalized_arbitration.source,
        ),
    }
    return CompanyReport(
        report_id=UUID("00000000-0000-0000-0000-000000000004"),
        generated_at=RECEIVED_AT,
        target_identifier="0000000000",
        target_identifier_type=DataNewtonIdentifierType.LEGAL_ENTITY_INN,
        status=CompanyReportStatus.COMPLETE,
        counterparty=normalized_counterparty,
        finance=normalized_finance,
        arbitration=normalized_arbitration,
        datasets=datasets,
        completeness=CompanyReportCompleteness(
            required_datasets=("counterparty", "finance", "arbitration"),
            available_datasets=["counterparty", "finance", "arbitration"],
            missing_datasets=[],
            unavailable_datasets=[],
            available_count=3,
            required_count=3,
            ratio=Decimal("1"),
            percent=100,
            identity_available=True,
            financial_data_available=True,
            arbitration_data_available=True,
        ),
        freshness=ReportFreshness(
            oldest_received_at=RECEIVED_AT,
            newest_received_at=RECEIVED_AT,
            datasets_received_at={
                "counterparty": normalized_counterparty.source.received_at,
                "finance": normalized_finance.source.received_at,
                "arbitration": normalized_arbitration.source.received_at,
            },
            generated_at=RECEIVED_AT,
            age_seconds_at_generation=Decimal("0"),
        ),
        usable_for_public_page=True,
        usable_for_future_scoring=True,
    )


def report_without_finance_facts() -> CompanyReport:
    report = finance_company_report()
    return CompanyReport.model_validate(
        {**report.model_dump(mode="python"), "finance": None}
    )


def sample_signal(
    *,
    code: str = "counterparty.sample",
    category: SignalCategory = SignalCategory.LEGAL_STATUS,
    source: list[SourceMetadata] | None = None,
) -> Signal:
    fact = SignalFact(id="count", normalized_path="derived.sample.count", exact_value=1)
    period_fact = SignalFact(
        id="year",
        normalized_path="derived.sample.year",
        exact_value=2026,
    )
    eligibility = PredicateExpression(fact_id="count", operator=PresenceOperator())
    trigger = PredicateExpression(
        fact_id="count",
        operator=EqualityOperator(operand=LiteralOperand(value=1)),
    )
    return Signal(
        code=code,
        category=category,
        direction=SignalDirection.INFORMATIONAL,
        strength=SignalStrength.LOW,
        factual_basis=SignalFactualBasis(
            facts=[fact, period_fact],
            eligibility=eligibility,
            trigger=trigger,
            strength_decision=SignalStrengthDecision(
                default_strength=SignalStrength.LOW
            ),
            period_basis=SignalPeriodBasis(
                fact_ids=["year"],
                operation=SignalPeriodOperation.YEAR,
            ),
        ),
        source=source if source is not None else [signal_source()],
        period=YearPeriod(year=2026),
        confidence=SignalConfidence.HIGH,
    )
