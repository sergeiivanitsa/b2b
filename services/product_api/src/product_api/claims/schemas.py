from typing import Any

from pydantic import BaseModel, ConfigDict


class PartialPaymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Any | None = None
    date: Any | None = None


class NormalizedDataPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    creditor_name: Any | None = None
    debtor_name: Any | None = None
    contract_signed: Any | None = None
    contract_number: Any | None = None
    contract_date: Any | None = None
    debt_amount: Any | None = None
    payment_due_date: Any | None = None
    partial_payments_present: Any | None = None
    partial_payments: list[PartialPaymentIn] | None = None
    penalty_exists: Any | None = None
    penalty_rate_text: Any | None = None
    documents_mentioned: list[Any] | None = None


class ClaimPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_email: Any | None = None
    client_phone: Any | None = None
    case_type: Any | None = None
    normalized_data: NormalizedDataPatchIn | None = None


class ClaimContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_email: Any
    client_phone: Any | None = None


class Step2DerivedOut(BaseModel):
    total_paid_amount: int | float
    remaining_debt_amount: int | float | None
    overdue_days: int | None
    is_overdue: bool | None


class Step2ConditionalVisibilityOut(BaseModel):
    show_partial_payments: bool
    show_penalty_rate: bool


class Step2Out(BaseModel):
    always_visible_fields: list[str]
    conditional_visibility: Step2ConditionalVisibilityOut
    missing_fields: list[str]
    derived: Step2DerivedOut


class ClaimPreviewOut(BaseModel):
    claim_id: int
    generation_state: str
    manual_review_required: bool
    risk_flags: list[str]
    allowed_blocks: list[str]
    blocked_blocks: list[str]
    generated_preview_text: str
    missing_fields: list[str]
