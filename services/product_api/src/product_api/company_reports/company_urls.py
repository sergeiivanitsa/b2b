"""Deterministic company-page URL policy shared by every backend surface.

The legal-form registry is owner-defined.  It is deliberately closed: values
outside the approved exact Russian aliases do not produce a form-first URL
and must remain on a legacy URL.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Literal


COMPANY_URL_POLICY_VERSION = "company_page_url_v2"
MAX_NAME_SLUG_LENGTH = 200
MAX_CANONICAL_PATH_LENGTH = 240

_INN = re.compile(r"(?:[0-9]{10}|[0-9]{12})")
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_QUOTE_MARKERS = frozenset("\"'`«»„“”‘’")
_OPEN_WRAPPERS = frozenset("\"'`«„“‘([{")
_CLOSE_WRAPPERS = frozenset("\"'`»”’)]}")


@dataclass(frozen=True)
class LegalFormRule:
    full_ru: str
    short_ru: str
    url_token: str
    provider_aliases: tuple[str, ...] = ()


LEGAL_FORM_RULES = (
    LegalFormRule(
        "Общество с ограниченной ответственностью",
        "ООО",
        "ooo",
        ("Общества с ограниченной ответственностью",),
    ),
    LegalFormRule("Акционерное общество", "АО", "ao"),
    LegalFormRule("Открытое акционерное общество", "ОАО", "oao"),
    LegalFormRule("Закрытое акционерное общество", "ЗАО", "zao"),
    LegalFormRule("Публичное акционерное общество", "ПАО", "pao"),
    LegalFormRule("Индивидуальный предприниматель", "ИП", "ip"),
)


def _legal_form_aliases(rule: LegalFormRule) -> tuple[str, ...]:
    return (rule.full_ru, rule.short_ru, *rule.provider_aliases)


_RULE_BY_ALIAS = {
    unicodedata.normalize("NFKC", alias).casefold(): rule
    for rule in LEGAL_FORM_RULES
    for alias in _legal_form_aliases(rule)
}
_RULE_BY_TOKEN = {rule.url_token: rule for rule in LEGAL_FORM_RULES}

_CYRILLIC_TRANSLITERATION = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
    "й": "j", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "x", "ц": "c", "ч": "ch",
    "ш": "sh", "щ": "shh", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}
_LEGACY_TRANSLITERATION = str.maketrans({
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e",
    "ж":"zh","з":"z","и":"i","й":"i","к":"k","л":"l","м":"m",
    "н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u",
    "ф":"f","х":"h","ц":"c","ч":"ch","ш":"sh","щ":"sh","ъ":"",
    "ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
})


@dataclass(frozen=True)
class CanonicalCompanyIdentity:
    inn: str
    legal_form: str | None
    legal_short_name: str | None
    legal_full_name: str | None


@dataclass(frozen=True)
class CanonicalUrlBinding:
    canonical_path: str
    form_token: str | None
    name_slug: str


@dataclass(frozen=True)
class ParsedCompanyKey:
    kind: Literal["plain", "legacy", "v2"]
    inn: str
    form_token: str | None
    name_slug: str | None


@dataclass(frozen=True)
class _SlugAttempt:
    status: Literal["ok", "missing", "no_token", "conflict", "overlength", "invalid"]
    slug: str | None = None


def is_valid_inn(value: object) -> bool:
    return type(value) is str and value.isascii() and _INN.fullmatch(value) is not None


def resolve_legal_form(value: object) -> LegalFormRule | None:
    """Resolve only an owner-approved exact alias."""
    if type(value) is not str:
        return None
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    return _RULE_BY_ALIAS.get(normalized)


def _is_boundary(character: str) -> bool:
    return not character.isalnum()


def _boundary_alias(name: str) -> tuple[LegalFormRule, str] | None:
    value = " ".join(unicodedata.normalize("NFKC", name).split()).strip()
    folded = value.casefold()
    aliases = sorted(
        (
            (unicodedata.normalize("NFKC", alias).casefold(), rule)
            for rule in LEGAL_FORM_RULES
            for alias in _legal_form_aliases(rule)
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    # Leading wins.  Wrappers may surround the alias itself, but an internal
    # occurrence is never removed.
    start = 0
    while start < len(value) and value[start] in _OPEN_WRAPPERS:
        start += 1
    for alias, rule in aliases:
        end = start + len(alias)
        if folded[start:end] != alias:
            continue
        if end < len(value) and not _is_boundary(value[end]):
            continue
        while end < len(value) and value[end] in _CLOSE_WRAPPERS:
            end += 1
        return rule, value[end:].lstrip()

    end = len(value)
    while end > 0 and value[end - 1] in _CLOSE_WRAPPERS:
        end -= 1
    for alias, rule in aliases:
        start = end - len(alias)
        if start < 0 or folded[start:end] != alias:
            continue
        if start > 0 and not _is_boundary(value[start - 1]):
            continue
        while start > 0 and value[start - 1] in _OPEN_WRAPPERS:
            start -= 1
        return rule, value[:start].rstrip()
    return None


def _canonical_slug_attempt(
    name: object,
    *,
    legal_form: LegalFormRule | None = None,
) -> _SlugAttempt:
    if type(name) is not str or not name.strip():
        return _SlugAttempt("missing")
    value = unicodedata.normalize("NFKC", name)
    if legal_form is not None:
        boundary = _boundary_alias(value)
        if boundary is not None:
            observed_form, value = boundary
            if observed_form != legal_form:
                return _SlugAttempt("conflict")
    value = value.lower()
    pieces: list[str] = []
    separator_pending = False
    for character in value:
        if character in _QUOTE_MARKERS or character in {"ъ", "ь"}:
            continue
        transliterated = _CYRILLIC_TRANSLITERATION.get(character)
        if transliterated is not None:
            pieces.append(transliterated)
            separator_pending = False
        elif character.isascii() and ("a" <= character <= "z" or "0" <= character <= "9"):
            pieces.append(character)
            separator_pending = False
        else:
            separator_pending = bool(pieces)
        if separator_pending and pieces and pieces[-1] != "-":
            pieces.append("-")
    slug = re.sub(r"-+", "-", "".join(pieces).strip("-"))
    if not slug:
        return _SlugAttempt("no_token")
    if len(slug) > MAX_NAME_SLUG_LENGTH:
        return _SlugAttempt("overlength")
    if _SLUG.fullmatch(slug) is None:
        return _SlugAttempt("invalid")
    return _SlugAttempt("ok", slug)


def canonical_slug(name: object, *, legal_form: LegalFormRule | None = None) -> str | None:
    """Return a name-only v2 slug, or ``None`` without truncating input."""
    attempt = _canonical_slug_attempt(name, legal_form=legal_form)
    return attempt.slug if attempt.status == "ok" else None


def build_v2_company_binding(identity: CanonicalCompanyIdentity) -> CanonicalUrlBinding | None:
    if type(identity) is not CanonicalCompanyIdentity or not is_valid_inn(identity.inn):
        return None
    rule = resolve_legal_form(identity.legal_form)
    if rule is None:
        return None
    short_attempt = _canonical_slug_attempt(identity.legal_short_name, legal_form=rule)
    if short_attempt.status == "ok":
        attempts = (short_attempt,)
    elif short_attempt.status in {"missing", "no_token"}:
        attempts = (_canonical_slug_attempt(identity.legal_full_name, legal_form=rule),)
    else:
        return None
    for attempt in attempts:
        if attempt.status != "ok" or attempt.slug is None:
            return None
        path = f"/company/{rule.url_token}-{attempt.slug}-{identity.inn}"
        if len(path) <= MAX_CANONICAL_PATH_LENGTH:
            return CanonicalUrlBinding(path, rule.url_token, attempt.slug)
        return None
    return None


def legacy_canonical_slug(name: object) -> str:
    """Reproduce the historical H1 slug byte-for-byte for compatibility."""
    if type(name) is not str:
        raise ValueError("company name cannot form a canonical slug")
    value = unicodedata.normalize("NFKD", name.lower().translate(_LEGACY_TRANSLITERATION))
    value = "".join(character for character in value if not ("\u0300" <= character <= "\u036f"))
    value = "".join(character if character.isascii() and character.isalnum() else "-" for character in value)
    slug = re.sub(r"-+", "-", value).strip("-")
    if not slug:
        raise ValueError("company name cannot form a canonical slug")
    return slug[:MAX_NAME_SLUG_LENGTH].rstrip("-")


def legacy_h1_binding(inn: str, name: object) -> CanonicalUrlBinding:
    if not is_valid_inn(inn):
        raise ValueError("INN must contain exactly 10 or 12 ASCII digits")
    slug = legacy_canonical_slug(name)
    return CanonicalUrlBinding(f"/company/{inn}-{slug}", None, slug)


def build_h1_company_binding(identity: CanonicalCompanyIdentity) -> CanonicalUrlBinding | None:
    """Build v2 when eligible, otherwise preserve the historical H1 grammar."""
    v2 = build_v2_company_binding(identity)
    if v2 is not None:
        return v2
    if not is_valid_inn(identity.inn):
        return None
    for source in (identity.legal_short_name, identity.legal_full_name):
        if type(source) is not str or not source.strip():
            continue
        try:
            return legacy_h1_binding(identity.inn, source.strip())
        except ValueError:
            continue
    return None


def legacy_h2_binding(inn: str) -> CanonicalUrlBinding:
    if not is_valid_inn(inn):
        raise ValueError("INN must contain exactly 10 or 12 ASCII digits")
    return CanonicalUrlBinding(f"/company/{inn}-company", None, "company")


def parse_company_key(value: object) -> ParsedCompanyKey | None:
    if type(value) is not str or not value or not value.isascii():
        return None
    if _INN.fullmatch(value):
        return ParsedCompanyKey("plain", value, None, None)
    legacy = re.fullmatch(
        r"(?P<inn>[0-9]{10}|[0-9]{12})-(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)",
        value,
    )
    if legacy is not None:
        return ParsedCompanyKey("legacy", legacy.group("inn"), None, legacy.group("name"))
    tokens = "|".join(re.escape(token) for token in sorted(_RULE_BY_TOKEN))
    v2 = re.fullmatch(
        rf"(?P<form>{tokens})-(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)-(?P<inn>[0-9]{{10}}|[0-9]{{12}})",
        value,
    )
    if v2 is None:
        return None
    return ParsedCompanyKey("v2", v2.group("inn"), v2.group("form"), v2.group("name"))


def parse_company_path(value: object) -> ParsedCompanyKey | None:
    if type(value) is not str:
        return None
    match = re.fullmatch(r"/company/(?P<company_key>[a-z0-9-]+)", value)
    return parse_company_key(match.group("company_key")) if match is not None else None


__all__ = [
    "COMPANY_URL_POLICY_VERSION",
    "MAX_CANONICAL_PATH_LENGTH",
    "MAX_NAME_SLUG_LENGTH",
    "CanonicalCompanyIdentity",
    "CanonicalUrlBinding",
    "LEGAL_FORM_RULES",
    "LegalFormRule",
    "ParsedCompanyKey",
    "build_v2_company_binding",
    "build_h1_company_binding",
    "canonical_slug",
    "is_valid_inn",
    "legacy_h2_binding",
    "legacy_h1_binding",
    "legacy_canonical_slug",
    "parse_company_key",
    "parse_company_path",
    "resolve_legal_form",
]
