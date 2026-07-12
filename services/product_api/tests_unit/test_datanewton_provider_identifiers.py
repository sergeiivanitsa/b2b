import pytest
from pydantic import ValidationError

from product_api.providers.datanewton import (
    BatchCardsRequest,
    DataNewtonIdentifierType,
    DataNewtonValidationError,
    identify_identifier_type,
    normalize_identifier,
)


@pytest.mark.parametrize(
    ("raw", "normalized", "identifier_type"),
    [
        (
            "77 01-23-45-67",
            "7701234567",
            DataNewtonIdentifierType.LEGAL_ENTITY_INN,
        ),
        (
            "5001 0000 0001",
            "500100000001",
            DataNewtonIdentifierType.INDIVIDUAL_ENTREPRENEUR_INN,
        ),
        ("1-02-77-001321-9-5", "1027700132195", DataNewtonIdentifierType.OGRN),
        (
            "3 04 50 000 0000 001",
            "304500000000001",
            DataNewtonIdentifierType.OGRNIP,
        ),
    ],
)
def test_normalizes_supported_identifier_types(raw, normalized, identifier_type):
    assert normalize_identifier(raw) == normalized
    assert identify_identifier_type(raw) is identifier_type


def test_rejects_invalid_identifier_length():
    with pytest.raises(DataNewtonValidationError):
        normalize_identifier("123456789")


def test_rejects_empty_identifier():
    with pytest.raises(DataNewtonValidationError):
        normalize_identifier(" -- ")


def test_batch_request_deduplicates_after_normalization_and_preserves_order():
    request = BatchCardsRequest(
        source_inns_or_ogrns=[
            "7701-234-567",
            "1-02-77-001321-9-5",
            "7701234567",
            "1027700132195",
            "5001 0000 0001",
        ]
    )

    assert request.source_inns_or_ogrns == [
        "7701234567",
        "1027700132195",
        "500100000001",
    ]


def test_batch_request_rejects_more_than_5000_input_items():
    identifiers = [f"{value:010d}" for value in range(5001)]

    with pytest.raises(ValidationError):
        BatchCardsRequest(source_inns_or_ogrns=identifiers)
