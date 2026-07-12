from __future__ import annotations

import re
from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Any

from product_api.company_reports.errors import (
    CompanyReportNormalizationError,
    InvalidDatasetPayloadError,
)
from product_api.company_reports.models import (
    ArbitrationCaseFacts,
    ArbitrationClaimAmounts,
    ArbitrationDocumentSummary,
    ArbitrationFacts,
    ArbitrationParty,
    ArbitrationResultType,
    ArbitrationRole,
    ArbitrationStatus,
    NormalizationWarning,
    ResultSummary,
    RoleSummary,
    StatusSummary,
)
from product_api.providers.datanewton import (
    ARBITRATION_CASES_ENDPOINT,
    DataNewtonResult,
    normalize_identifier,
)
from product_api.providers.datanewton.errors import DataNewtonValidationError

from .common import (
    optional_string,
    parse_date,
    parse_decimal,
    parse_temporal,
    source_metadata,
    validate_result,
    warning,
)

_NON_DIGIT_RE = re.compile(r"\D+")
_PARTY_CONTAINERS: tuple[tuple[str, ArbitrationRole], ...] = (
    ("plaintiffs", ArbitrationRole.PLAINTIFF),
    ("respondents", ArbitrationRole.RESPONDENT),
    ("applicants", ArbitrationRole.APPLICANT),
    ("creditors", ArbitrationRole.CREDITOR),
    ("creditors_current_payments", ArbitrationRole.CREDITOR),
    ("debtors", ArbitrationRole.DEBTOR),
    ("interested_persons", ArbitrationRole.INTERESTED_PERSON),
    ("third_parties", ArbitrationRole.THIRD_PARTY),
    ("others", ArbitrationRole.OTHER),
)
_RESULT_TYPES = {
    "SATISFIED_FULL": ArbitrationResultType.SATISFIED_FULL,
    "REFUSED": ArbitrationResultType.REFUSED,
    "RETURNED": ArbitrationResultType.RETURNED,
    "UNDEF": ArbitrationResultType.UNDEFINED,
}


def normalize_arbitration(
    result: DataNewtonResult,
    *,
    target_identifier: str,
) -> ArbitrationFacts:
    payload = validate_result(
        result,
        expected_dataset="arbitration_cases",
        expected_endpoint=ARBITRATION_CASES_ENDPOINT,
    )
    try:
        normalized_target = normalize_identifier(target_identifier)
    except DataNewtonValidationError as exc:
        raise CompanyReportNormalizationError(
            "target identifier is invalid",
            dataset=result.dataset,
            endpoint=result.endpoint,
        ) from exc

    raw_cases = payload.get("data")
    if not isinstance(raw_cases, list):
        raise InvalidDatasetPayloadError(
            "arbitration payload must contain a data array",
            dataset=result.dataset,
            endpoint=result.endpoint,
        )

    warnings: list[NormalizationWarning] = []
    cases: list[ArbitrationCaseFacts] = []
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, dict):
            warnings.append(
                warning(
                    "arbitration_case_invalid",
                    f"$.data[{index}]",
                    "arbitration case entry must be an object",
                )
            )
            continue
        cases.append(
            _normalize_case(
                raw_case,
                index=index,
                target_identifier=normalized_target,
                warnings=warnings,
            )
        )

    total_cases = _integer(
        payload.get("total_cases"),
        default=len(raw_cases),
        path="$.total_cases",
        warnings=warnings,
    )
    offset = _integer(
        payload.get("offset", result.request_parameters.get("offset")),
        default=0,
        path="$.offset",
        warnings=warnings,
    )
    limit = _integer(
        payload.get("limit", result.request_parameters.get("limit")),
        default=len(raw_cases),
        path="$.limit",
        warnings=warnings,
    )
    role_summary = _role_summary(cases)
    status_summary = _status_summary(cases)
    result_summary = _result_summary(cases)
    amounts_by_currency, plaintiff_total, respondent_total = _claim_amounts(
        cases,
        warnings,
    )
    source = source_metadata(result, warnings)
    return ArbitrationFacts(
        source=source,
        total_cases=total_cases,
        returned_cases=len(cases),
        offset=offset,
        limit=limit,
        is_complete=offset == 0 and len(raw_cases) >= total_cases,
        cases=cases,
        role_summary=role_summary,
        status_summary=status_summary,
        result_summary=result_summary,
        claim_amount_as_plaintiff=plaintiff_total,
        claim_amount_as_respondent=respondent_total,
        claim_amounts_by_currency=amounts_by_currency,
        warnings=source.warnings,
    )


