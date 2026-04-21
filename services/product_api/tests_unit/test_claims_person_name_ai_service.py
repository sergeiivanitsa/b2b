import json

import httpx
import pytest

from product_api.claims import person_name_ai_service
from product_api.gateway_client import GatewayError
from product_api.settings import Settings
from shared.schemas import ChatResponse

pytestmark = pytest.mark.asyncio


def _build_settings(**overrides) -> Settings:
    payload = {
        "DATABASE_URL": "postgresql+asyncpg://app:app@postgres:5432/app",
        "GATEWAY_URL": "http://gateway_api:8001",
        "GATEWAY_SHARED_SECRET": "test-shared-secret",
        "AUTH_TOKEN_SECRET": "test-auth-secret",
        "CLAIM_EDIT_TOKEN_SECRET": "test-claim-edit-secret",
        "CLAIMS_UPLOAD_DIR": "C:/tmp/claims",
        "INVITE_TOKEN_SECRET": "test-invite-secret",
        "SESSION_SECRET": "test-session-secret",
        "EMAIL_FROM": "no-reply@example.com",
        "CLAIMS_FIO_AI_MODEL": "gpt-5.2",
        "CLAIMS_FIO_AI_PROMPT_VERSION": "v1",
        "CLAIMS_FIO_AI_TIMEOUT_SECONDS": 10,
        "CLAIMS_FIO_AI_CACHE_TTL_SECONDS": 3600,
        "CLAIMS_FIO_AI_NEGATIVE_CACHE_TTL_SECONDS": 300,
    }
    payload.update(overrides)
    return Settings.model_validate(payload)


@pytest.fixture(autouse=True)
def _clear_fio_ai_cache():
    person_name_ai_service.clear_person_name_ai_cache()


async def test_transform_person_name_success_uses_gateway_contract(monkeypatch):
    settings = _build_settings(CLAIMS_FIO_AI_PROMPT_VERSION="v7")
    captured: dict[str, object] = {}

    async def fake_send_chat(_settings, payload):
        captured["payload"] = payload
        return ChatResponse(text='{"fio":"Ли Виктора Менгиновича"}')

    monkeypatch.setattr(person_name_ai_service, "send_chat", fake_send_chat)

    result = await person_name_ai_service.transform_person_name_with_ai(
        settings,
        raw_fio="Ли Виктор Менгинович",
        target_case="genitive",
        entity_kind="legal_entity",
        strip_ip_prefix=False,
    )

    assert result.status == "ok"
    assert result.fio == "Ли Виктора Менгиновича"
    assert result.preprocessed_fio == "Ли Виктор Менгинович"
    assert result.error_code is None
    assert result.cache_hit is False

    payload = captured["payload"]
    assert payload.model == settings.claims_fio_ai_model
    assert payload.stream is False
    assert payload.timeout == settings.claims_fio_ai_timeout_seconds
    assert payload.metadata.company_id == 0
    assert payload.metadata.user_id == 0
    assert payload.metadata.conversation_id == 0
    assert payload.metadata.message_id == 0
    context = json.loads(payload.messages[1].content)
    assert context["prompt_version"] == "v7"
    assert context["input"]["target_case"] == "genitive"
    assert context["input"]["entity_kind"] == "legal_entity"


async def test_transform_person_name_empty_input_skips_gateway(monkeypatch):
    settings = _build_settings()
    called = False

    async def fake_send_chat(_settings, payload):
        nonlocal called
        called = True
        return ChatResponse(text='{"fio":"unused"}')

    monkeypatch.setattr(person_name_ai_service, "send_chat", fake_send_chat)

    result = await person_name_ai_service.transform_person_name_with_ai(
        settings,
        raw_fio="   ",
        target_case="genitive",
        entity_kind="legal_entity",
        strip_ip_prefix=False,
    )

    assert result.status == "empty_input"
    assert result.fio is None
    assert result.preprocessed_fio is None
    assert result.error_code is None
    assert called is False


async def test_transform_person_name_invalid_json_is_negative_cached(monkeypatch):
    settings = _build_settings()
    call_count = 0

    async def fake_send_chat(_settings, payload):
        nonlocal call_count
        call_count += 1
        return ChatResponse(text="not-json")

    monkeypatch.setattr(person_name_ai_service, "send_chat", fake_send_chat)

    first = await person_name_ai_service.transform_person_name_with_ai(
        settings,
        raw_fio="Сапсай Владислав Александрович",
        target_case="dative",
        entity_kind="legal_entity",
        strip_ip_prefix=False,
    )
    second = await person_name_ai_service.transform_person_name_with_ai(
        settings,
        raw_fio="Сапсай Владислав Александрович",
        target_case="dative",
        entity_kind="legal_entity",
        strip_ip_prefix=False,
    )

    assert first.status == "invalid_response"
    assert first.error_code == "invalid_response"
    assert first.cache_hit is False
    assert second.status == "invalid_response"
    assert second.cache_hit is True
    assert call_count == 1


