from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from . import person_name_inflection_exceptions as exceptions

PartySide = Literal["from", "to"]
InflectionTargetCase = Literal["genitive", "dative"]
InflectionStatus = Literal["can_inflect", "use_raw", "empty"]
GenderHint = Literal["male", "female", "unknown"]
DecisionReason = Literal[
    "empty_input",
    "not_three_words",
    "non_cyrillic",
    "initials_or_noise",
    "all_caps",
    "missing_or_invalid_patronymic",
    "low_confidence_gender",
    "high_confidence_parse",
]

_CYRILLIC_TOKEN_PATTERN = re.compile(r"^[А-Яа-яЁё]+$")
_LATIN_PATTERN = re.compile(r"[A-Za-z]")
_DIGIT_PATTERN = re.compile(r"\d")
_CONSONANTS = set("бвгджзйклмнпрстфхцчшщ")
_I_ENDING_BEFORE = set("гкхжчшщц")


@dataclass(frozen=True, slots=True)
class ParsedPersonName:
    # raw is the normalized person name (trim + collapsed spaces).
    raw: str
    surname: str
    first_name: str
    patronymic: str


@dataclass(frozen=True, slots=True)
class InflectionDecision:
    target_case: InflectionTargetCase
    status: InflectionStatus
    reason: DecisionReason
    gender_hint: GenderHint
    parsed: ParsedPersonName | None


def target_case_for_side(side: PartySide) -> InflectionTargetCase:
    if side == "from":
        return "genitive"
    if side == "to":
        return "dative"
    raise ValueError("invalid side")


def normalize_person_name_for_decision(person_name: str | None) -> str | None:
    if person_name is None:
        return None
    normalized = " ".join(person_name.strip().split())
    return normalized or None


def build_inflection_decision(
    person_name: str | None,
    *,
    side: PartySide,
) -> InflectionDecision:
    target_case = target_case_for_side(side)
    normalized = normalize_person_name_for_decision(person_name)
    if normalized is None:
        return InflectionDecision(
            target_case=target_case,
            status="empty",
            reason="empty_input",
            gender_hint="unknown",
            parsed=None,
        )

    tokens = normalized.split(" ")
    if len(tokens) != 3:
        return InflectionDecision(
            target_case=target_case,
            status="use_raw",
            reason="not_three_words",
            gender_hint="unknown",
            parsed=None,
        )

    parsed = ParsedPersonName(
        raw=normalized,
        surname=tokens[0],
        first_name=tokens[1],
        patronymic=tokens[2],
    )

    if _contains_latin_letters(tokens):
        return InflectionDecision(
            target_case=target_case,
            status="use_raw",
            reason="non_cyrillic",
            gender_hint="unknown",
            parsed=parsed,
        )

    if _contains_initials_or_noise(tokens):
        return InflectionDecision(
            target_case=target_case,
            status="use_raw",
            reason="initials_or_noise",
            gender_hint="unknown",
            parsed=parsed,
        )

    if _is_all_caps(tokens):
        return InflectionDecision(
            target_case=target_case,
            status="use_raw",
            reason="all_caps",
            gender_hint="unknown",
            parsed=parsed,
        )

    if not _is_valid_patronymic_token(parsed.patronymic):
        return InflectionDecision(
            target_case=target_case,
            status="use_raw",
            reason="missing_or_invalid_patronymic",
            gender_hint="unknown",
            parsed=parsed,
        )

    gender_hint = _infer_gender_from_patronymic(parsed.patronymic)
    if gender_hint == "unknown":
        return InflectionDecision(
            target_case=target_case,
            status="use_raw",
            reason="low_confidence_gender",
            gender_hint=gender_hint,
            parsed=parsed,
        )

    return InflectionDecision(
        target_case=target_case,
        status="can_inflect",
        reason="high_confidence_parse",
        gender_hint=gender_hint,
        parsed=parsed,
    )


