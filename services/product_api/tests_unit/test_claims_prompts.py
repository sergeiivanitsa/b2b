import json

from product_api.claims.prompts import build_preview_generation_messages


def test_build_preview_generation_messages_contains_block_constraints():
    messages = build_preview_generation_messages(
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={"debtor_name": "ООО Вектор"},
        allowed_blocks=["facts", "demands"],
        blocked_blocks=["legal_basis"],
        risk_flags=["case_type_uncertain"],
    )

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert "plain text" in messages[0].content.lower()
    assert messages[1].role == "user"
    assert "allowed_blocks" in messages[1].content
    assert "blocked_blocks" in messages[1].content

    json_part = messages[1].content.split("Структурированные данные и ограничения:\n", 1)[1]
    json_payload = json.loads(json_part.split("\n\n", 1)[0])
    assert json_payload["allowed_blocks"] == ["facts", "demands"]
    assert json_payload["blocked_blocks"] == ["legal_basis"]
