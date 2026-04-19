from __future__ import annotations

from typing import Final
from typing import Literal

InflectionTargetCase = Literal["genitive", "dative"]
GenderKey = Literal["male", "female", "unknown"]

CaseMap = dict[InflectionTargetCase, str]
FullNameCaseOverrides = dict[str, CaseMap]
SurnameGenderCaseOverrides = dict[str, dict[GenderKey, CaseMap]]


def normalize_exception_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


# Full-name overrides have the highest priority and store full prepared FIO forms.
FULL_NAME_CASE_OVERRIDES: Final[FullNameCaseOverrides] = {}


# Surname overrides are keyed by surname and gender, and store only surname forms by case.
SURNAME_GENDER_CASE_OVERRIDES: Final[SurnameGenderCaseOverrides] = {
    "иваница": {
        "male": {
            "genitive": "Иваницы",
            "dative": "Иванице",
        },
        "female": {
            "genitive": "Иваница",
            "dative": "Иваница",
        },
        "unknown": {},
    }
}
