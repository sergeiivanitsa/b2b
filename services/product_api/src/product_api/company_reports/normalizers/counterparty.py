from __future__ import annotations

from typing import Any

from product_api.company_reports.errors import InvalidDatasetPayloadError
from product_api.company_reports.models import (
    CompanyAddress,
    CompanyManager,
    CompanyNames,
    CompanyStatus,
    CounterpartyBlockStatus,
    CounterpartyFacts,
    NormalizationWarning,
    TaxModeInfo,
)
from product_api.providers.datanewton import COUNTERPARTY_ENDPOINT, DataNewtonResult

from .common import (
    optional_bool,
    optional_string,
    parse_date,
    parse_decimal,
    source_metadata,
    validate_result,
    warning,
)

_BLOCKS: dict[str, tuple[str, str, tuple[type[Any], ...]]] = {
    "address": ("ADDRESS_BLOCK", "address", (dict,)),
    "managers": ("MANAGER_BLOCK", "managers", (list,)),
    "owners": ("OWNER_BLOCK", "owners", (dict, list)),
    "okved": ("OKVED_BLOCK", "okveds", (list, dict)),
    "negative_lists": ("NEGATIVE_LISTS_BLOCK", "negative_lists", (list, dict)),
    "workers_count": ("WORKERS_COUNT_BLOCK", "workers_count", (int, dict, list)),
    "contacts": ("CONTACT_BLOCK", "contacts", (dict, list)),
    "branches": ("BRANCHES_BLOCK", "branches", (list, dict)),
    "msp": ("MSP_BLOCK", "msp_block", (dict, list)),
    "rosstat": ("ROSSTAT_BLOCK", "ros_stat_codes", (dict, list)),
}


def normalize_counterparty(result: DataNewtonResult) -> CounterpartyFacts:
    payload = validate_result(
        result,
        expected_dataset="counterparty",
        expected_endpoint=COUNTERPARTY_ENDPOINT,
    )
    company = payload.get("company")
    if not isinstance(company, dict):
        raise InvalidDatasetPayloadError(
            "counterparty payload must contain a company object",
            dataset=result.dataset,
            endpoint=result.endpoint,
        )

    warnings: list[NormalizationWarning] = []
    requested_filters = _requested_filters(result.request_parameters.get("filters"))
    requested_filter_set = set(requested_filters)
    block_statuses = {
        name: _block_status(
            company=company,
            block_name=name,
            requested_filter=provider_filter,
            payload_key=payload_key,
            expected_types=expected_types,
            requested_filters=requested_filter_set,
            warnings=warnings,
        )
        for name, (provider_filter, payload_key, expected_types) in _BLOCKS.items()
    }

    names_payload = company.get("company_names")
    if names_payload is not None and not isinstance(names_payload, dict):
        warnings.append(
            warning(
                "counterparty_names_invalid",
                "$.company.company_names",
                "company_names block must be an object",
            )
        )
        names_payload = None
    names = (
        CompanyNames(
            short_name=optional_string(names_payload.get("short_name")),
            full_name=optional_string(names_payload.get("full_name")),
        )
        if isinstance(names_payload, dict)
        else None
    )

    status_payload = company.get("status")
    if status_payload is not None and not isinstance(status_payload, dict):
        warnings.append(
            warning(
                "counterparty_status_invalid",
                "$.company.status",
                "status block must be an object",
            )
        )
        status_payload = None
    status = (
        CompanyStatus(
            is_active=optional_bool(status_payload.get("active_status")),
            code=optional_string(status_payload.get("code_egr")),
            text=optional_string(
                status_payload.get("status_rus_short")
                or status_payload.get("status_egr")
            ),
        )
        if isinstance(status_payload, dict)
        else None
    )

    address = _address(company.get("address"), warnings)
    managers = _managers(company.get("managers"), warnings)
    tax_modes = _tax_modes(company.get("tax_mode_info"), warnings)
    registration_date = parse_date(
        company.get("registration_date"),
        path="$.company.registration_date",
        warnings=warnings,
    )
    dissolved_date = parse_date(
        company.get("dissolved_date"),
        path="$.company.dissolved_date",
        warnings=warnings,
    )
    charter_capital = parse_decimal(
        company.get("charter_capital"),
        path="$.company.charter_capital",
        warnings=warnings,
    )

    source = source_metadata(result, warnings)
    return CounterpartyFacts(
        source=source,
        inn=optional_string(payload.get("inn") or company.get("inn")),
        ogrn=optional_string(payload.get("ogrn") or company.get("ogrn")),
        kpp=optional_string(company.get("kpp")),
        short_name=names.short_name if names else None,
        full_name=names.full_name if names else None,
        names=names,
        legal_form=optional_string(company.get("opf")),
        is_active=status.is_active if status else None,
        status_code=status.code if status else None,
        status_text=status.text if status else None,
        status=status,
        registration_date=registration_date,
        dissolved_date=dissolved_date,
        years_from_registration=_optional_int(company.get("years_from_registration")),
        charter_capital=charter_capital,
        address=address,
        managers=managers,
        tax_modes=tax_modes,
        requested_filters=requested_filters,
        block_statuses=block_statuses,
        warnings=source.warnings,
    )