def inflect_person_name_for_display(
    person_name: str | None,
    *,
    side: PartySide,
) -> str | None:
    normalized_raw = normalize_person_name_for_decision(person_name)
    if normalized_raw is None:
        return None

    # For a narrow safe subset of ALL CAPS cyrillic full names, first normalize
    # the display casing and then run the regular inflection pipeline.
    display_candidate = normalize_person_name_for_display(person_name)
    if display_candidate is not None:
        decision = build_inflection_decision(display_candidate, side=side)
        if decision.status != "can_inflect":
            return display_candidate
    else:
        decision = build_inflection_decision(person_name, side=side)
        if decision.status == "empty":
            return None
        if decision.status != "can_inflect":
            return normalized_raw

    parsed = decision.parsed
    if parsed is None:
        return display_candidate if display_candidate is not None else normalized_raw

    full_name_override = _get_full_name_override(parsed.raw, decision.target_case)
    if full_name_override is not None:
        return full_name_override

    surname = _get_surname_override(parsed.surname, decision.gender_hint, decision.target_case)
    if surname is None:
        surname = _inflect_surname_rule_based(
            parsed.surname,
            decision.gender_hint,
            decision.target_case,
        )

    first_name = _inflect_first_name_rule_based(
        parsed.first_name,
        decision.gender_hint,
        decision.target_case,
    )
    patronymic = _inflect_patronymic_rule_based(
        parsed.patronymic,
        decision.gender_hint,
        decision.target_case,
    )

    # Phase 1 safety rule: if at least one component is unsupported, keep raw full name.
    if surname is None or first_name is None or patronymic is None:
        return parsed.raw

    return f"{surname} {first_name} {patronymic}"


def _contains_latin_letters(tokens: list[str]) -> bool:
    return any(_LATIN_PATTERN.search(token) for token in tokens)


def normalize_person_name_for_display(person_name: str | None) -> str | None:
    normalized = normalize_person_name_for_decision(person_name)
    if normalized is None:
        return None
    tokens = normalized.split(" ")
    if not _is_safe_structured_all_caps_cyrillic(tokens):
        return None
    return " ".join(_titlecase_cyrillic_token(token) for token in tokens)


def _contains_initials_or_noise(tokens: list[str]) -> bool:
    for token in tokens:
        if "." in token:
            return True
        if _DIGIT_PATTERN.search(token):
            return True
        if not _CYRILLIC_TOKEN_PATTERN.fullmatch(token):
            return True
    return False


def _is_all_caps(tokens: list[str]) -> bool:
    letters_only = [token for token in tokens if token]
    if not letters_only:
        return False
    return all(token.upper() == token and token.lower() != token for token in letters_only)


def _is_safe_structured_all_caps_cyrillic(tokens: list[str]) -> bool:
    if len(tokens) != 3:
        return False
    if _contains_latin_letters(tokens):
        return False
    if _contains_initials_or_noise(tokens):
        return False
    if not _is_all_caps(tokens):
        return False
    patronymic = tokens[2]
    if not _is_valid_patronymic_token(patronymic):
        return False
    return _infer_gender_from_patronymic(patronymic) != "unknown"


def _titlecase_cyrillic_token(token: str) -> str:
    if not token:
        return token
    return f"{token[:1].upper()}{token[1:].lower()}"


def _is_valid_patronymic_token(token: str) -> bool:
    if not _CYRILLIC_TOKEN_PATTERN.fullmatch(token):
        return False
    return len(token) >= 3


def _infer_gender_from_patronymic(token: str) -> GenderHint:
    lowered = token.lower()
    if lowered.endswith("ич"):
        return "male"
    if lowered.endswith("на"):
        return "female"
    return "unknown"


def _get_full_name_override(
    full_name: str,
    target_case: InflectionTargetCase,
) -> str | None:
    key = exceptions.normalize_exception_key(full_name)
    by_case = exceptions.FULL_NAME_CASE_OVERRIDES.get(key)
    if not isinstance(by_case, dict):
        return None
    value = by_case.get(target_case)
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.strip().split())
    return normalized or None


