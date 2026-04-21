import json

from product_api.claims.person_name_ai_prompts import build_person_name_ai_messages


def test_build_person_name_ai_messages_contains_strict_json_contract():
    messages = build_person_name_ai_messages(
        fio="Ли Виктор Менгинович",
        target_case="genitive",
        entity_kind="legal_entity",
        strip_ip_prefix=False,
        prompt_version="v1",
    )

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert "JSON-объект вида {\"fio\":\"...\"}" in messages[0].content
    assert "без дополнительных ключей" in messages[0].content.lower()
    assert messages[1].role == "user"

    payload = json.loads(messages[1].content)
    assert payload["task"] == "person_name_case_transform"
    assert payload["prompt_version"] == "v1"
    assert payload["input"] == {
        "fio": "Ли Виктор Менгинович",
        "target_case": "genitive",
        "entity_kind": "legal_entity",
        "strip_ip_prefix": False,
    }
    assert payload["output_schema"] == {"fio": "string"}

