import pytest

from product_api.claims import generation
from product_api.gateway_client import GatewayError
from product_api.settings import get_settings
from shared.schemas import ChatResponse

pytestmark = pytest.mark.asyncio


def _decision() -> dict:
    return {
        "generation_state": "ready",
        "risk_flags": [],
        "allowed_blocks": ["header", "facts", "demands"],
        "blocked_blocks": [],
        "missing_fields": [],
    }


def _assert_artifact_free(text: str):
    lowered = text.lower()
    for forbidden in (
        "header",
        "facts",
        "legal_basis",
        "demand_block",
        "allowed_blocks",
        "blocked_blocks",
        "risk_flags",
        "требует уточнения",
    ):
        assert forbidden not in lowered
    for forbidden_label in (
        "Кому:",
        "От кого:",
        "Адрес:",
        "E-mail:",
        "E-mail/контакты:",
        "Email:",
        "Контакты:",
        "Телефон:",
        "Исходное описание ситуации:",
        "Кредитор:",
        "Должник:",
        "Сумма долга:",
    ):
        assert forbidden_label not in text


def _paragraphs(text: str) -> list[str]:
    return [paragraph for paragraph in text.split("\n\n") if paragraph.strip()]


def _first_paragraph(text: str) -> str:
    return _paragraphs(text)[0]


def _assert_preview_body_contract(text: str):
    _assert_artifact_free(text)
    assert 1 <= len(_paragraphs(text)) <= 2
    assert not any(line.strip().casefold() == "претензия" for line in text.splitlines())
    lowered = text.lower()
    for forbidden in (
        "исх. №",
        "б/н от",
        "требуем оплатить",
        "просим оплатить",
        "погасить задолженность в срок",
        "обратиться в суд",
        "обратимся в суд",
        "в судебном порядке",
        "исковое заявление",
        "арбитражный суд",
        "гк рф",
        "апк рф",
        "гражданский кодекс",
        "приложения",
        "подпись",
        "с уважением",
        "демо-версия",
        "полная версия документа",
        "полная версия после оплаты",
        "доступна после оплаты",
        "оплатите доступ",
    ):
        assert forbidden not in lowered


_VALID_PARAGRAPH_1 = (
    "Между ООО Альфа и ООО Вектор возникли отношения по договору поставки, "
    "в рамках которых поставка товара и его приемка подтверждаются представленными документами."
)
_VALID_PARAGRAPH_2 = (
    "По представленным данным задолженность связана с оплатой поставленного товара, "
    "а срок оплаты определяется условиями договора и первичными документами сторон."
)


async def _generate_with_raw_response(
    monkeypatch,
    raw_response: str,
    *,
    case_type: str | None = "supply",
    normalized_data: dict | None = None,
):
    async def fake_send_chat(_settings, payload):
        return ChatResponse(text=raw_response)

    monkeypatch.setattr(generation, "send_chat", fake_send_chat)
    return await generation.generate_claim_preview(
        get_settings(),
        claim_id=99,
        input_text="ООО Вектор не оплатило поставку",
        case_type=case_type,
        normalized_data=normalized_data
        or {
            "creditor_name": "ООО Альфа",
            "debtor_name": "ООО Вектор",
            "contract_signed": True,
            "contract_number": "34",
            "contract_date": "2024-08-09",
            "debt_amount": 380000,
            "payment_due_date": "2024-09-15",
            "documents_mentioned": ["contract"],
        },
        decision=_decision(),
    )


async def test_generate_claim_preview_success(monkeypatch):
    async def fake_send_chat(_settings, payload):
        assert payload.stream is False
        assert payload.metadata.company_id == 15
        return ChatResponse(text=f"{_VALID_PARAGRAPH_1}\n\n{_VALID_PARAGRAPH_2}")

    monkeypatch.setattr(generation, "send_chat", fake_send_chat)

    result = await generation.generate_claim_preview(
        get_settings(),
        claim_id=15,
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={"debtor_name": "ООО Вектор"},
        decision=_decision(),
    )

    assert result["used_fallback"] is False
    assert result["error_code"] is None
    assert result["generated_preview_text"] == f"{_VALID_PARAGRAPH_1}\n\n{_VALID_PARAGRAPH_2}"
    _assert_preview_body_contract(result["generated_preview_text"])


