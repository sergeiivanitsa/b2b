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
from product_api.company_reports.company_card_v2.models import CompanyCardV2Snapshot
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