def _get_surname_override(
    surname: str,
    gender_hint: GenderHint,
    target_case: InflectionTargetCase,
) -> str | None:
    if gender_hint == "unknown":
        return None
    key = exceptions.normalize_exception_key(surname)
    by_gender = exceptions.SURNAME_GENDER_CASE_OVERRIDES.get(key)
    if not isinstance(by_gender, dict):
        return None
    by_case = by_gender.get(gender_hint)
    if not isinstance(by_case, dict):
        return None
    value = by_case.get(target_case)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _inflect_surname_rule_based(
    surname: str,
    gender_hint: GenderHint,
    target_case: InflectionTargetCase,
) -> str | None:
    lowered = surname.lower()
    if gender_hint == "male":
        if lowered.endswith(("ов", "ев", "ёв", "ин", "ын")):
            return _append_suffix(surname, "а" if target_case == "genitive" else "у")
        if lowered.endswith(("ский", "цкий")):
            return _replace_suffix(
                surname,
                "ий",
                "ого" if target_case == "genitive" else "ому",
            )
        if lowered.endswith(("ой", "ый", "ий")):
            return _replace_suffix(
                surname,
                lowered[-2:],
                "ого" if target_case == "genitive" else "ому",
            )
        if lowered and lowered[-1] in _CONSONANTS:
            return _append_suffix(surname, "а" if target_case == "genitive" else "у")
        return None

    if gender_hint == "female":
        if lowered.endswith(("ова", "ева", "ёва", "ина", "ына")):
            return _replace_suffix(surname, lowered[-1:], "ой")
        if lowered.endswith(("ская", "цкая")):
            return _replace_suffix(surname, "ая", "ой")
        if lowered.endswith("ая"):
            return _replace_suffix(surname, "ая", "ой")
        if lowered.endswith("яя"):
            return _replace_suffix(surname, "яя", "ей")
        return None

    return None


def _inflect_first_name_rule_based(
    first_name: str,
    gender_hint: GenderHint,
    target_case: InflectionTargetCase,
) -> str | None:
    lowered = first_name.lower()
    if gender_hint == "male":
        if lowered.endswith("й"):
            return _replace_suffix(first_name, "й", "я" if target_case == "genitive" else "ю")
        if lowered.endswith("ь"):
            return _replace_suffix(first_name, "ь", "я" if target_case == "genitive" else "ю")
        if lowered and lowered[-1] in _CONSONANTS:
            return _append_suffix(first_name, "а" if target_case == "genitive" else "у")
        return None

    if gender_hint == "female":
        if lowered.endswith("ия"):
            return _replace_suffix(first_name, "ия", "ии")
        if lowered.endswith("я"):
            return _replace_suffix(first_name, "я", "и" if target_case == "genitive" else "е")
        if lowered.endswith("а"):
            if target_case == "genitive":
                suffix = "и" if len(lowered) >= 2 and lowered[-2] in _I_ENDING_BEFORE else "ы"
                return _replace_suffix(first_name, "а", suffix)
            return _replace_suffix(first_name, "а", "е")
        return None

    return None


def _inflect_patronymic_rule_based(
    patronymic: str,
    gender_hint: GenderHint,
    target_case: InflectionTargetCase,
) -> str | None:
    lowered = patronymic.lower()
    if gender_hint == "male":
        if lowered.endswith("ич"):
            return _append_suffix(patronymic, "а" if target_case == "genitive" else "у")
        return None
    if gender_hint == "female":
        if lowered.endswith("на"):
            return _replace_suffix(patronymic, "а", "ы" if target_case == "genitive" else "е")
        return None
    return None


def _append_suffix(token: str, suffix: str) -> str:
    return f"{token}{suffix}"


def _replace_suffix(token: str, source_suffix: str, target_suffix: str) -> str:
    return f"{token[: -len(source_suffix)]}{target_suffix}"