async def test_generate_claim_preview_fallback_on_gateway_error(monkeypatch):
    async def fake_send_chat(_settings, payload):
        raise GatewayError("boom")

    monkeypatch.setattr(generation, "send_chat", fake_send_chat)

    result = await generation.generate_claim_preview(
        get_settings(),
        claim_id=16,
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={
            "creditor_name": "ООО Альфа",
            "debtor_name": "ООО Вектор",
            "debt_amount": 380000,
            "payment_due_date": "2026-02-01",
        },
        decision=_decision(),
    )

    assert result["used_fallback"] is True
    assert result["error_code"] == "preview_fallback"
    _assert_preview_body_contract(result["generated_preview_text"])
    assert "ООО Альфа" in result["generated_preview_text"]
    assert "ООО Вектор" in result["generated_preview_text"]


async def test_generate_claim_preview_fallback_on_empty_text(monkeypatch):
    async def fake_send_chat(_settings, payload):
        return ChatResponse(text="   ")

    monkeypatch.setattr(generation, "send_chat", fake_send_chat)

    result = await generation.generate_claim_preview(
        get_settings(),
        claim_id=17,
        input_text="ООО Вектор не оплатило поставку",
        case_type=None,
        normalized_data={},
        decision=_decision(),
    )

    assert result["used_fallback"] is True
    assert result["generated_preview_text"]
    _assert_preview_body_contract(result["generated_preview_text"])


@pytest.mark.parametrize(
    "raw_response",
    [
        "header\nfacts\nlegal_basis",
        '{"allowed_blocks":["header"],"text":"Между сторонами возникли отношения."}',
        "## facts\nМежду сторонами возникли отношения.",
        'Кому: ООО "Вектор"\nОт кого: ООО "Строй Керамик Сервис"\nАдрес: г. Хабаровск',
        'Адрес места нахождения: г. Хабаровск\nE-mail/контакты: claim@example.test',
        '```json\n{"allowed_blocks":["header"],"text":"Между сторонами возникли отношения."}\n```',
    ],
)
async def test_generate_claim_preview_fallback_on_artifact_output(monkeypatch, raw_response):
    async def fake_send_chat(_settings, payload):
        return ChatResponse(text=raw_response)

    monkeypatch.setattr(generation, "send_chat", fake_send_chat)

    result = await generation.generate_claim_preview(
        get_settings(),
        claim_id=18,
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={
            "creditor_name": "ООО Альфа",
            "debtor_name": "ООО Вектор",
            "debt_amount": 380000,
            "payment_due_date": "2026-02-01",
        },
        decision=_decision(),
    )

    assert result["used_fallback"] is True
    assert result["error_code"] == "preview_fallback"
    _assert_preview_body_contract(result["generated_preview_text"])


async def test_generate_claim_preview_limits_to_first_two_valid_paragraphs(monkeypatch):
    result = await _generate_with_raw_response(
        monkeypatch,
        f"{_VALID_PARAGRAPH_1}\n\n{_VALID_PARAGRAPH_2}\n\n"
        "В случае неоплаты обратимся в Арбитражный суд.",
    )

    assert result["used_fallback"] is False
    assert result["error_code"] is None
    assert result["generated_preview_text"] == f"{_VALID_PARAGRAPH_1}\n\n{_VALID_PARAGRAPH_2}"
    assert "Арбитражный суд" not in result["generated_preview_text"]


async def test_generate_claim_preview_discards_full_document_tail_without_fallback(monkeypatch):
    raw_response = (
        f"{_VALID_PARAGRAPH_1}\n\n{_VALID_PARAGRAPH_2}\n\n"
        "Исх. №: б/н от 03 мая 2026 года\n"
        "Приложения: договор и акт сверки.\n"
        "С уважением, директор.\n"
        "Полная версия документа будет доступна после оплаты.\n"
        "В случае неоплаты обратимся в Арбитражный суд."
    )

    result = await _generate_with_raw_response(monkeypatch, raw_response)

    assert result["used_fallback"] is False
    assert result["error_code"] is None
    assert result["generated_preview_text"] == f"{_VALID_PARAGRAPH_1}\n\n{_VALID_PARAGRAPH_2}"
    _assert_preview_body_contract(result["generated_preview_text"])


