from __future__ import annotations

import json
from pathlib import Path

import pytest

from product_api.company_reports.company_card_v2.counterparty import (
    COUNTERPARTY_FIELD_MANIFEST_V1,
    CounterpartyShapeError,
    parse_observed_counterparty,
)


def _payload() -> dict[str, object]:
    path = Path(__file__).parent / "fixtures" / "company_card_v2" / "counterparty_observed_shape.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_observed_counterparty_parser_releases_only_approved_core() -> None:
    core, limitations = parse_observed_counterparty(_payload())

    assert COUNTERPARTY_FIELD_MANIFEST_V1.company_path == "$.company"
    assert core.inn == "7701234567"
    assert core.full_name == "Общество с ограниченной ответственностью Синтетический контрагент"
    assert core.address_inaccuracy is False
    assert {item.field for item in limitations} == {
        "status", "legal_form", "charter_capital", "tax_modes", "okved",
        "managers", "owners", "workers", "tax_authority", "contacts",
    }


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("inn",), "not-an-inn"),
        (("company", "company_names"), "not-an-object"),
        (("company", "address", "is_inaccuracy"), "false"),
        (("company", "registration_date"), "2026-99-99"),
    ],
)
def test_observed_counterparty_parser_fails_closed_on_manifest_type_or_value(path, value) -> None:
    payload = _payload()
    target = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]

    with pytest.raises(CounterpartyShapeError):
        parse_observed_counterparty(payload)


def test_observed_counterparty_parser_discards_personal_and_contact_leaves() -> None:
    payload = _payload()
    company = payload["company"]
    company["managers"] = [{"fio": "Private", "innfl": "123456789012"}]
    company["owners"] = {"fl": [{"name": "Private", "inn": "123456789012"}]}
    company["contacts"] = {"email": "private@example.test"}

    core, _ = parse_observed_counterparty(payload)
    dumped = core.model_dump(mode="json")
    assert "innfl" not in str(dumped)
    assert "private@example.test" not in str(dumped)
