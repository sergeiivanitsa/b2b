from uuid import UUID
import json
from pathlib import Path

import pytest

from product_api.company_reports.company_card_v2.arbitration import (
    ArbitrationGateClosedError,
    build_fixture_arbitration_basis,
    collect_fixture_arbitration_pages,
    private_opponent_token,
    public_arbitration_nulls,
    require_arbitration_provider_gate,
    select_verified_alias,
    visible_case_number,
)
from product_api.company_reports.company_card_v2.evidence import EvidenceGate


def _verified_registry() -> dict[str, object]:
    return {
        name: EvidenceGate(name=name, state="verified", reason="fixture_only")
        for name in (
            "arbitration_total_path", "arbitration_total_type", "total_scope",
            "data_path", "offset_path", "limit_path", "shape_version",
        )
    }


def _page(*, offset: int, total: int, rows: list[object]) -> dict[str, object]:
    return {"total_cases": total, "offset": offset, "limit": 100, "data": rows}


def _row(case_id: str, *, target_role: str = "respondents", amount: str = "1") -> dict[str, object]:
    return {"case_id": case_id, target_role: [{"inn": "7701234567"}], "sum": amount, "year": 2025}


def _fixture_pages() -> tuple[dict[str, object], list[object]]:
    path = Path(__file__).parent / "fixtures" / "company_card_v2" / "arbitration_pages.json"
    source = json.loads(path.read_text(encoding="utf-8"))
    return source["registry"], source["pages"]


def test_shipped_arbitration_gate_is_closed() -> None:
    with pytest.raises(ArbitrationGateClosedError):
        require_arbitration_provider_gate()
    assert public_arbitration_nulls() == {"A1": None, "A2": None, "A3": None, "A4": None, "A5": None}


def test_fixture_collector_is_pure_and_keeps_calendar_separate_from_complete_collection() -> None:
    registry, pages = _fixture_pages()
    collection = collect_fixture_arbitration_pages(
        pages, registry=registry,
        secret=b"a" * 32, key_id="key_1", target_inn="7701234567",
        report_id=UUID("a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"),
    )

    assert collection.collection_complete is True
    assert collection.completion_reasons == ("complete",)
    assert collection.calendar_complete is False
    assert collection.calendar_scope == "unverified"
    assert collection.counters.rows_observed == 2
    assert collection.page_manifest[0].accepted_count == 2


@pytest.mark.parametrize(
    ("pages", "reason"),
    [
        ([_page(offset=0, total=2, rows=[_row("a")])], "non_progress"),
        ([_page(offset=1, total=1, rows=[_row("a")])], "offset_drift"),
        ([
            _page(offset=0, total=200, rows=[_row(f"a{index}") for index in range(100)]),
            _page(offset=100, total=201, rows=[_row("b")]),
        ], "total_drift"),
        ([{"provider_error": "fixture"}], "provider_error"),
    ],
)
def test_fixture_collector_fails_partial_with_precedence_reasons(pages, reason) -> None:
    collection = collect_fixture_arbitration_pages(
        pages, registry=_verified_registry(), secret=b"a" * 32, key_id="key_1",
        target_inn="7701234567", report_id=UUID("a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"),
    )
    assert collection.collection_complete is False
    assert collection.completion_reason == reason


def test_fixture_collector_dedup_and_conflict_never_readmit_key() -> None:
    collection = collect_fixture_arbitration_pages(
        [_page(offset=0, total=3, rows=[_row("a"), _row("a", amount="2"), _row("a")])],
        registry=_verified_registry(), secret=b"a" * 32, key_id="key_1", target_inn="7701234567",
        report_id=UUID("a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"),
    )
    assert collection.basis.cases == ()
    assert collection.counters.duplicate_conflict_key_count == 1
    assert collection.counters.duplicate_conflict_row_count == 2
    assert collection.completion_reason == "duplicate_conflict"