async def test_generate_claim_preview_fallback_when_selected_paragraph_has_title(monkeypatch):
    result = await _generate_with_raw_response(
        monkeypatch,
        f"ПРЕТЕНЗИЯ\n\n{_VALID_PARAGRAPH_1}\n\n{_VALID_PARAGRAPH_2}",
    )

    assert result["used_fallback"] is True
    assert result["error_code"] == "preview_fallback"
    _assert_preview_body_contract(result["generated_preview_text"])


async def test_generate_claim_preview_accepts_two_valid_paragraphs(monkeypatch):
    result = await _generate_with_raw_response(
        monkeypatch,
        f"{_VALID_PARAGRAPH_1}\n\n{_VALID_PARAGRAPH_2}",
    )

    assert result["used_fallback"] is False
    assert result["error_code"] is None
    assert result["generated_preview_text"] == f"{_VALID_PARAGRAPH_1}\n\n{_VALID_PARAGRAPH_2}"


async def test_generate_claim_preview_accepts_one_valid_paragraph(monkeypatch):
    result = await _generate_with_raw_response(monkeypatch, _VALID_PARAGRAPH_1)

    assert result["used_fallback"] is False
    assert result["error_code"] is None
    assert result["generated_preview_text"] == _VALID_PARAGRAPH_1


@pytest.mark.parametrize(
    "raw_response",
    [
        "- Между ООО Альфа и ООО Вектор возникли отношения по поставке.",
        f"{_VALID_PARAGRAPH_1}\n\nТребуем оплатить задолженность.",
        f"{_VALID_PARAGRAPH_1}\n\nОбратимся в Арбитражный суд.",
        f"{_VALID_PARAGRAPH_1}\n\nСогласно ст. 309 ГК РФ обязательства исполняются надлежащим образом.",
    ],
)
async def test_generate_claim_preview_fallback_on_product_shape_output(
    monkeypatch,
    raw_response,
):
    result = await _generate_with_raw_response(monkeypatch, raw_response)

    assert result["used_fallback"] is True
    assert result["error_code"] == "preview_fallback"
    _assert_preview_body_contract(result["generated_preview_text"])


@pytest.mark.parametrize(
    "raw_response",
    [
        "Порядок обмена документами может определяться условиями договора, включая адрес для корреспонденции.",
        "Указанные факты подтверждаются первичными документами сторон.",
    ],
)
async def test_generate_claim_preview_allows_normal_sentences_with_non_label_words(
    monkeypatch,
    raw_response,
):
    async def fake_send_chat(_settings, payload):
        return ChatResponse(text=raw_response)

    monkeypatch.setattr(generation, "send_chat", fake_send_chat)

    result = await generation.generate_claim_preview(
        get_settings(),
        claim_id=19,
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={"debtor_name": "ООО Вектор"},
        decision=_decision(),
    )

    assert result["used_fallback"] is False
    assert result["error_code"] is None
    assert result["generated_preview_text"] == raw_response


async def test_generate_claim_preview_accepts_contract_payment_duty_phrase(monkeypatch):
    raw_response = (
        "Между ООО «Бондюэль-Кубань» и ООО «Вектор» был заключён договор поставки "
        "№17 от 12.01.2026, на основании которого между сторонами возникли взаимные "
        "обязательства, связанные с поставкой, приёмкой и оплатой товара. По условиям "
        "договора ООО «Бондюэль-Кубань» выступило поставщиком и обязалось передать "
        "товар покупателю, тогда как ООО «Вектор», являясь покупателем, обязалось "
        "принять поставленный товар и своевременно произвести оплату его стоимости."
    )

    result = await _generate_with_raw_response(monkeypatch, raw_response)

    assert result["used_fallback"] is False
    assert result["error_code"] is None
    assert result["generated_preview_text"] == raw_response


