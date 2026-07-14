from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from product_api.company_reports import (
    CompanyReport,
    CompanyReportCompleteness,
    CompanyReportStatus,
    CounterpartyFacts,
    DatasetReport,
    DatasetReportStatus,
    NormalizationWarning,
    ReportFreshness,
    SafeDatasetError,
    SourceMetadata,
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
