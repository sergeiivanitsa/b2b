from types import SimpleNamespace

from product_api.company_reports.company_card_v2.service import h2_cohort_selected


def _settings(**overrides):
    values = {
        "company_card_v2_presentations_enabled": True,
        "company_card_v2_rollout_generation": 7,
        "company_card_v2_allowlist_inns": [],
        "company_card_v2_percentage_basis_points": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_h2_cohort_is_server_deterministic_and_allowlist_first():
    settings = _settings(company_card_v2_allowlist_inns=["7701234567"])
    assert h2_cohort_selected(inn="7701234567", settings=settings)
    assert not h2_cohort_selected(inn="7701234568", settings=settings)
    percentage = _settings(company_card_v2_percentage_basis_points=10_000)
    assert h2_cohort_selected(inn="7701234568", settings=percentage)
    assert h2_cohort_selected(inn="7701234568", settings=percentage)


def test_h2_cohort_fails_closed_for_disabled_or_malformed_configuration():
    assert not h2_cohort_selected(inn="7701234567", settings=_settings(company_card_v2_presentations_enabled=False))
    assert not h2_cohort_selected(inn="7701234567", settings=_settings(company_card_v2_rollout_generation=0))
    assert not h2_cohort_selected(inn="bad", settings=_settings(company_card_v2_percentage_basis_points=10_000))
    assert not h2_cohort_selected(inn="7701234567", settings=_settings(company_card_v2_allowlist_inns="7701234567"))
