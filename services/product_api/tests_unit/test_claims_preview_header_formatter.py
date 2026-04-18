import pytest

from product_api.claims.preview_header_formatter import build_preview_header


def test_formatter_legal_entity_director_keeps_legacy_and_builds_rendered():
    header = build_preview_header(
        from_party={
            "kind": "legal_entity",
            "company_name": "ООО «Альфа»",
            "position_raw": "директор",
            "person_name": "Петров Петр Петрович",
        },
        to_party={
            "kind": "legal_entity",
            "company_name": "ООО «Вектор»",
            "position_raw": "директор",
            "person_name": "Иванов Иван Иванович",
        },
    )
    assert header["from_party"]["line1"] == "Директора ООО «Альфа»"
    assert header["from_party"]["line2"] == "Петров Петр Петрович"
    assert header["to_party"]["line1"] == "Директору ООО «Вектор»"
    assert header["to_party"]["line2"] == "Иванов Иван Иванович"

    assert header["from_party"]["rendered"] == {
        "line1": "От директора",
        "line2": "ООО «Альфа»",
        "line3": "Петров Петр Петрович",
    }
    assert header["to_party"]["rendered"] == {
        "line1": "Директору",
        "line2": "ООО «Вектор»",
        "line3": "Иванов Иван Иванович",
    }


def test_formatter_general_director_priority_over_director_keeps_legacy_and_builds_rendered():
    header = build_preview_header(
        from_party={
            "kind": "legal_entity",
            "company_name": "ООО «Альфа»",
            "position_raw": "генеральный директор",
            "person_name": "Петров Петр Петрович",
        },
        to_party={
            "kind": "legal_entity",
            "company_name": "ООО «Вектор»",
            "position_raw": "генеральный директор",
            "person_name": "Иванов Иван Иванович",
        },
    )
    assert header["from_party"]["line1"] == "Генерального директора ООО «Альфа»"
    assert header["to_party"]["line1"] == "Генеральному директору ООО «Вектор»"

    assert header["from_party"]["rendered"]["line1"] == "От генерального директора"
    assert header["to_party"]["rendered"]["line1"] == "Генеральному директору"


def test_formatter_president_uses_rendered_alias_and_keeps_legacy_fallback():
    header = build_preview_header(
        from_party={
            "kind": "legal_entity",
            "company_name": "ООО «Альфа»",
            "position_raw": "президент",
            "person_name": "Петров Петр Петрович",
        },
        to_party={
            "kind": "legal_entity",
            "company_name": "ООО «Вектор»",
            "position_raw": "президент",
            "person_name": "Иванов Иван Иванович",
        },
    )
    # Legacy line1/line2 remain unchanged in this commit.
    assert header["from_party"]["line1"] == "Руководителя ООО «Альфа»"
    assert header["to_party"]["line1"] == "Руководителю ООО «Вектор»"

    assert header["from_party"]["rendered"]["line1"] == "От президента"
    assert header["to_party"]["rendered"]["line1"] == "Президенту"


def test_formatter_unknown_position_uses_rendered_fallback():
    header = build_preview_header(
        from_party={
            "kind": "legal_entity",
            "company_name": "ООО «Альфа»",
            "position_raw": "уполномоченный представитель",
            "person_name": "Петров Петр Петрович",
        },
        to_party={
            "kind": "legal_entity",
            "company_name": "ООО «Вектор»",
            "position_raw": "уполномоченный представитель",
            "person_name": "Иванов Иван Иванович",
        },
    )
    assert header["from_party"]["rendered"] == {
        "line1": "От руководителя",
        "line2": "ООО «Альфа»",
        "line3": "Петров Петр Петрович",
    }
    assert header["to_party"]["rendered"] == {
        "line1": "Руководителю",
        "line2": "ООО «Вектор»",
        "line3": "Иванов Иван Иванович",
    }


