import pytest

from product_api.claims import person_name_inflection_exceptions as exceptions
from product_api.claims.person_name_inflection import (
    build_inflection_decision,
    inflect_person_name_for_display,
    normalize_person_name_for_decision,
    target_case_for_side,
)


def test_target_case_for_side():
    assert target_case_for_side("from") == "genitive"
    assert target_case_for_side("to") == "dative"


def test_normalize_person_name_for_decision_trims_and_collapses_spaces():
    assert (
        normalize_person_name_for_decision("  Иванов   Иван   Иванович  ")
        == "Иванов Иван Иванович"
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
    ],
)
def test_empty_input_returns_empty_status(value: str | None):
    decision = build_inflection_decision(value, side="from")
    assert decision.status == "empty"
    assert decision.reason == "empty_input"
    assert decision.gender_hint == "unknown"
    assert decision.parsed is None
    assert decision.target_case == "genitive"


def test_not_three_words_uses_raw():
    decision = build_inflection_decision("Иванов Иван", side="from")
    assert decision.status == "use_raw"
    assert decision.reason == "not_three_words"
    assert decision.gender_hint == "unknown"
    assert decision.parsed is None


def test_male_patronymic_high_confidence_parse():
    decision = build_inflection_decision("Иванов Иван Иванович", side="from")
    assert decision.status == "can_inflect"
    assert decision.reason == "high_confidence_parse"
    assert decision.gender_hint == "male"
    assert decision.target_case == "genitive"
    assert decision.parsed is not None
    assert decision.parsed.raw == "Иванов Иван Иванович"
    assert decision.parsed.surname == "Иванов"
    assert decision.parsed.first_name == "Иван"
    assert decision.parsed.patronymic == "Иванович"


def test_female_patronymic_high_confidence_parse():
    decision = build_inflection_decision("Смирнова Анна Ивановна", side="to")
    assert decision.status == "can_inflect"
    assert decision.reason == "high_confidence_parse"
    assert decision.gender_hint == "female"
    assert decision.target_case == "dative"
    assert decision.parsed is not None
    assert decision.parsed.raw == "Смирнова Анна Ивановна"


def test_unknown_patronymic_gender_uses_raw():
    decision = build_inflection_decision("Иванов Иван Оглы", side="to")
    assert decision.status == "use_raw"
    assert decision.reason == "low_confidence_gender"
    assert decision.gender_hint == "unknown"
    assert decision.target_case == "dative"
    assert decision.parsed is not None


def test_initials_or_noise_uses_raw():
    decision = build_inflection_decision("Петров П.П. Петрович", side="from")
    assert decision.status == "use_raw"
    assert decision.reason == "initials_or_noise"
    assert decision.gender_hint == "unknown"
    assert decision.parsed is not None


def test_non_cyrillic_uses_raw():
    decision = build_inflection_decision("Ivanov Ivan Ivanovich", side="from")
    assert decision.status == "use_raw"
    assert decision.reason == "non_cyrillic"
    assert decision.gender_hint == "unknown"
    assert decision.parsed is not None


def test_all_caps_uses_raw_with_dedicated_reason():
    decision = build_inflection_decision("ИВАНОВ ИВАН ИВАНОВИЧ", side="to")
    assert decision.status == "use_raw"
    assert decision.reason == "all_caps"
    assert decision.gender_hint == "unknown"
    assert decision.target_case == "dative"
    assert decision.parsed is not None


def test_hyphenated_cyrillic_form_uses_safe_raw():
    decision = build_inflection_decision("Иванов-Петров Иван Иванович", side="from")
    assert decision.status == "use_raw"
    assert decision.reason == "initials_or_noise"
    assert decision.gender_hint == "unknown"
    assert decision.parsed is not None


def test_inflect_person_name_male_supported_rules():
    assert (
        inflect_person_name_for_display("Иванов Иван Иванович", side="from")
        == "Иванова Ивана Ивановича"
    )
    assert (
        inflect_person_name_for_display("Иванов Иван Иванович", side="to")
        == "Иванову Ивану Ивановичу"
    )


def test_inflect_person_name_female_supported_rules():
    assert (
        inflect_person_name_for_display("Смирнова Анна Ивановна", side="from")
        == "Смирновой Анны Ивановны"
    )
    assert (
        inflect_person_name_for_display("Смирнова Анна Ивановна", side="to")
        == "Смирновой Анне Ивановне"
    )


