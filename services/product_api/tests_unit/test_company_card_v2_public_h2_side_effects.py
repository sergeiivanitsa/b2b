from product_api.company_reports.company_card_v2.service import h2_cohort_selected


def test_default_off_h2_cohort_prevents_any_selection_before_persistence() -> None:
    settings = type("Settings", (), {
        "company_card_v2_presentations_enabled": False,
        "company_card_v2_rollout_generation": 0,
        "company_card_v2_allowlist_inns": [],
        "company_card_v2_percentage_basis_points": 10_000,
    })()
    assert not h2_cohort_selected(inn="7701234567", settings=settings)
