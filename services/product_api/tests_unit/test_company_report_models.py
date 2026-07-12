import json

import pytest
from pydantic import ValidationError

from company_report_test_helpers import (
    arbitration_result,
    build_result,
    counterparty_result,
    finance_result,
    load_fixture,
)
from product_api.company_reports import (
    DatasetMismatchError,
    InvalidDatasetPayloadError,
    normalize_arbitration,
    normalize_counterparty,
    normalize_finance,
)
from product_api.providers.datanewton import DataNewtonResult


def test_dataset_and_endpoint_mismatch_raise_typed_error():
    with pytest.raises(DatasetMismatchError):
        normalize_finance(counterparty_result())

    wrong_endpoint = build_result(
        dataset="finance",
        endpoint="/v1/not-finance",
        payload=load_fixture("finance_success.json"),
    )
    with pytest.raises(DatasetMismatchError):
        normalize_finance(wrong_endpoint)


def test_invalid_root_and_dataset_payload_raise_typed_error():
    valid = finance_result()
    invalid_root = DataNewtonResult.model_construct(**{**valid.__dict__, "raw_payload": []})
    with pytest.raises(InvalidDatasetPayloadError):
        normalize_finance(invalid_root)

    invalid_company = build_result(
        dataset="counterparty",
        endpoint="/v1/counterparty",
        payload={"company": []},
    )
    with pytest.raises(InvalidDatasetPayloadError):
        normalize_counterparty(invalid_company)


def test_source_metadata_and_provider_warnings_are_preserved_safely():
    result = build_result(
        dataset="finance",
        endpoint="/v1/finance",
        payload=load_fixture("finance_success.json"),
        warnings=["synthetic provider warning"],
    )

    facts = normalize_finance(result)

    assert facts.source.provider == "datanewton"
    assert facts.source.dataset == "finance"
    assert facts.source.endpoint == "/v1/finance"
    assert facts.source.response_hash == result.response_hash
    assert facts.source.received_at == result.received_at
    assert facts.source.request_id == "synthetic-request"
    assert "provider_warning" in {item.code for item in facts.source.warnings}


@pytest.mark.parametrize(
    "facts",
    [
        normalize_counterparty(counterparty_result()),
        normalize_finance(finance_result()),
        normalize_arbitration(arbitration_result(), target_identifier="0000000000"),
    ],
)
def test_normalized_models_are_json_serializable_without_raw_payload(facts):
    dumped = facts.model_dump(mode="json")
    serialized = json.dumps(dumped, ensure_ascii=False)

    assert "raw_payload" not in serialized
    assert "available_count" not in serialized
    assert serialized


def test_models_are_frozen():
    facts = normalize_finance(finance_result())

    with pytest.raises(ValidationError):
        facts.latest_year = 1900