def _normalize_case(
    raw_case: dict[str, Any],
    *,
    index: int,
    target_identifier: str,
    warnings: list[NormalizationWarning],
) -> ArbitrationCaseFacts:
    path = f"$.data[{index}]"
    parties_by_container: dict[str, list[ArbitrationParty]] = {}
    company_roles: list[ArbitrationRole] = []
    for container, role in _PARTY_CONTAINERS:
        parties = _parties(raw_case.get(container), path=f"{path}.{container}", warnings=warnings)
        parties_by_container[container] = parties
        if any(_party_matches(party, target_identifier) for party in parties):
            if role not in company_roles:
                company_roles.append(role)

    documents = _documents(raw_case.get("documents"), path=path, warnings=warnings)
    declared_document_types = raw_case.get("document_types")
    document_types = {
        item for item in declared_document_types if isinstance(item, str) and item
    } if isinstance(declared_document_types, list) else set()
    document_types.update(
        item.document_type for item in documents if item.document_type is not None
    )
    last_document_date = parse_date(
        raw_case.get("last_document_date"),
        path=f"{path}.last_document_date",
        warnings=warnings,
    )
    document_dates = [
        item.creation_date for item in documents if item.creation_date is not None
    ]
    if last_document_date is not None:
        document_dates.append(last_document_date)
    raw_status = _raw_scalar(raw_case.get("status"))
    raw_result_type = optional_string(raw_case.get("result_type"))
    return ArbitrationCaseFacts(
        internal_id=optional_string(raw_case.get("id") or raw_case.get("case_id")),
        case_number=optional_string(raw_case.get("first_number")),
        date_start=parse_date(
            raw_case.get("date_start"), path=f"{path}.date_start", warnings=warnings
        ),
        date_update=parse_date(
            raw_case.get("date_update"), path=f"{path}.date_update", warnings=warnings
        ),
        updated_at=parse_temporal(
            raw_case.get("updated_at"), path=f"{path}.updated_at", warnings=warnings
        ),
        last_document_date=last_document_date,
        year=_optional_integer(raw_case.get("year")),
        claim_amount=parse_decimal(
            raw_case.get("sum"), path=f"{path}.sum", warnings=warnings
        ),
        currency=optional_string(raw_case.get("currency")),
        raw_status=raw_status,
        normalized_status=_normalize_status(raw_status),
        raw_result_type=raw_result_type,
        normalized_result_type=_RESULT_TYPES.get(
            raw_result_type.upper() if raw_result_type else "",
            ArbitrationResultType.OTHER,
        ),
        dispute_code=_raw_scalar(raw_case.get("dispute")),
        company_roles=company_roles,
        plaintiffs=parties_by_container["plaintiffs"],
        respondents=parties_by_container["respondents"],
        documents=documents,
        document_count=len(documents),
        document_types=sorted(document_types),
        latest_document_date=max(document_dates) if document_dates else None,
        kad_arbitr_link=optional_string(raw_case.get("kad_arbitr_link")),
    )


def _parties(
    value: object,
    *,
    path: str,
    warnings: list[NormalizationWarning],
) -> list[ArbitrationParty]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(
            warning("arbitration_parties_invalid", path, "party block must be an array")
        )
        return []
    parties: list[ArbitrationParty] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            warnings.append(
                warning(
                    "arbitration_party_invalid",
                    f"{path}[{index}]",
                    "party entry must be an object",
                )
            )
            continue
        parties.append(
            ArbitrationParty(
                name=optional_string(item.get("name")),
                normalized_name=optional_string(item.get("norm_name")),
                inn=optional_string(item.get("inn") or item.get("inn_src")),
                ogrn=optional_string(item.get("ogrn") or item.get("ogrn_src")),
                raw_role=optional_string(item.get("role")),
            )
        )
    return parties


def _documents(
    value: object,
    *,
    path: str,
    warnings: list[NormalizationWarning],
) -> list[ArbitrationDocumentSummary]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(
            warning(
                "arbitration_documents_invalid",
                f"{path}.documents",
                "documents block must be an array",
            )
        )
        return []
    documents: list[ArbitrationDocumentSummary] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            warnings.append(
                warning(
                    "arbitration_document_invalid",
                    f"{path}.documents[{index}]",
                    "document entry must be an object",
                )
            )
            continue
        documents.append(
            ArbitrationDocumentSummary(
                document_type=optional_string(item.get("document_type")),
                creation_date=parse_date(
                    item.get("creation_date"),
                    path=f"{path}.documents[{index}].creation_date",
                    warnings=warnings,
                ),
                instance_id=optional_string(item.get("instance_id")),
                instance_name=optional_string(item.get("instance_name")),
                instance_number=optional_string(item.get("instance_num")),
            )
        )
    return documents


def _party_matches(party: ArbitrationParty, target_identifier: str) -> bool:
    return any(
        _digits(identifier) == target_identifier
        for identifier in (party.inn, party.ogrn)
        if identifier
    )


def _digits(value: str) -> str:
    return _NON_DIGIT_RE.sub("", value)


