from __future__ import annotations

import copy
import json
from pathlib import Path
from uuid import UUID

import pytest

from product_api.company_reports.company_card_v2.decimal_transport import (
    DecimalTransportError,
    parse_source_decimal,
)
from product_api.company_reports.company_card_v2.canonical_json import canonical_json_bytes
from product_api.company_reports.company_card_v2.canonical_json import canonical_digest
from product_api.company_reports.company_card_v2.models import (
    CompanyCardV2Snapshot,
    CompanyCardV2SnapshotV1,
    CompanyCardV2SnapshotV2,
    CompanyCardV2SnapshotV3,
)
from product_api.company_reports.company_card_v2.public_h2 import build_public_h2
from product_api.company_reports.company_card_v2.public_h2_models import (
    CompanyPublicH2Response,
    PublicH2Narrative,
)
from product_api.company_reports.persistence.v3 import (
    CompanyReportSnapshotError,
    calculate_company_card_v2_snapshot_hash,
    company_card_v2_from_snapshot,
    company_card_v2_to_snapshot,
    validate_company_card_v2_finalization,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _json(*parts: str) -> dict[str, object]:
    return json.loads((_FIXTURES.joinpath(*parts)).read_text(encoding="utf-8"))


def test_v3_complete_and_sparse_signed_fixtures_are_strict_round_trips() -> None:
    expected = {
        "snapshot_v3_complete.json": ("bd8a44a8388779bd28b44b2990f0776d9e0b2dc219d53a8affa5db414d129f43", 1517),
        "snapshot_v3_sparse_signed.json": ("059d74f00fb56bf5214a5231f9e1a35614f7292d806a541ba24dc7aeed3e94af", 1896),
    }
    for name, (expected_hash, expected_bytes) in expected.items():
        raw = _json("company_card_v2", name)
        restored = company_card_v2_from_snapshot(raw)
        emitted = company_card_v2_to_snapshot(restored)
        assert company_card_v2_to_snapshot(company_card_v2_from_snapshot(emitted)) == emitted
        assert calculate_company_card_v2_snapshot_hash(emitted) == expected_hash
        assert len(canonical_json_bytes(emitted)) == expected_bytes
        assert emitted["report_version"] == "3"
        assert emitted["finance_basis"]["unit_policy"] == "datanewton_finance_thousand_rub_v2"
        assert emitted["chart_facts"]["unit_policy"] == "datanewton_finance_thousand_rub_v2"


def test_frozen_v3_v1_parser_never_materializes_new_discriminator_or_evidence() -> None:
    raw = _json("company_card_v2", "snapshot_v3_complete.json")
    original = copy.deepcopy(raw)

    restored = company_card_v2_from_snapshot(copy.deepcopy(raw))
    emitted = company_card_v2_to_snapshot(restored)

    assert type(restored) is CompanyCardV2SnapshotV1
    assert "snapshot_schema_version" not in emitted
    assert "narrative_evidence" not in emitted
    assert raw == original
    assert calculate_company_card_v2_snapshot_hash(emitted) == "bd8a44a8388779bd28b44b2990f0776d9e0b2dc219d53a8affa5db414d129f43"
    assert len(canonical_json_bytes(emitted)) == 1517


def test_discriminated_v3_v2_fixture_has_exact_round_trip_hash_and_bytes() -> None:
    raw = _json("company_card_v2", "snapshot_v3_narrative_v2.json")
    restored = company_card_v2_from_snapshot(copy.deepcopy(raw))
    emitted = company_card_v2_to_snapshot(restored)

    assert type(restored) is CompanyCardV2SnapshotV2
    assert company_card_v2_to_snapshot(company_card_v2_from_snapshot(emitted)) == emitted
    assert emitted["snapshot_schema_version"] == "company_card_v2_snapshot_v2"
    assert emitted["narrative_evidence"]["primary_activity"] == {
        "code": "62.01",
        "label": "Разработка компьютерного программного обеспечения",
        "is_primary": True,
    }
    assert calculate_company_card_v2_snapshot_hash(emitted) == "508bcb51730fc1745c5718583dc6118412893d7dbef7bbbf70140c8aeba2911a"
    assert len(canonical_json_bytes(emitted)) == 2077


def test_discriminated_v3_arbitration_fixture_has_exact_cjson_hash_and_bytes() -> None:
    path = _FIXTURES / "company_card_v2" / "snapshot_v3_arbitration_v3.json"
    fixture_bytes = path.read_bytes()
    fixture_cjson = fixture_bytes.rstrip(b"\r\n")
    raw = json.loads(fixture_bytes)

    restored = company_card_v2_from_snapshot(copy.deepcopy(raw))
    emitted = company_card_v2_to_snapshot(restored)
    emitted_cjson = canonical_json_bytes(emitted)

    assert type(restored) is CompanyCardV2SnapshotV3
    assert fixture_bytes in {fixture_cjson, fixture_cjson + b"\n", fixture_cjson + b"\r\n"}
    assert fixture_cjson == canonical_json_bytes(raw)
    assert emitted_cjson == fixture_cjson
    assert company_card_v2_to_snapshot(company_card_v2_from_snapshot(emitted)) == emitted
    assert emitted["snapshot_schema_version"] == "company_card_v2_snapshot_v3"
    assert emitted["arbitration_basis"]["sanitized_cases"][0] == {
        "case_id": "private-case-v2-a",
        "first_number": "A40-123/2026",
        "year": 2026,
        "role": "plaintiff",
        "outcome": "won",
        "date_start": "2026-01-02",
        "date_update": "2026-01-05",
        "duration_days": 3,
        "amount_state": "available",
        "amount": "-12.34",
        "currency_state": "rub",
        "opponent_tokens": [
            {
                "algorithm_version": "opponent_hmac_sha256_v1",
                "key_id": "active_2026",
                "value": "c247da23c29bb20cdcc5cc1c2ab259a7622ff7e7e03efad27df70cfe43d67d7d",
            }
        ],
        "limitations": [],
    }
    assert calculate_company_card_v2_snapshot_hash(emitted) == (
        "b60621a9f208ad067e6d77bd67f36acd7f64ab1c360c56f9ff254b778b9adc0b"
    )
    assert len(emitted_cjson) == 4322
    for forbidden in (
        b"RAW TARGET NAME",
        b"RAW OPPONENT NAME",
        b"7800000000",
        b"1027800000000",
        b"raw.example.invalid",
        b"inn_src",
        b"name_src",
    ):
        assert forbidden not in emitted_cjson


@pytest.mark.parametrize("discriminator", [None, True, 2, "unknown_v1", " company_card_v2_snapshot_v2"])
def test_v3_parser_rejects_unknown_or_coerced_snapshot_discriminators(discriminator: object) -> None:
    raw = _json("company_card_v2", "snapshot_v3_narrative_v2.json")
    raw["snapshot_schema_version"] = discriminator

    with pytest.raises(CompanyReportSnapshotError):
        company_card_v2_from_snapshot(raw)


def test_v1_v2_cross_shapes_fail_closed_instead_of_inferring_a_schema() -> None:
    frozen = _json("company_card_v2", "snapshot_v3_complete.json")
    frozen["snapshot_schema_version"] = "company_card_v2_snapshot_v2"
    with pytest.raises(CompanyReportSnapshotError):
        company_card_v2_from_snapshot(frozen)

    narrative = _json("company_card_v2", "snapshot_v3_narrative_v2.json")
    narrative.pop("snapshot_schema_version")
    with pytest.raises(CompanyReportSnapshotError):
        company_card_v2_from_snapshot(narrative)


@pytest.mark.parametrize(
    ("fixture_name", "tampered_discriminator"),
    (
        ("snapshot_v3_narrative_v2.json", "company_card_v2_snapshot_v3"),
        ("snapshot_v3_narrative_v2.json", "unknown_snapshot_v9"),
        ("snapshot_v3_arbitration_v3.json", "company_card_v2_snapshot_v2"),
    ),
)
def test_persistence_rejects_model_copy_discriminator_bypass(
    fixture_name: str,
    tampered_discriminator: str,
) -> None:
    snapshot = company_card_v2_from_snapshot(
        _json("company_card_v2", fixture_name)
    )
    tampered = snapshot.model_copy(
        update={"snapshot_schema_version": tampered_discriminator}
    )

    with pytest.raises(CompanyReportSnapshotError):
        company_card_v2_to_snapshot(tampered)
    with pytest.raises(CompanyReportSnapshotError):
        calculate_company_card_v2_snapshot_hash(tampered)
    with pytest.raises(CompanyReportSnapshotError):
        validate_company_card_v2_finalization(
            tampered,
            report_id=UUID(tampered.report_id),
            subject_inn=tampered.subject_inn,
            writer_profile=tampered.writer_profile,
            report_version=tampered.report_version,
            presentation_contract=tampered.presentation_contract,
            rollout_config_generation=tampered.rollout_config_generation,
        )


def test_v3_snapshot_rejects_noncanonical_writer_identity_timestamp_and_chart_facts() -> None:
    raw = _json("company_card_v2", "snapshot_v3_complete.json")
    for mutate in (
        lambda item: item.__setitem__("rollout_config_generation", 0),
        lambda item: item.__setitem__("report_id", "00000000-0000-4000-8000-00000000000A"),
        lambda item: item.__setitem__("generated_at", "2026-08-24T12:00:00+00:00"),
        lambda item: item["chart_facts"].__setitem__("hash", "a" * 64),
    ):
        changed = copy.deepcopy(raw)
        mutate(changed)
        with pytest.raises(CompanyReportSnapshotError):
            company_card_v2_from_snapshot(changed)


def test_v3_finalization_helper_requires_full_writer_tuple_and_returns_same_hash() -> None:
    snapshot = company_card_v2_from_snapshot(_json("company_card_v2", "snapshot_v3_complete.json"))
    serialized, digest = validate_company_card_v2_finalization(
        snapshot,
        report_id=UUID(snapshot.report_id),
        subject_inn=snapshot.subject_inn,
        writer_profile=snapshot.writer_profile,
        report_version=snapshot.report_version,
        presentation_contract=snapshot.presentation_contract,
        rollout_config_generation=snapshot.rollout_config_generation,
    )
    assert serialized == company_card_v2_to_snapshot(snapshot)
    assert digest == calculate_company_card_v2_snapshot_hash(snapshot)
    with pytest.raises(CompanyReportSnapshotError):
        validate_company_card_v2_finalization(
            snapshot,
            report_id=UUID(snapshot.report_id),
            subject_inn=snapshot.subject_inn,
            writer_profile=snapshot.writer_profile,
            report_version=snapshot.report_version,
            presentation_contract=snapshot.presentation_contract,
            rollout_config_generation=snapshot.rollout_config_generation + 1,
        )


def test_v2_exact_fixture_remains_legacy_parser_input() -> None:
    raw = _json("company_reports", "snapshot_v2_exact.json")
    assert raw["report_version"] == "2"
    assert {"optional_datasets", "tax_info", "bankruptcy"}.issubset(raw)
    assert "raw_payload" not in str(raw)


class _GoldenNarrativeBinding:
    narrative = PublicH2Narrative(
        mode="artifact",
        renderer_version="fixture_v1",
        description="Проверочный текст подтверждённого fixture-only narrative. " * 10,
        statement_ids=("fixture_statement",),
        render_digest="a" * 64,
    )


def _fixture_projection(version: str) -> dict[str, object]:
    snapshot = CompanyCardV2Snapshot.model_validate(
        _json("company_card_v2", "snapshot_v3_complete.json")
    )
    payload = build_public_h2(
        snapshot, narrative_binding=_GoldenNarrativeBinding()
    ).model_dump(mode="json")
    if version == "3":
        return payload
    # Legacy preview has no shipped runtime narrative source.  This is a pure
    # test-only serializer fixture that locks the already closed DTO/CJSON
    # contract without changing runtime eligibility or resolver behaviour.
    payload["report_version"] = version
    payload["snapshot_capability"] = "legacy_read_only"
    payload["projection_scope"] = "active_publication"
    payload.pop("projection_digest")
    payload["projection_digest"] = canonical_digest(payload)
    return CompanyPublicH2Response.model_validate(payload).model_dump(mode="json")


def test_public_h2_static_recursive_dto_and_cjson_goldens_are_exact() -> None:
    for version in ("1", "2", "3"):
        path = _FIXTURES / "company_card_v2" / f"public_h2_v{version}_expected.json"
        expected_bytes = path.read_bytes()
        expected = json.loads(expected_bytes)
        actual = _fixture_projection(version)
        # Files themselves are committed canonical CJSON bytes, not a small
        # surrogate header. This proves every recursive leaf plus its digest.
        assert expected == actual
        assert expected_bytes == canonical_json_bytes(expected)
        assert canonical_json_bytes(actual) == expected_bytes
        assert CompanyPublicH2Response.model_validate(expected).model_dump(mode="json") == actual


def test_finance_lexical_fixture_accepts_only_closed_decimal_grammar() -> None:
    values = _json("company_card_v2", "finance_lexical_payload.json")["values"]
    assert [parse_source_decimal(value).lexeme for value in values[:3]] == ["273325", "-12.34", "0"]
    for value in values[3:]:
        with pytest.raises(DecimalTransportError):
            parse_source_decimal(value)