def test_inflect_person_name_ivanitsa_male_uses_surname_override():
    assert (
        inflect_person_name_for_display("Иваница Сергей Петрович", side="from")
        == "Иваницы Сергея Петровича"
    )
    assert (
        inflect_person_name_for_display("Иваница Сергей Петрович", side="to")
        == "Иванице Сергею Петровичу"
    )


def test_inflect_person_name_ivanitsa_female_uses_surname_override():
    assert (
        inflect_person_name_for_display("Иваница Анна Петровна", side="from")
        == "Иваница Анны Петровны"
    )
    assert (
        inflect_person_name_for_display("Иваница Анна Петровна", side="to")
        == "Иваница Анне Петровне"
    )


def test_female_name_ending_ya_uses_expected_forms():
    assert (
        inflect_person_name_for_display("Сидорова Наталья Ивановна", side="from")
        == "Сидоровой Натальи Ивановны"
    )
    assert (
        inflect_person_name_for_display("Сидорова Наталья Ивановна", side="to")
        == "Сидоровой Наталье Ивановне"
    )


def test_female_name_ending_iya_uses_expected_forms():
    assert (
        inflect_person_name_for_display("Сидорова Мария Ивановна", side="from")
        == "Сидоровой Марии Ивановны"
    )
    assert (
        inflect_person_name_for_display("Сидорова Мария Ивановна", side="to")
        == "Сидоровой Марии Ивановне"
    )


def test_if_any_component_is_unsupported_return_raw_full_name():
    # Female first name ending with "ь" is intentionally unsupported in Phase 1 rules.
    source = "Смирнова Любовь Ивановна"
    assert inflect_person_name_for_display(source, side="from") == source
    assert inflect_person_name_for_display(source, side="to") == source


def test_use_raw_for_all_caps_in_final_output():
    source = "ИВАНОВ ИВАН ИВАНОВИЧ"
    assert inflect_person_name_for_display(source, side="from") == source
    assert inflect_person_name_for_display(source, side="to") == source


def test_full_name_override_has_highest_priority(monkeypatch: pytest.MonkeyPatch):
    full_overrides = {
        "иванов иван иванович": {
            "genitive": "ПОЛНЫЙ ОВЕРРАЙД GEN",
            "dative": "ПОЛНЫЙ ОВЕРРАЙД DAT",
        }
    }
    surname_overrides = {
        "иванов": {
            "male": {"genitive": "ФАМИЛИЯ GEN", "dative": "ФАМИЛИЯ DAT"},
            "female": {},
            "unknown": {},
        }
    }
    monkeypatch.setattr(exceptions, "FULL_NAME_CASE_OVERRIDES", full_overrides)
    monkeypatch.setattr(exceptions, "SURNAME_GENDER_CASE_OVERRIDES", surname_overrides)

    assert (
        inflect_person_name_for_display("Иванов Иван Иванович", side="from")
        == "ПОЛНЫЙ ОВЕРРАЙД GEN"
    )
    assert (
        inflect_person_name_for_display("Иванов Иван Иванович", side="to")
        == "ПОЛНЫЙ ОВЕРРАЙД DAT"
    )


def test_surname_gender_override_has_priority_over_rule_based(monkeypatch: pytest.MonkeyPatch):
    full_overrides: dict[str, dict[str, str]] = {}
    surname_overrides = {
        "иванов": {
            "male": {
                "genitive": "ТЕСТОВАЯФАМИЛИЯGEN",
                "dative": "ТЕСТОВАЯФАМИЛИЯDAT",
            },
            "female": {},
            "unknown": {},
        }
    }
    monkeypatch.setattr(exceptions, "FULL_NAME_CASE_OVERRIDES", full_overrides)
    monkeypatch.setattr(exceptions, "SURNAME_GENDER_CASE_OVERRIDES", surname_overrides)

    assert (
        inflect_person_name_for_display("Иванов Иван Иванович", side="from")
        == "ТЕСТОВАЯФАМИЛИЯGEN Ивана Ивановича"
    )
    assert (
        inflect_person_name_for_display("Иванов Иван Иванович", side="to")
        == "ТЕСТОВАЯФАМИЛИЯDAT Ивану Ивановичу"
    )
