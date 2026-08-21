from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from product_api.company_reports.models import FrozenDomainModel


class ExplanationDatasetStatus(FrozenDomainModel):
    dataset: str = Field(min_length=1)
    status: str = Field(min_length=1)


class ExplanationSignal(FrozenDomainModel):
    code: str = Field(min_length=1)
    category: str = Field(min_length=1)
    direction: str = Field(min_length=1)
    strength: str = Field(min_length=1)
    confidence: str = Field(min_length=1)


class ExplanationScoring(FrozenDomainModel):
    ruleset_version: Literal["1"]
    level: str = Field(min_length=1)
    score_points: str | None = None
    confidence: str
    reason_signal_codes: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)


class CatalogStatement(FrozenDomainModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class AllowedStatementCatalog(FrozenDomainModel):
    overall_conclusions: list[CatalogStatement] = Field(default_factory=list)
    recovery_factors: list[CatalogStatement] = Field(default_factory=list)
    key_risks: list[CatalogStatement] = Field(default_factory=list)
    urgencies: list[CatalogStatement] = Field(default_factory=list)
    recommended_next_steps: list[CatalogStatement] = Field(default_factory=list)
    limitations: list[CatalogStatement] = Field(default_factory=list)

    @field_validator(
        "overall_conclusions",
        "recovery_factors",
        "key_risks",
        "urgencies",
        "recommended_next_steps",
        "limitations",
    )
    @classmethod
    def _sort_statements(cls, value: list[CatalogStatement]) -> list[CatalogStatement]:
        ids = [statement.id for statement in value]
        if len(ids) != len(set(ids)):
            raise ValueError("catalog statement ids must be unique per section")
        return sorted(value, key=lambda statement: statement.id)


class ExplanationInputEnvelope(FrozenDomainModel):
    report_version: Literal["1", "2"]
    report_status: str = Field(min_length=1)
    completeness: dict[str, object]
    dataset_statuses: list[ExplanationDatasetStatus]
    report_warning_codes: list[str] = Field(default_factory=list)
    signals: list[ExplanationSignal] = Field(default_factory=list)
    signal_warning_codes: list[str] = Field(default_factory=list)
    scoring: ExplanationScoring
    allowed_statement_catalog: AllowedStatementCatalog

    @field_validator("dataset_statuses")
    @classmethod
    def _sort_datasets(cls, value: list[ExplanationDatasetStatus]) -> list[ExplanationDatasetStatus]:
        names = [item.dataset for item in value]
        if len(names) != len(set(names)):
            raise ValueError("dataset statuses must be unique")
        return sorted(value, key=lambda item: item.dataset)

    @field_validator("report_warning_codes", "signal_warning_codes")
    @classmethod
    def _sort_codes(cls, value: list[str]) -> list[str]:
        return sorted(set(value))

    @field_validator("signals")
    @classmethod
    def _sort_signals(cls, value: list[ExplanationSignal]) -> list[ExplanationSignal]:
        codes = [signal.code for signal in value]
        if len(codes) != len(set(codes)):
            raise ValueError("signal codes must be unique")
        return sorted(value, key=lambda signal: (signal.category, signal.code))


class ExplanationSelection(FrozenDomainModel):
    output_schema_version: Literal["1"]
    overall_conclusion_id: str = Field(min_length=1)
    recovery_factor_ids: list[str] = Field(default_factory=list, max_length=3)
    key_risk_ids: list[str] = Field(default_factory=list, max_length=3)
    urgency_id: str = Field(min_length=1)
    recommended_next_step_id: str = Field(min_length=1)
    limitation_ids: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("recovery_factor_ids", "key_risk_ids", "limitation_ids")
    @classmethod
    def _sort_selected_ids(cls, value: list[str]) -> list[str]:
        return sorted(value)

    @model_validator(mode="after")
    def _unique_ids(self) -> "ExplanationSelection":
        for field_name in (
            "recovery_factor_ids",
            "key_risk_ids",
            "limitation_ids",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        return self


class AIExplanation(FrozenDomainModel):
    output_schema_version: Literal["1"]
    overall_conclusion: str
    recovery_factors: list[str]
    key_risks: list[str]
    urgency: str
    recommended_next_step: str
    limitations: list[str]
    prompt_version: str
    model_profile: str
    resolved_model: str
    attempt_count: Literal[1, 2]


class AIExplanationStatus(StrEnum):
    OK = "ok"
    TRANSPORT_FAILURE = "transport_failure"
    INVALID_RESPONSE = "invalid_response"
    CONFIGURATION_ERROR = "configuration_error"


class AIExplanationFailure(FrozenDomainModel):
    safe_code: str = Field(min_length=1)
    model_profile: str
    prompt_version: str
    output_schema_version: Literal["1"]
    retry_attempted: bool


class AIExplanationResult(FrozenDomainModel):
    status: AIExplanationStatus
    explanation: AIExplanation | None = None
    failure: AIExplanationFailure | None = None

    @model_validator(mode="after")
    def _success_or_failure_only(self) -> "AIExplanationResult":
        success = self.status is AIExplanationStatus.OK
        if success != (self.explanation is not None) or success == (self.failure is not None):
            raise ValueError("result must contain exactly its matching success or failure payload")
        return self
