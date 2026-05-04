from product_api.claims.prompts import build_preview_generation_messages


def test_build_preview_generation_messages_defines_body_only_contract():
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
    assert messages[1].role == "user"

    combined = "\n".join(message.content for message in messages)
    assert "plain text" in combined.lower()
    assert "только plain text тела preview" in combined
    assert "1–2 содержательных абзаца" in combined
    assert "Абзац 1 описывает основание отношений" in combined
    assert "юридическим opening paragraph" in combined
    assert "договор или иное основание отношений" in combined
    assert "взаимные обязательства" in combined
    assert "case_type=supply" in combined
    assert "поставщик" in combined
    assert "покупатель" in combined
    assert "передать товар" in combined
    assert "принять и оплатить товар" in combined
    assert "case_type=services" in combined
    assert "исполнитель" in combined
    assert "заказчик" in combined
    assert "оказать услуги" in combined
    assert "принять и оплатить услуги" in combined
    assert "case_type=contract_work" in combined
    assert "подрядчик" in combined
    assert "выполнить работы" in combined
    assert "принять и оплатить работы" in combined
    assert "case_type отсутствует" in combined
    assert "нейтральные формулировки" in combined
    assert "без специальных ролей" in combined
    assert "contract_signed=false" in combined
    assert "договор не подписан" in combined
    assert "не утверждай" in combined
    assert '"был заключён договор"' in combined
    assert "не выдумывай номер" in combined
    assert "не выдумывай дату" in combined
    assert "documents_mentioned" in combined
    assert "не копируй technical ids" in combined
    assert "обычные русские названия" in combined
    assert '"обязалось произвести оплату"' in combined
    assert '"требуем оплатить"' in combined
    assert '"просим оплатить"' in combined
    assert '"погасить задолженность в срок"' in combined
    assert "Абзац 2 описывает исполнение и оплату" in combined
    assert "Не возвращай markdown" in combined
    assert "Не возвращай JSON" in combined
    assert "Не используй списки" in combined
    assert "Не дублируй шапку документа" in combined
    assert "Не генерируй заголовок ПРЕТЕНЗИЯ" in combined
    assert "исходящий номер" in combined
    assert "дату самой претензии" in combined
    assert "контакты" in combined
    assert "финальное требование" in combined
    assert "судебный блок" in combined
    assert "статьями ГК РФ/АПК РФ" in combined
    assert "приложения" in combined
    assert "подпись" in combined
    assert "Демо-версия" in combined
    assert "полная версия после оплаты" in combined
    assert "оплатите доступ" in combined
    assert "Не пиши строки header, facts, legal_basis, demand_block, allowed_blocks, blocked_blocks, risk_flags" in combined
    assert '"Кому:"' in combined
    assert '"От кого:"' in combined
    assert '"Адрес:"' in combined
    assert '"E-mail:"' in combined
    assert '"E-mail/контакты:"' in combined
    assert '"Контакты:"' in combined

    assert "Используй только allowed_blocks" not in combined
    assert "По blocked_blocks" not in combined
    assert '"allowed_blocks"' not in messages[1].content
    assert '"blocked_blocks"' not in messages[1].content
    assert '"risk_flags"' not in messages[1].content
    assert "не добавлять правовой блок со ссылками на нормы права" in messages[1].content
    assert "если тип отношений неочевиден" in messages[1].content
