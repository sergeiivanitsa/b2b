from product_api.claims.preview_header_formatter import build_preview_header


def test_formatter_legal_entity_director():
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


def test_formatter_general_director_priority_over_director():
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


def test_formatter_unknown_position_uses_fallback():
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
    assert header["from_party"]["line1"] == "Руководителя ООО «Альфа»"
    assert header["to_party"]["line1"] == "Руководителю ООО «Вектор»"


def test_formatter_ip_uses_kind_not_position():
    header = build_preview_header(
        from_party={
            "kind": "individual_entrepreneur",
            "company_name": "ИП Петров Петр Петрович",
            "position_raw": "директор",
            "person_name": "Петров Петр Петрович",
        },
        to_party={
            "kind": "individual_entrepreneur",
            "company_name": "ИП Иванов Иван Иванович",
            "position_raw": "генеральный директор",
            "person_name": "Иванов Иван Иванович",
        },
    )
    assert header["from_party"]["line1"] == "Индивидуального предпринимателя"
    assert header["to_party"]["line1"] == "Индивидуальному предпринимателю"


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