async def test_transform_person_name_positive_cache_hit(monkeypatch):
    settings = _build_settings()
    call_count = 0

    async def fake_send_chat(_settings, payload):
        nonlocal call_count
        call_count += 1
        return ChatResponse(text='{"fio":"Ене Владимиру Владиславовичу"}')

    monkeypatch.setattr(person_name_ai_service, "send_chat", fake_send_chat)

    first = await person_name_ai_service.transform_person_name_with_ai(
        settings,
        raw_fio="Ена Владимир Владиславович",
        target_case="dative",
        entity_kind="legal_entity",
        strip_ip_prefix=False,
    )
    second = await person_name_ai_service.transform_person_name_with_ai(
        settings,
        raw_fio="Ена Владимир Владиславович",
        target_case="dative",
        entity_kind="legal_entity",
        strip_ip_prefix=False,
    )

    assert first.status == "ok"
    assert first.cache_hit is False
    assert second.status == "ok"
    assert second.cache_hit is True
    assert call_count == 1


@pytest.mark.parametrize(
    "raw_response",
    [
        '{"fio":"Иванову Ивану Ивановичу","extra":"x"}',
        '{"fio":"Иванову Ивану"}',
        '{"fio":"Иванову Ивану Ивановичу\\n"}',
        '{"fio":"Иванову, Ивану Ивановичу"}',
    ],
)
async def test_transform_person_name_invalid_response_variants(
    monkeypatch,
    raw_response: str,
):
    settings = _build_settings()

    async def fake_send_chat(_settings, payload):
        return ChatResponse(text=raw_response)

    monkeypatch.setattr(person_name_ai_service, "send_chat", fake_send_chat)

    result = await person_name_ai_service.transform_person_name_with_ai(
        settings,
        raw_fio="Иванов Иван Иванович",
        target_case="dative",
        entity_kind="legal_entity",
        strip_ip_prefix=False,
    )

    assert result.status == "invalid_response"
    assert result.fio is None
    assert result.preprocessed_fio == "Иванов Иван Иванович"
    assert result.error_code == "invalid_response"


async def test_transform_person_name_gateway_error(monkeypatch):
    settings = _build_settings()

    async def fake_send_chat(_settings, payload):
        raise GatewayError("boom")

    monkeypatch.setattr(person_name_ai_service, "send_chat", fake_send_chat)

    result = await person_name_ai_service.transform_person_name_with_ai(
        settings,
        raw_fio="Козаченко Игорь Викторович",
        target_case="dative",
        entity_kind="legal_entity",
        strip_ip_prefix=False,
    )

    assert result.status == "gateway_error"
    assert result.fio is None
    assert result.preprocessed_fio == "Козаченко Игорь Викторович"
    assert result.error_code == "gateway_error"


async def test_transform_person_name_timeout(monkeypatch):
    settings = _build_settings()

    async def fake_send_chat(_settings, payload):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(person_name_ai_service, "send_chat", fake_send_chat)

    result = await person_name_ai_service.transform_person_name_with_ai(
        settings,
        raw_fio="Приходько Владимир Сергеевич",
        target_case="dative",
        entity_kind="legal_entity",
        strip_ip_prefix=False,
    )

    assert result.status == "timeout"
    assert result.fio is None
    assert result.preprocessed_fio == "Приходько Владимир Сергеевич"
    assert result.error_code == "timeout"


async def test_strip_ip_prefix_is_applied_only_at_start(monkeypatch):
    settings = _build_settings()
    sent_inputs: list[str] = []

    async def fake_send_chat(_settings, payload):
        context = json.loads(payload.messages[1].content)
        sent_input_fio = context["input"]["fio"]
        sent_inputs.append(sent_input_fio)
        return ChatResponse(text=json.dumps({"fio": sent_input_fio}, ensure_ascii=False))

    monkeypatch.setattr(person_name_ai_service, "send_chat", fake_send_chat)

    first = await person_name_ai_service.transform_person_name_with_ai(
        settings,
        raw_fio="ИП Абрамов Дмитрий Вадимович",
        target_case="genitive",
        entity_kind="individual_entrepreneur",
        strip_ip_prefix=True,
    )
    second = await person_name_ai_service.transform_person_name_with_ai(
        settings,
        raw_fio="Компания ИП Абрамов Дмитрий Вадимович",
        target_case="genitive",
        entity_kind="individual_entrepreneur",
        strip_ip_prefix=True,
    )

    assert first.status == "ok"
    assert first.preprocessed_fio == "Абрамов Дмитрий Вадимович"
    assert second.status == "ok"
    assert second.preprocessed_fio == "Компания ИП Абрамов Дмитрий Вадимович"
    assert sent_inputs == [
        "Абрамов Дмитрий Вадимович",
        "Компания ИП Абрамов Дмитрий Вадимович",
    ]

