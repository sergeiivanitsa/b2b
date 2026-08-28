from __future__ import annotations

from copy import deepcopy
import json

import pytest

from product_api.company_reports.company_card_v2.canonical_json import (
    canonical_json_bytes,
)
from product_api.company_reports.company_card_v2.rollout_models import (
    H1_PRESENTATION_CONTRACT,
    H2_PRESENTATION_CONTRACT,
    MAX_DECISION_BYTES,
    RolloutDecisionError,
    cohort_bucket,
    parse_rollout_decision,
    rollout_advisory_lock_key,
)


def _activate() -> dict[str, object]:
    return {
        "schema_version": "company_card_v2_rollout_decision_v1",
        "decision_id": "00000000-0000-0000-0000-000000000000",
        "authorization_reference": "P3-test",
        "release_commit": "a" * 40,
        "rollout_generation": 7,
        "action": "activate",
        "stage": "allowlist",
        "target_contract": H2_PRESENTATION_CONTRACT,
        "h2_indexable": False,
        "allowlist_inns": ["7701234567"],
        "percentage_basis_points": 0,
        "maximum_batch_size": 1,
        "observation_window_seconds": 60,
        "abort_policy_reference": "P4-test",
        "targets": [
            {
                "subject_id": "00000000-0000-0000-0000-000000000001",
                "inn": "7701234567",
                "expected_assignment_generation": 0,
                "expected_current_contract": None,
                "expected_current_pin_generation": None,
                "source_h2_pin_generation": 1,
                "expected_active_h2_pin_generation": 2,
                "expected_active_projection_digest": "b" * 64,
                "h1_rollback_pin_generation": 1,
            }
        ],
    }


def _parse(value: dict[str, object]):
    return parse_rollout_decision(canonical_json_bytes(value))


def test_activate_decision_is_canonical_private_and_uses_frozen_lock_vector() -> None:
    parsed = _parse(_activate())

    assert parsed.decision.reason_code == "activate_allowlist"
    assert parsed.decision.decision_id == "00000000-0000-0000-0000-000000000000"
    assert len(parsed.decision_digest) == 64
    assert rollout_advisory_lock_key(parsed.decision.decision_id) == 3432249925710045878
    rendered = " ".join(
        (repr(parsed), repr(parsed.decision), repr(parsed.decision.targets[0]))
    )
    assert "7701234567" not in rendered
    assert "P3-test" not in rendered


def test_rollback_matrix_is_exact_and_does_not_require_live_cohort_fields() -> None:
    value = _activate()
    value.update(
        {
            "action": "rollback",
            "stage": "emergency_rollback",
            "target_contract": H1_PRESENTATION_CONTRACT,
            "h2_indexable": False,
            "rollout_generation": None,
            "allowlist_inns": None,
            "percentage_basis_points": None,
            "observation_window_seconds": None,
            "abort_policy_reference": None,
            "targets": [
                {
                    "subject_id": "00000000-0000-0000-0000-000000000001",
                    "inn": "7701234567",
                    "expected_assignment_generation": 4,
                    "expected_current_contract": H2_PRESENTATION_CONTRACT,
                    "expected_current_pin_generation": 3,
                    "h1_target_pin_generation": 1,
                }
            ],
        }
    )
    parsed = _parse(value)
    assert parsed.decision.reason_code == "rollback_emergency_rollback"


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.update(schema_version="unknown"),
        lambda value: value.update(release_commit="A" * 40),
        lambda value: value.update(stage="ga"),
        lambda value: value.update(maximum_batch_size=0),
        lambda value: value.update(allowlist_inns=[]),
        lambda value: value["targets"][0].update(expected_assignment_generation=True),
        lambda value: value["targets"][0].update(expected_current_contract=H1_PRESENTATION_CONTRACT),
        lambda value: value["targets"][0].update(unexpected="forbidden"),
        lambda value: value.update(unexpected="forbidden"),
    ),
)
def test_closed_contract_rejects_invalid_shapes(mutate) -> None:
    value = _activate()
    mutate(value)
    with pytest.raises(RolloutDecisionError):
        _parse(value)


def test_target_order_and_identity_are_strict() -> None:
    value = _activate()
    second = deepcopy(value["targets"][0])
    second.update(
        subject_id="00000000-0000-0000-0000-000000000002",
        inn="500100732259",
    )
    value["targets"].append(second)
    value["allowlist_inns"] = ["500100732259", "7701234567"]
    value["maximum_batch_size"] = 2
    with pytest.raises(RolloutDecisionError):
        _parse(value)

    value["targets"].reverse()
    assert len(_parse(value).decision.targets) == 2


def test_percentage_membership_reuses_frozen_bucket_rule() -> None:
    value = _activate()
    inn = value["targets"][0]["inn"]
    bucket = cohort_bucket(inn)
    assert bucket < 9_999
    value.update(
        stage="percentage",
        allowlist_inns=[],
        percentage_basis_points=bucket + 1,
    )
    assert _parse(value).decision.stage == "percentage"
    value["percentage_basis_points"] = bucket
    with pytest.raises(RolloutDecisionError):
        _parse(value)


@pytest.mark.parametrize(
    "raw",
    (
        b"\xef\xbb\xbf{}",
        b'{"a":1,"a":1}',
        b'{"value":1.0}',
        b'{"value":NaN}',
        b'{"value":"\\ud800"}',
        b"{}\n",
    ),
)
def test_parser_rejects_noncanonical_or_unsafe_json(raw: bytes) -> None:
    with pytest.raises(RolloutDecisionError):
        parse_rollout_decision(raw)


def test_parser_rejects_oversize_input_before_json_work() -> None:
    with pytest.raises(RolloutDecisionError, match="size cap"):
        parse_rollout_decision(b" " * (MAX_DECISION_BYTES + 1))


def test_standard_json_serialization_is_rejected_even_when_semantically_equal() -> None:
    value = _activate()
    ordinary = json.dumps(value, ensure_ascii=False).encode("utf-8")
    assert ordinary != canonical_json_bytes(value)
    with pytest.raises(RolloutDecisionError, match="canonical"):
        parse_rollout_decision(ordinary)
