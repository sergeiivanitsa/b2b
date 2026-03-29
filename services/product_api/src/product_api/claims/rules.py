from typing import Any

from .extraction import build_empty_normalized_data, build_missing_fields

ALL_PREVIEW_BLOCKS = [
    "header",
    "facts",
    "debt_calculation",
    "legal_basis",
    "demands",
    "attachments",
    "penalty_section",
]

MANUAL_REVIEW_RISK_FLAGS = {
    "case_type_uncertain",
    "contract_status_uncertain",
    "no_supporting_documents",
    "high_claim_amount",
}

BLOCKED_BLOCKS_BY_RISK = {
    "case_type_uncertain": ["legal_basis"],
    "contract_status_uncertain": ["penalty_section"],
    "no_supporting_documents": ["attachments"],
    "high_claim_amount": [],
}


def evaluate_claim_rules(
    *,
    case_type: str | None,
    normalized_data: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = _normalize_claim_data(normalized_data)
    missing_fields = normalized["missing_fields"]
    risk_flags = _collect_risk_flags(case_type=case_type, normalized_data=normalized)

    if missing_fields:
        generation_state = "insufficient_data"
    elif any(flag in MANUAL_REVIEW_RISK_FLAGS for flag in risk_flags):
        generation_state = "manual_review_required"
    else:
        generation_state = "ready"

    blocked_blocks = _compute_blocked_blocks(risk_flags)
    allowed_blocks = [block for block in ALL_PREVIEW_BLOCKS if block not in blocked_blocks]
    return {
        "generation_state": generation_state,
        "risk_flags": risk_flags,
        "allowed_blocks": allowed_blocks,
        "blocked_blocks": blocked_blocks,
        "missing_fields": missing_fields,
    }


def _normalize_claim_data(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = build_empty_normalized_data()
    if isinstance(payload, dict):
        for key in normalized:
            if key == "missing_fields":
                continue
            if key in payload:
                normalized[key] = payload[key]
    normalized["missing_fields"] = build_missing_fields(normalized)
    return normalized


def _collect_risk_flags(
    *,
    case_type: str | None,
    normalized_data: dict[str, Any],
) -> list[str]:
    risk_flags: list[str] = []
    if case_type is None:
        risk_flags.append("case_type_uncertain")

    if normalized_data.get("contract_signed") is not True:
        risk_flags.append("contract_status_uncertain")

    documents = normalized_data.get("documents_mentioned")
    if not isinstance(documents, list) or len(documents) == 0:
        risk_flags.append("no_supporting_documents")

    debt_amount = normalized_data.get("debt_amount")
    if isinstance(debt_amount, (int, float)) and not isinstance(debt_amount, bool):
        if debt_amount >= 5_000_000:
            risk_flags.append("high_claim_amount")

    deduped: list[str] = []
    for flag in risk_flags:
        if flag not in deduped:
            deduped.append(flag)
    return deduped


def _compute_blocked_blocks(risk_flags: list[str]) -> list[str]:
    blocked: list[str] = []
    for flag in risk_flags:
        for block_name in BLOCKED_BLOCKS_BY_RISK.get(flag, []):
            if block_name not in blocked:
                blocked.append(block_name)
    return blocked