async def test_generate_claim_preview_strips_plain_text_code_fence(monkeypatch):
    async def fake_send_chat(_settings, payload):
        return ChatResponse(
            text="```text\nМежду сторонами возникли договорные отношения.\n```"
        )

    monkeypatch.setattr(generation, "send_chat", fake_send_chat)

    result = await generation.generate_claim_preview(
        get_settings(),
        claim_id=20,
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={"debtor_name": "ООО Вектор"},
        decision=_decision(),
    )

    assert result["used_fallback"] is False
    assert result["generated_preview_text"] == "Между сторонами возникли договорные отношения."


async def test_safe_draft_preview_omits_artifacts_even_with_blocked_blocks():
    text = generation.build_safe_draft_preview(
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={
            "creditor_name": "ООО Альфа",
            "debtor_name": "ООО Вектор",
            "debt_amount": 380000,
            "payment_due_date": "2026-02-01",
        },
        decision={
            "missing_fields": ["contract_number"],
            "blocked_blocks": ["legal_basis", "attachments"],
            "allowed_blocks": ["header", "facts"],
            "risk_flags": ["case_type_uncertain"],
        },
    )

    _assert_preview_body_contract(text)
    assert "ООО Альфа" in text
    assert "ООО Вектор" in text


async def test_safe_draft_preview_supply_builds_mature_contract_opening():
    text = generation.build_safe_draft_preview(
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={
            "creditor_name": "ООО «Бондюэль-Кубань»",
            "debtor_name": "ООО «Вектор»",
            "contract_signed": True,
            "contract_number": "17",
            "contract_date": "2026-01-12",
            "debt_amount": 380000,
            "payment_due_date": "2024-09-15",
            "documents_mentioned": ["contract"],
        },
        decision=_decision(),
    )

    _assert_preview_body_contract(text)
    opening = _first_paragraph(text)
    assert "Между ООО «Бондюэль-Кубань» и ООО «Вектор»" in opening
    assert "договор поставки №17 от 12.01.2026" in opening
    assert "возникли взаимные обязательства" in opening
    assert "поставкой, приёмкой и оплатой товара" in opening
    assert "ООО «Бондюэль-Кубань» выступило поставщиком" in opening
    assert "ООО «Вектор», являясь покупателем" in opening
    assert "принять поставленный товар" in opening
    assert "произвести оплату его стоимости" in opening
    assert "380 000 руб." in text
    assert "15.09.2024" in text


async def test_safe_draft_preview_services_builds_mature_opening():
    text = generation.build_safe_draft_preview(
        input_text="ООО Вектор не оплатило услуги",
        case_type="services",
        normalized_data={
            "creditor_name": "ООО «Альфа»",
            "debtor_name": "ООО «Вектор»",
            "contract_signed": True,
            "contract_number": "7",
            "contract_date": "2026-01-12",
        },
        decision=_decision(),
    )

    _assert_preview_body_contract(text)
    opening = _first_paragraph(text)
    assert "договор оказания услуг" in opening
    assert "оказанием, приёмкой и оплатой услуг" in opening
    assert "исполнителем" in opening
    assert "заказчиком" in opening
    assert "оказать услуги заказчику" in opening
    assert "принять оказанные услуги" in opening
    assert "произвести оплату их стоимости" in opening


async def test_safe_draft_preview_contract_work_builds_mature_opening():
    text = generation.build_safe_draft_preview(
        input_text="ООО Вектор не оплатило работы",
        case_type="contract_work",
        normalized_data={
            "creditor_name": "ООО «Альфа»",
            "debtor_name": "ООО «Вектор»",
            "contract_signed": True,
            "contract_number": "11",
            "contract_date": "2026-01-12",
        },
        decision=_decision(),
    )

    _assert_preview_body_contract(text)
    opening = _first_paragraph(text)
    assert "договор подряда" in opening
    assert "выполнением, приёмкой и оплатой работ" in opening
    assert "подрядчиком" in opening
    assert "заказчиком" in opening
    assert "выполнить работы для заказчика" in opening
    assert "принять результат выполненных работ" in opening
    assert "произвести оплату их стоимости" in opening