def _requested_filters(value: object) -> list[str]:
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, (list, tuple)):
        candidates = [item for item in value if isinstance(item, str)]
    else:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _block_status(
    *,
    company: dict[str, Any],
    block_name: str,
    requested_filter: str,
    payload_key: str,
    expected_types: tuple[type[Any], ...],
    requested_filters: set[str],
    warnings: list[NormalizationWarning],
) -> CounterpartyBlockStatus:
    if requested_filter not in requested_filters:
        return CounterpartyBlockStatus.NOT_REQUESTED
    value = company.get(payload_key)
    if value is None or value == [] or value == {}:
        return CounterpartyBlockStatus.AVAILABLE_EMPTY
    if isinstance(value, bool) and bool not in expected_types:
        valid_type = False
    else:
        valid_type = isinstance(value, expected_types)
    if valid_type:
        return CounterpartyBlockStatus.AVAILABLE
    warnings.append(
        warning(
            "counterparty_block_invalid",
            f"$.company.{payload_key}",
            f"requested {block_name} block has an unexpected type",
        )
    )
    return CounterpartyBlockStatus.INVALID


def _address(
    value: object,
    warnings: list[NormalizationWarning],
) -> CompanyAddress | None:
    if value in (None, {}, []):
        return None
    if not isinstance(value, dict):
        return None
    return CompanyAddress(
        line_address=optional_string(value.get("line_address")),
        country=optional_string(value.get("country")),
        region=optional_string(value.get("region")),
        region_code=optional_string(value.get("region_code")),
        city=optional_string(value.get("city")),
        street=optional_string(value.get("street")),
        house=optional_string(value.get("house")),
        office=optional_string(value.get("office")),
        zip_code=optional_string(value.get("zip_code")),
        is_inaccuracy=optional_bool(value.get("is_inaccuracy")),
    )


def _managers(
    value: object,
    warnings: list[NormalizationWarning],
) -> list[CompanyManager]:
    if not isinstance(value, list):
        return []
    managers: list[CompanyManager] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            warnings.append(
                warning(
                    "counterparty_manager_invalid",
                    f"$.company.managers[{index}]",
                    "manager entry must be an object",
                )
            )
            continue
        managers.append(
            CompanyManager(
                full_name=optional_string(item.get("fio") or item.get("full_name")),
                position=optional_string(item.get("position")),
                innfl=optional_string(item.get("innfl")),
                appointed_at=parse_date(
                    item.get("date") or item.get("appointed_at"),
                    path=f"$.company.managers[{index}].date",
                    warnings=warnings,
                ),
                is_inaccuracy=optional_bool(item.get("is_inaccuracy")),
            )
        )
    return managers


def _tax_modes(
    value: object,
    warnings: list[NormalizationWarning],
) -> TaxModeInfo | None:
    if value in (None, {}, []):
        return None
    if not isinstance(value, dict):
        warnings.append(
            warning(
                "counterparty_tax_modes_invalid",
                "$.company.tax_mode_info",
                "tax_mode_info block must be an object",
            )
        )
        return None
    return TaxModeInfo(
        common_mode=optional_bool(value.get("common_mode")),
        usn_sign=optional_bool(value.get("usn_sign")),
        ausn_sign=optional_bool(value.get("ausn_sign")),
        envd_sign=optional_bool(value.get("envd_sign")),
        eshn_sign=optional_bool(value.get("eshn_sign")),
        npd_sign=optional_bool(value.get("npd_sign")),
        psn_sign=optional_bool(value.get("psn_sign")),
        srp_sign=optional_bool(value.get("srp_sign")),
        publication_date=parse_date(
            value.get("publication_date"),
            path="$.company.tax_mode_info.publication_date",
            warnings=warnings,
        ),
    )


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