def _normalize_status(value: int | str | None) -> ArbitrationStatus:
    if value == 0 or value == "0":
        return ArbitrationStatus.OPEN
    if value == 1 or value == "1":
        return ArbitrationStatus.COMPLETED
    return ArbitrationStatus.UNKNOWN


def _role_summary(cases: list[ArbitrationCaseFacts]) -> RoleSummary:
    counts = Counter[str]()
    for case in cases:
        roles = set(case.company_roles)
        if ArbitrationRole.PLAINTIFF in roles:
            counts["plaintiff"] += 1
        if ArbitrationRole.RESPONDENT in roles:
            counts["respondent"] += 1
        if ArbitrationRole.APPLICANT in roles:
            counts["applicant"] += 1
        if ArbitrationRole.CREDITOR in roles:
            counts["creditor"] += 1
        if ArbitrationRole.DEBTOR in roles:
            counts["debtor"] += 1
        if roles.intersection(
            {
                ArbitrationRole.THIRD_PARTY,
                ArbitrationRole.INTERESTED_PERSON,
                ArbitrationRole.OTHER,
            }
        ):
            counts["other"] += 1
        if not roles:
            counts["unknown"] += 1
    return RoleSummary(
        plaintiff_count=counts["plaintiff"],
        respondent_count=counts["respondent"],
        applicant_count=counts["applicant"],
        creditor_count=counts["creditor"],
        debtor_count=counts["debtor"],
        other_count=counts["other"],
        unknown_count=counts["unknown"],
    )


def _status_summary(cases: list[ArbitrationCaseFacts]) -> StatusSummary:
    counts = Counter(case.normalized_status for case in cases)
    return StatusSummary(
        open_count=counts[ArbitrationStatus.OPEN],
        completed_count=counts[ArbitrationStatus.COMPLETED],
        unknown_count=counts[ArbitrationStatus.UNKNOWN],
    )


def _result_summary(cases: list[ArbitrationCaseFacts]) -> ResultSummary:
    counts = Counter(case.normalized_result_type for case in cases)
    return ResultSummary(
        satisfied_full_count=counts[ArbitrationResultType.SATISFIED_FULL],
        refused_count=counts[ArbitrationResultType.REFUSED],
        returned_count=counts[ArbitrationResultType.RETURNED],
        undefined_count=counts[ArbitrationResultType.UNDEFINED],
        other_count=counts[ArbitrationResultType.OTHER],
    )


def _claim_amounts(
    cases: list[ArbitrationCaseFacts],
    warnings: list[NormalizationWarning],
) -> tuple[dict[str, ArbitrationClaimAmounts], Decimal | None, Decimal | None]:
    totals: dict[str, dict[ArbitrationRole, Decimal]] = {}
    role_currencies: dict[ArbitrationRole, set[str]] = {
        ArbitrationRole.PLAINTIFF: set(),
        ArbitrationRole.RESPONDENT: set(),
    }
    for case in cases:
        if len(case.company_roles) != 1 or case.claim_amount is None:
            continue
        role = case.company_roles[0]
        if role not in role_currencies:
            continue
        currency = (case.currency or "UNKNOWN").upper()
        role_currencies[role].add(currency)
        currency_totals = totals.setdefault(
            currency,
            {
                ArbitrationRole.PLAINTIFF: Decimal("0"),
                ArbitrationRole.RESPONDENT: Decimal("0"),
            },
        )
        currency_totals[role] += case.claim_amount

    all_currencies = set().union(*role_currencies.values())
    if len(all_currencies) > 1:
        warnings.append(
            warning(
                "arbitration_mixed_currencies",
                "$.data",
                "claim amounts use multiple currencies and were not combined",
            )
        )
    by_currency = {
        currency: ArbitrationClaimAmounts(
            plaintiff=values[ArbitrationRole.PLAINTIFF],
            respondent=values[ArbitrationRole.RESPONDENT],
        )
        for currency, values in sorted(totals.items())
    }
    plaintiff_total = _single_currency_total(
        totals, role_currencies[ArbitrationRole.PLAINTIFF], ArbitrationRole.PLAINTIFF
    )
    respondent_total = _single_currency_total(
        totals, role_currencies[ArbitrationRole.RESPONDENT], ArbitrationRole.RESPONDENT
    )
    return by_currency, plaintiff_total, respondent_total


def _single_currency_total(
    totals: dict[str, dict[ArbitrationRole, Decimal]],
    currencies: set[str],
    role: ArbitrationRole,
) -> Decimal | None:
    if len(currencies) != 1:
        return None
    currency = next(iter(currencies))
    return totals[currency][role]


def _integer(
    value: object,
    *,
    default: int,
    path: str,
    warnings: list[NormalizationWarning],
) -> int:
    parsed = _optional_integer(value)
    if parsed is not None:
        return parsed
    warnings.append(warning("integer_parse_failed", path, "integer value could not be parsed"))
    return default


def _optional_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _raw_scalar(value: object) -> int | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, str)):
        return value
    return str(value)