async def test_safe_draft_preview_unknown_uses_neutral_opening():
    text = generation.build_safe_draft_preview(
        input_text="ООО Вектор не оплатило",
        case_type=None,
        normalized_data={
            "creditor_name": "ООО Альфа",
            "debtor_name": "ООО Вектор",
            "documents_mentioned": ["invoice", "specification", "upd", "заявка"],
        },
        decision=_decision(),
    )

    _assert_preview_body_contract(text)
    opening = _first_paragraph(text)
    assert "обязательственные отношения" in opening
    lowered = opening.lower()
    assert "поставщик" not in lowered
    assert "покупатель" not in lowered
    assert "исполнитель" not in lowered
    assert "подрядчик" not in lowered


async def test_safe_draft_preview_contract_reference_with_only_number():
    text = generation.build_safe_draft_preview(
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={
            "creditor_name": "ООО «Альфа»",
            "debtor_name": "ООО «Вектор»",
            "contract_number": "17",
        },
        decision=_decision(),
    )

    _assert_preview_body_contract(text)
    opening = _first_paragraph(text)
    assert "№17" in opening
    assert "от None" not in opening


async def test_safe_draft_preview_contract_reference_with_only_date():
    text = generation.build_safe_draft_preview(
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={
            "creditor_name": "ООО «Альфа»",
            "debtor_name": "ООО «Вектор»",
            "contract_date": "2026-01-12",
        },
        decision=_decision(),
    )

    _assert_preview_body_contract(text)
    opening = _first_paragraph(text)
    assert "от 12.01.2026" in opening
    assert "№None" not in opening


async def test_safe_draft_preview_contract_reference_without_number_or_date():
    text = generation.build_safe_draft_preview(
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={
            "creditor_name": "ООО «Альфа»",
            "debtor_name": "ООО «Вектор»",
            "contract_signed": True,
        },
        decision=_decision(),
    )

    _assert_preview_body_contract(text)
    opening = _first_paragraph(text)
    assert "договор поставки" in opening
    assert "№None" not in opening
    assert "от None" not in opening


async def test_safe_draft_preview_contract_reference_omits_invalid_date():
    text = generation.build_safe_draft_preview(
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={
            "creditor_name": "ООО «Альфа»",
            "debtor_name": "ООО «Вектор»",
            "contract_signed": True,
            "contract_date": "2026-99-99",
        },
        decision=_decision(),
    )

    _assert_preview_body_contract(text)
    opening = _first_paragraph(text)
    assert "договор поставки" in opening
    assert "2026-99-99" not in opening
    assert "от None" not in opening


async def test_safe_draft_preview_documents_only_uses_known_labels():
    text = generation.build_safe_draft_preview(
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={
            "creditor_name": "ООО «Бондюэль-Кубань»",
            "debtor_name": "ООО «Вектор»",
            "documents_mentioned": ["invoice", "upd", "specification", "unknown_doc"],
        },
        decision=_decision(),
    )

    _assert_preview_body_contract(text)
    opening = _first_paragraph(text)
    assert "представленные документы" in opening
    assert "счёт" in opening
    assert "УПД" in opening
    assert "спецификацию" in opening
    assert "unknown_doc" not in opening
    assert "№" not in opening
    assert "от 12.01.2026" not in opening


async def test_safe_draft_preview_cautious_when_contract_not_signed():
    text = generation.build_safe_draft_preview(
        input_text="ООО Вектор не оплатило поставку",
        case_type="supply",
        normalized_data={
            "creditor_name": "ООО «Бондюэль-Кубань»",
            "debtor_name": "ООО «Вектор»",
            "contract_signed": False,
            "contract_number": "17",
            "contract_date": "2026-01-12",
            "documents_mentioned": ["contract"],
        },
        decision=_decision(),
    )

    _assert_preview_body_contract(text)
    opening = _first_paragraph(text)
    assert "был заключён договор" not in opening
    assert "договор поставки №17 от 12.01.2026" in opening
    assert "отношения сторон связаны" in opening
