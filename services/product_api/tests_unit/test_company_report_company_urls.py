from product_api.company_reports.company_urls import (
    CanonicalCompanyIdentity,
    LEGAL_FORM_RULES,
    build_h1_company_binding,
    build_v2_company_binding,
    canonical_slug,
    parse_company_key,
    parse_company_path,
    resolve_legal_form,
)


def identity(form: str | None, short: str | None, full: str | None = None, inn: str = "7707079463"):
    return CanonicalCompanyIdentity(inn, form, short, full)


def test_owner_defined_registry_has_only_six_legal_form_rules() -> None:
    assert [(rule.short_ru, rule.url_token) for rule in LEGAL_FORM_RULES] == [
        ("ООО", "ooo"), ("АО", "ao"), ("ОАО", "oao"),
        ("ЗАО", "zao"), ("ПАО", "pao"), ("ИП", "ip"),
    ]
    for rule in LEGAL_FORM_RULES:
        assert resolve_legal_form(rule.short_ru.lower()) == rule
        assert resolve_legal_form(rule.full_ru.upper()) == rule
    assert resolve_legal_form("Непубличные акционерные общества") is None
    assert resolve_legal_form("Синтетическая организационная форма") is None


def test_fixed_transliteration_and_cleanup_vectors() -> None:
    assert canonical_slug("Ёж Йод Хлеб Щука Объект Подъезд") == "yozh-jod-xleb-shhuka-obekt-podezd"
    assert canonical_slug("Цех — test_NAME / 😀 №42") == "cex-test-name-no42"
    assert canonical_slug("ъь ' ` \" «»") is None


def test_datanewton_llc_opf_alias_builds_form_first_url() -> None:
    observed_opf = "Общества с ограниченной ответственностью"

    assert resolve_legal_form(observed_opf) == LEGAL_FORM_RULES[0]
    binding = build_v2_company_binding(
        identity(
            observed_opf,
            'ООО "Проверка"',
        )
    )

    assert binding is not None
    assert binding.canonical_path == "/company/ooo-proverka-7707079463"


def test_builder_uses_short_then_full_and_strips_one_matching_boundary_alias() -> None:
    assert build_v2_company_binding(identity("ООО", "ООО «Ёлка и Щука»")).canonical_path == "/company/ooo-yolka-i-shhuka-7707079463"
    assert build_v2_company_binding(identity("Акционерное общество", "", "Акционерное общество «Объект»")).canonical_path == "/company/ao-obekt-7707079463"
    assert build_v2_company_binding(identity("ПАО", "ПАО Компания (ПАО)")).name_slug == "kompaniya-pao"
    assert build_v2_company_binding(identity("ПАО", "Компания (ПАО)")).name_slug == "kompaniya"
    assert build_v2_company_binding(identity("ИП", "Иванов Иван", inn="123456789012")).canonical_path == "/company/ip-ivanov-ivan-123456789012"


def test_builder_does_not_strip_internal_or_different_form_and_fails_closed() -> None:
    assert build_v2_company_binding(identity("ООО", "Проект ООО Ромашка")).name_slug == "proekt-ooo-romashka"
    assert build_v2_company_binding(identity("ООО", "Проект ПАО Ромашка")) is not None
    assert build_v2_company_binding(identity("ООО", "ПАО Ромашка")) is None
    assert build_v2_company_binding(identity("ООО", "Ромашка (ПАО)")) is None
    assert build_h1_company_binding(identity("ООО", "ПАО Ромашка")).canonical_path == "/company/7707079463-pao-romashka"
    assert build_v2_company_binding(identity(None, "Ромашка")) is None
    assert build_v2_company_binding(identity("unknown", "Ромашка")) is None
    assert build_v2_company_binding(identity("ООО", "ъь")) is None
    assert build_v2_company_binding(identity("ООО", "а" * 201)) is None
    assert build_v2_company_binding(identity("ООО", "а" * 200)) is not None


def test_short_name_fallback_is_only_for_missing_or_tokenless_short_name() -> None:
    fallback = build_v2_company_binding(identity("ООО", "ъь «»", "ООО Ромашка"))
    assert fallback is not None and fallback.name_slug == "romashka"
    assert build_v2_company_binding(identity("ООО", "а" * 201, "ООО Ромашка")) is None
    assert build_v2_company_binding(identity("ООО", "ПАО Ромашка", "ООО Ромашка")) is None


def test_parser_round_trip_plain_legacy_and_v2_without_slicing() -> None:
    assert parse_company_key("7707079463") == parse_company_path("/company/7707079463")
    plain = parse_company_key("7707079463")
    assert plain and (plain.kind, plain.inn, plain.form_token, plain.name_slug) == ("plain", "7707079463", None, None)
    legacy = parse_company_key("7707079463-company")
    assert legacy and (legacy.kind, legacy.name_slug) == ("legacy", "company")
    path = build_v2_company_binding(identity("ООО", "Ромашка"))
    assert path is not None
    parsed = parse_company_path(path.canonical_path)
    assert parsed and (parsed.kind, parsed.form_token, parsed.name_slug, parsed.inn) == ("v2", "ooo", "romashka", "7707079463")


def test_parser_rejects_ambiguous_or_unsafe_keys() -> None:
    invalid = (
        "12345678901", "ооо-name-7707079463", "unknown-name-7707079463",
        "ooo-7707079463", "ooo-name-７７０７０７９４６３", "ooo-name-7707079463/",
        "ooo--name-7707079463", "7707079463-Name", "7707079463-name?x=1",
    )
    assert all(parse_company_key(value) is None for value in invalid)


def test_inn_suffix_makes_v2_paths_unique() -> None:
    first = build_v2_company_binding(identity("ООО", "Ромашка", inn="7707079463"))
    second = build_v2_company_binding(identity("ООО", "Ромашка", inn="7707079464"))
    assert first is not None and second is not None
    assert first.canonical_path != second.canonical_path