@pytest.mark.parametrize(
    ("position_raw", "expected_from_line1", "expected_to_line1"),
    [
        ("general director", "От генерального директора", "Генеральному директору"),
        ("director", "От директора", "Директору"),
        ("president", "От президента", "Президенту"),
        ("  general   director  ", "От генерального директора", "Генеральному директору"),
    ],
)
def test_formatter_rendered_english_aliases_use_exact_normalized_equality(
    position_raw: str,
    expected_from_line1: str,
    expected_to_line1: str,
):
    header = build_preview_header(
        from_party={
            "kind": "legal_entity",
            "company_name": "ООО «Альфа»",
            "position_raw": position_raw,
            "person_name": "Петров Петр Петрович",
        },
        to_party={
            "kind": "legal_entity",
            "company_name": "ООО «Вектор»",
            "position_raw": position_raw,
            "person_name": "Иванов Иван Иванович",
        },
    )
    assert header["from_party"]["rendered"]["line1"] == expected_from_line1
    assert header["to_party"]["rendered"]["line1"] == expected_to_line1
    assert header["from_party"]["rendered"]["line2"] == "ООО «Альфа»"
    assert header["to_party"]["rendered"]["line3"] == "Иванов Иван Иванович"


@pytest.mark.parametrize(
    "position_raw",
    [
        "президент, председатель правления",
        "assistant director",
        "заместитель директора",
    ],
)
def test_formatter_rendered_fallback_for_non_exact_or_unsupported_positions(position_raw: str):
    header = build_preview_header(
        from_party={
            "kind": "legal_entity",
            "company_name": "ООО «Альфа»",
            "position_raw": position_raw,
            "person_name": "Петров Петр Петрович",
        },
        to_party={
            "kind": "legal_entity",
            "company_name": "ООО «Вектор»",
            "position_raw": position_raw,
            "person_name": "Иванов Иван Иванович",
        },
    )
    assert header["from_party"]["rendered"]["line1"] == "От руководителя"
    assert header["to_party"]["rendered"]["line1"] == "Руководителю"


def test_formatter_ip_uses_kind_not_position_and_applies_narrow_antidup():
    header = build_preview_header(
        from_party={
            "kind": "individual_entrepreneur",
            "company_name": "ИП Петров Петр Петрович",
            "position_raw": "директор",
            "person_name": "Петров Петр Петрович",
        },
        to_party={
            "kind": "individual_entrepreneur",
            "company_name": "Индивидуальный предприниматель Иванов Иван Иванович",
            "position_raw": "генеральный директор",
            "person_name": "Иванов Иван Иванович",
        },
    )
    assert header["from_party"]["line1"] == "Индивидуального предпринимателя"
    assert header["to_party"]["line1"] == "Индивидуальному предпринимателю"

    assert header["from_party"]["rendered"] == {
        "line1": "От индивидуального предпринимателя",
        "line2": "ИП Петров Петр Петрович",
        "line3": None,
    }
    assert header["to_party"]["rendered"] == {
        "line1": "Индивидуальному предпринимателю",
        "line2": "Индивидуальный предприниматель Иванов Иван Иванович",
        "line3": None,
    }


def test_formatter_ip_without_person_name_keeps_line3_none():
    header = build_preview_header(
        from_party={
            "kind": "individual_entrepreneur",
            "company_name": "ИП Петров Петр Петрович",
            "position_raw": "президент",
            "person_name": None,
        },
        to_party={
            "kind": "individual_entrepreneur",
            "company_name": "ИП Иванов Иван Иванович",
            "position_raw": None,
            "person_name": None,
        },
    )
    assert header["from_party"]["rendered"] == {
        "line1": "От индивидуального предпринимателя",
        "line2": "ИП Петров Петр Петрович",
        "line3": None,
    }
    assert header["to_party"]["rendered"] == {
        "line1": "Индивидуальному предпринимателю",
        "line2": "ИП Иванов Иван Иванович",
        "line3": None,
    }


def test_formatter_partial_data():
    header = build_preview_header(
        from_party={
            "kind": "unknown",
            "company_name": None,
            "position_raw": None,
            "person_name": None,
        },
        to_party={
            "kind": "legal_entity",
            "company_name": "ООО «Вектор»",
            "position_raw": None,
            "person_name": None,
        },
    )
    assert header["from_party"]["line1"] == "Руководителя"
    assert header["from_party"]["line2"] is None
    assert header["to_party"]["line1"] == "Руководителю ООО «Вектор»"
    assert header["to_party"]["line2"] is None

    assert header["from_party"]["rendered"] == {
        "line1": "От руководителя",
        "line2": None,
        "line3": None,
    }
    assert header["to_party"]["rendered"] == {
        "line1": "Руководителю",
        "line2": "ООО «Вектор»",
        "line3": None,
    }
