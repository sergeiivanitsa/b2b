from product_api.claims.datanewton_client import parse_datanewton_counterparty_payload


def test_parse_datanewton_legal_entity_payload():
    payload = {
        "data": {
            "short_name": "ООО «Вектор»",
            "subject_type": "ЮЛ",
            "manager": {
                "fio": "Иванов Иван Иванович",
                "position": "генеральный директор",
            },
            "address": "г. Москва, ул. Пушкина, д. 1",
        }
    }

    parsed = parse_datanewton_counterparty_payload(payload, fallback_inn="7701234567")

    assert parsed is not None
    assert parsed["kind"] == "legal_entity"
    assert parsed["company_name"] == "ООО «Вектор»"
    assert parsed["person_name"] == "Иванов Иван Иванович"
    assert parsed["position_raw"] == "генеральный директор"
    assert parsed["address"] == "г. Москва, ул. Пушкина, д. 1"


def test_parse_datanewton_individual_entrepreneur_payload():
    payload = {
        "result": {
            "entityType": "ИП",
            "full_name": "ИП Петров Петр Петрович",
            "individual": {
                "fio": "Петров Петр Петрович",
            },
            "legal_address": "г. Владивосток, ул. Морская, д. 7",
        }
    }

    parsed = parse_datanewton_counterparty_payload(payload, fallback_inn="780123456789")

    assert parsed is not None
    assert parsed["kind"] == "individual_entrepreneur"
    assert parsed["company_name"] == "ИП Петров Петр Петрович"
    assert parsed["person_name"] == "Петров Петр Петрович"
    assert parsed["position_raw"] is None
    assert parsed["address"] == "г. Владивосток, ул. Морская, д. 7"


def test_parse_datanewton_company_managers_shape():
    payload = {
        "data": {
            "company": {
                "company_names": {
                    "short_name": "ООО «Вектор»",
                    "full_name": "Общество с ограниченной ответственностью «Вектор»",
                },
                "managers": [
                    {
                        "fio": "Иванов Иван Иванович",
                        "position": "генеральный директор",
                    }
                ],
                "address": {"line_address": "г. Москва, ул. Ленина, д. 5"},
            }
        }
    }

    parsed = parse_datanewton_counterparty_payload(payload, fallback_inn="7701234567")

    assert parsed is not None
    assert parsed["company_name"] == "ООО «Вектор»"
    assert parsed["person_name"] == "Иванов Иван Иванович"
    assert parsed["position_raw"] == "генеральный директор"
    assert parsed["address"] == "г. Москва, ул. Ленина, д. 5"


def test_parse_datanewton_prefers_manager_fio_over_unrelated_fio():
    payload = {
        "data": {
            "company": {
                "company_names": {"short_name": "ООО «Альфа»"},
                "founders": [{"fio": "Смирнов Семен Семенович"}],
                "managers": [
                    {
                        "fio": "Петров Петр Петрович",
                        "position": "директор",
                    }
                ],
            }
        }
    }

    parsed = parse_datanewton_counterparty_payload(payload, fallback_inn="7701234567")

    assert parsed is not None
    assert parsed["person_name"] == "Петров Петр Петрович"
    assert parsed["position_raw"] == "директор"
