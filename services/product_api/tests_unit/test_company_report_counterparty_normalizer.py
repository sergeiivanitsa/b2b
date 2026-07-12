from datetime import date
from decimal import Decimal

from company_report_test_helpers import counterparty_result, load_fixture
from product_api.company_reports import CounterpartyBlockStatus, normalize_counterparty


def test_counterparty_normalizes_core_status_address_manager_and_tax_modes():
    facts = normalize_counterparty(counterparty_result())

    assert facts.inn == "0000000000"
    assert facts.ogrn == "0000000000000"
    assert facts.kpp == "000000000"
    assert facts.short_name == "ООО Синтетика Альфа"
    assert facts.legal_form == "Синтетическая организационная форма"
    assert facts.is_active is True
    assert facts.status_code == "SYNTH_ACTIVE"
    assert facts.registration_date == date(2020, 2, 3)
    assert facts.dissolved_date is None
    assert facts.charter_capital == Decimal("12345.67")
    assert facts.address is not None
    assert facts.address.city == "Макетный"
    assert facts.managers[0].appointed_at == date(2021, 4, 5)
    assert facts.tax_modes is not None
    assert facts.tax_modes.common_mode is True
    assert facts.tax_modes.publication_date == date(2025, 1, 15)


def test_counterparty_filters_determine_block_status_without_available_count():
    facts = normalize_counterparty(counterparty_result())

    assert facts.requested_filters == [
        "ADDRESS_BLOCK",
        "MANAGER_BLOCK",
        "OWNER_BLOCK",
        "OKVED_BLOCK",
        "WORKERS_COUNT_BLOCK",
    ]
    assert facts.block_statuses["address"] is CounterpartyBlockStatus.AVAILABLE
    assert facts.block_statuses["managers"] is CounterpartyBlockStatus.AVAILABLE
    assert facts.block_statuses["owners"] is CounterpartyBlockStatus.AVAILABLE_EMPTY
    assert facts.block_statuses["okved"] is CounterpartyBlockStatus.AVAILABLE_EMPTY
    assert facts.block_statuses["workers_count"] is CounterpartyBlockStatus.AVAILABLE_EMPTY
    assert facts.block_statuses["negative_lists"] is CounterpartyBlockStatus.NOT_REQUESTED
    assert facts.short_name is not None


def test_counterparty_requested_invalid_block_adds_warning():
    payload = load_fixture("counterparty_success.json")
    payload["company"]["address"] = "unexpected"

    facts = normalize_counterparty(
        counterparty_result(payload=payload, filters="ADDRESS_BLOCK")
    )

    assert facts.address is None
    assert facts.block_statuses["address"] is CounterpartyBlockStatus.INVALID
    assert "counterparty_block_invalid" in {item.code for item in facts.warnings}


def test_counterparty_invalid_date_is_none_with_warning():
    payload = load_fixture("counterparty_success.json")
    payload["company"]["registration_date"] = "not-a-date"

    facts = normalize_counterparty(counterparty_result(payload=payload))

    assert facts.registration_date is None
    assert "date_parse_failed" in {item.code for item in facts.warnings}


def test_counterparty_repr_hides_names_address_identifiers_and_manager_pii():
    facts = normalize_counterparty(counterparty_result())
    rendered = repr(facts)

    for sensitive_value in (
        "ООО Синтетика Альфа",
        "Тестов Тест Тестович",
        "улица Примерная",
        "0000000000",
        "000000000000",
    ):
        assert sensitive_value not in rendered