def test_fixture_collector_stops_after_ten_pages_and_detects_repeated_content() -> None:
    rows = [_row(f"case-{index}") for index in range(100)]
    exhausted = collect_fixture_arbitration_pages(
        [_page(offset=index * 100, total=1001, rows=[_row(f"{index}-{row}") for row in range(100)]) for index in range(10)],
        registry=_verified_registry(), secret=b"a" * 32, key_id="key_1", target_inn="7701234567",
        report_id=UUID("a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"),
    )
    repeated = collect_fixture_arbitration_pages(
        [_page(offset=0, total=200, rows=rows), _page(offset=100, total=200, rows=rows)],
        registry=_verified_registry(), secret=b"a" * 32, key_id="key_1", target_inn="7701234567",
        report_id=UUID("a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"),
    )
    assert exhausted.completion_reason == "max_pages_exhausted"
    assert exhausted.counters.rows_observed == 1000
    assert repeated.completion_reason == "non_progress"


def test_fixture_collector_requires_synthetic_verified_registry_and_mask_key() -> None:
    closed = collect_fixture_arbitration_pages(
        [], registry={}, secret=b"a" * 32, key_id="key_1", target_inn="7701234567",
        report_id=UUID("a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"),
    )
    unavailable = collect_fixture_arbitration_pages(
        [], registry=_verified_registry(), secret=None, key_id=None, target_inn="7701234567",
        report_id=UUID("a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"),
    )
    assert closed.completion_reason == "envelope_gate_closed"
    assert unavailable.completion_reason == "privacy_key_unavailable"


def test_visible_case_number_never_falls_back_to_internal_identity() -> None:
    row = {"case_id": "private-key", "first_number": " A40-1/2026 "}
    assert visible_case_number(row, gate_verified=False) is None
    assert visible_case_number(row, gate_verified=True) == "A40-1/2026"
    assert visible_case_number({"case_id": "private-key"}, gate_verified=True) is None


def test_verified_alias_requires_one_verified_legal_or_state_identifier() -> None:
    candidates = [
        {"entity_class": "legal", "identifier_verified": True, "inn": "7701234567", "safe_name": "Beta", "case_key": "b", "date_update": "2025-01-01"},
        {"entity_class": "legal", "identifier_verified": True, "inn": "7701234567", "safe_name": "Alpha", "case_key": "a", "date_update": "2025-01-01"},
    ]
    assert select_verified_alias(candidates) == "Alpha"
    assert select_verified_alias([{**candidates[0], "entity_class": "masked_unknown"}]) is None
    assert select_verified_alias([{**candidates[0], "inn": "7701234567"}, {**candidates[1], "inn": "7800000000"}]) is None


def test_fixture_arbitration_dedup_conflict_is_permanently_excluded_and_roles_are_exact() -> None:
    rows = [
        {"case_id": "a", "respondents": [{"inn": "7701234567"}]},
        {"case_id": "a", "respondents": [{"inn": "7701234567"}], "amount": "1"},
        {"case_id": "a", "respondents": [{"inn": "7701234567"}]},
        {"case_id": "b", "plaintiffs": [{"inn": "7701234567"}], "respondents": [{"inn": "7701234567"}]},
    ]

    basis = build_fixture_arbitration_basis(
        rows, secret=b"a" * 32, key_id="key_1", target_inn="7701234567",
    )

    assert [case.identity.value for case in basis.cases] == ["b"]
    assert basis.cases[0].roles == ("other",)


def test_private_opponent_token_uses_report_scoped_canonical_hmac_vector() -> None:
    token = private_opponent_token(
        secret=b"iteration-nineteen-hmac-vector-key-material",
        key_id="key_1",
        report_id=UUID("a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"),
        case_key="case-alpha",
        source_role_collection="respondents",
        zero_based_ordinal=0,
    )

    assert token.value == "21d8c54c7052e3112c6c748f3ae5fa545c121d23b37ca02561b2978b9f767220"


@pytest.mark.parametrize("secret,key_id", [(b"short", "key_1"), (b"a" * 32, "INVALID")])
def test_private_opponent_token_fails_closed_for_invalid_key_material(secret: bytes, key_id: str) -> None:
    with pytest.raises(ValueError):
        private_opponent_token(secret=secret, key_id=key_id, opponent_identifier="7701234567")


def test_private_opponent_token_never_inferrs_stable_identifier_kind() -> None:
    with pytest.raises(ValueError):
        private_opponent_token(
            secret=b"a" * 32, key_id="key_1", report_id=UUID("a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"),
            opponent_identifier="7701234567",
        )
