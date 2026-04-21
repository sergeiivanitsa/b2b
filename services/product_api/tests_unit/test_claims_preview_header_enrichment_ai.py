from __future__ import annotations

import pytest

from product_api.claims import preview_header_enrichment
from product_api.claims.person_name_ai_service import PersonNameAIResult
from product_api.models import Claim
from product_api.settings import Settings

pytestmark = pytest.mark.asyncio


def _build_settings(**overrides: object) -> Settings:
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
        "DATANEWTON_ENABLED": True,
        "DATANEWTON_API_KEY": "test-dn-key",
        "CLAIMS_FIO_AI_ENABLED": True,
    }
    payload.update(overrides)
    return Settings.model_validate(payload)


def _build_claim(normalized_data_json: dict[str, object]) -> Claim:
    return Claim(
        id=1001,
        status="draft",
        generation_state="ready",
        price_rub=990,
        edit_token_hash="test-hash",
        input_text="test input",
        normalized_data_json=normalized_data_json,
    )


@pytest.mark.parametrize(
    ("side", "source_fio", "expected_line3"),
    [
        pytest.param("from", "Ли Виктор Менгинович", "Ли Виктора Менгиновича", id="from_li"),
        pytest.param(
            "from",
            "Мягких Елена Сергеевна",
            "Мягких Елены Сергеевны",
            id="from_myagkih",
        ),
        pytest.param(
            "to",
            "Сапсай Владислав Александрович",
            "Сапсаю Владиславу Александровичу",
            id="to_sapsai",
        ),
        pytest.param(
            "to",
            "Ена Владимир Владиславович",
            "Ене Владимиру Владиславовичу",
            id="to_ena",
        ),
        pytest.param(
            "from",
            "Жукова Павел Михайлович",
            "Жукова Павла Михайловича",
            id="from_zhukova",
        ),
        pytest.param(
            "to",
            "Приходько Владимир Сергеевич",
            "Приходько Владимиру Сергеевичу",
            id="to_prihodko",
        ),
        pytest.param(
            "to",
            "Козаченко Игорь Викторович",
            "Козаченко Игорю Викторовичу",
            id="to_kozachenko",
        ),
    ],
)
async def test_rebuild_claim_preview_header_legal_entity_ai_success(
    monkeypatch: pytest.MonkeyPatch,
    side: str,
    source_fio: str,
    expected_line3: str,
) -> None:
    settings = _build_settings()
    if side == "from":
        normalized_data = {
            "creditor_name": "OOO Alpha",
            "creditor_inn": "7701234567",
            "debtor_name": "OOO Vector",
            "debtor_inn": None,
        }
        expected_party_key = "from_party"
        expected_case = "genitive"
        expected_company = "OOO Alpha"
        source_inn = "7701234567"
    else:
        normalized_data = {
            "creditor_name": "OOO Alpha",
            "creditor_inn": None,
            "debtor_name": "OOO Vector",
            "debtor_inn": "7801234567",
        }
        expected_party_key = "to_party"
        expected_case = "dative"
        expected_company = "OOO Vector"
        source_inn = "7801234567"

    claim = _build_claim(normalized_data)
    calls: list[tuple[str, str]] = []

    async def fake_fetch(_settings: Settings, inn: str) -> dict[str, object] | None:
        if inn != source_inn:
            return None
        return {
            "kind": "legal_entity",
            "company_name": expected_company,
            "position_raw": "генеральный директор",
            "person_name": source_fio,
            "address": None,
        }

    async def fake_transform(
        _settings: Settings,
        *,
        raw_fio: str | None,
        target_case: str,
        entity_kind: str,
        strip_ip_prefix: bool,
    ) -> PersonNameAIResult:
        calls.append((str(raw_fio), target_case))
        assert raw_fio == source_fio
        assert target_case == expected_case
        assert entity_kind == "legal_entity"
        assert strip_ip_prefix is False
        return PersonNameAIResult(
            status="ok",
            fio=expected_line3,
            preprocessed_fio=source_fio,
            error_code=None,
            cache_hit=False,
        )

    monkeypatch.setattr(preview_header_enrichment, "fetch_datanewton_party_by_inn", fake_fetch)
    monkeypatch.setattr(preview_header_enrichment, "transform_person_name_with_ai", fake_transform)

    header = await preview_header_enrichment.rebuild_claim_preview_header(settings, claim)

    assert header["format_version"] == 2
    target_party = header[expected_party_key]
    assert target_party["person_name"] == source_fio
    assert target_party["line2"] == source_fio
    assert target_party["rendered"]["line2"] == expected_company
    assert target_party["rendered"]["line3"] == expected_line3
    assert calls == [(source_fio, expected_case)]


@pytest.mark.parametrize(
    "status",
    ["invalid_response", "timeout", "gateway_error", "empty_input"],
)
async def test_rebuild_claim_preview_header_legal_entity_ai_failure_uses_preprocessed_fio(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    settings = _build_settings()
    source_fio = "Ена Владимир Владиславович"
    claim = _build_claim(
        {
            "creditor_name": "OOO Alpha",
            "creditor_inn": "7701234567",
            "debtor_name": "OOO Vector",
            "debtor_inn": None,
        }
    )

    async def fake_fetch(_settings: Settings, inn: str) -> dict[str, object] | None:
        if inn != "7701234567":
            return None
        return {
            "kind": "legal_entity",
            "company_name": "OOO Alpha",
            "position_raw": "генеральный директор",
            "person_name": source_fio,
            "address": None,
        }

    async def fake_transform(
        _settings: Settings,
        *,
        raw_fio: str | None,
        target_case: str,
        entity_kind: str,
        strip_ip_prefix: bool,
    ) -> PersonNameAIResult:
        assert raw_fio == source_fio
        assert target_case == "genitive"
        assert entity_kind == "legal_entity"
        assert strip_ip_prefix is False
        return PersonNameAIResult(
            status=status,  # type: ignore[arg-type]
            fio=None,
            preprocessed_fio=source_fio,
            error_code=status,
            cache_hit=False,
        )

    monkeypatch.setattr(preview_header_enrichment, "fetch_datanewton_party_by_inn", fake_fetch)
    monkeypatch.setattr(preview_header_enrichment, "transform_person_name_with_ai", fake_transform)

    header = await preview_header_enrichment.rebuild_claim_preview_header(settings, claim)

    assert header["from_party"]["person_name"] == source_fio
    assert header["from_party"]["line2"] == source_fio
    assert header["from_party"]["rendered"]["line2"] == "OOO Alpha"
    assert header["from_party"]["rendered"]["line3"] == source_fio


async def test_rebuild_claim_preview_header_keeps_formatter_line3_when_preprocessed_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _build_settings()
    source_fio = "Иванов Иван Иванович"
    claim = _build_claim(
        {
            "creditor_name": "OOO Alpha",
            "creditor_inn": "7701234567",
            "debtor_name": "OOO Vector",
            "debtor_inn": None,
        }
    )

    async def fake_fetch(_settings: Settings, inn: str) -> dict[str, object] | None:
        if inn != "7701234567":
            return None
        return {
            "kind": "legal_entity",
            "company_name": "OOO Alpha",
            "position_raw": "генеральный директор",
            "person_name": source_fio,
            "address": None,
        }

    async def fake_transform(
        _settings: Settings,
        *,
        raw_fio: str | None,
        target_case: str,
        entity_kind: str,
        strip_ip_prefix: bool,
    ) -> PersonNameAIResult:
        return PersonNameAIResult(
            status="invalid_response",
            fio=None,
            preprocessed_fio=None,
            error_code="invalid_response",
            cache_hit=False,
        )

    monkeypatch.setattr(preview_header_enrichment, "fetch_datanewton_party_by_inn", fake_fetch)
    monkeypatch.setattr(preview_header_enrichment, "transform_person_name_with_ai", fake_transform)

    header = await preview_header_enrichment.rebuild_claim_preview_header(settings, claim)

    assert header["from_party"]["rendered"]["line3"] == "Иванова Ивана Ивановича"


async def test_rebuild_claim_preview_header_applies_ai_to_individual_entrepreneur_line2_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _build_settings()
    source_fio = "ИП Абрамов Дмитрий Вадимович"
    target_company_name = "Индивидуальный предприниматель Суляндзига Аркадий Васильевич"
    claim = _build_claim(
        {
            "creditor_name": "ИП Ромашка",
            "creditor_inn": "770123456789",
            "debtor_name": target_company_name,
            "debtor_inn": "780123456789",
        }
    )
    calls: list[tuple[str | None, str, bool]] = []

    async def fake_fetch(_settings: Settings, inn: str) -> dict[str, object] | None:
        if inn == "770123456789":
            return {
                "kind": "individual_entrepreneur",
                "company_name": "ИП Ромашка",
                "position_raw": None,
                "person_name": source_fio,
                "address": None,
            }
        if inn == "780123456789":
            return {
                "kind": "individual_entrepreneur",
                "company_name": target_company_name,
                "position_raw": None,
                "person_name": None,
                "address": None,
            }
        return {
            "kind": "unknown",
            "company_name": None,
            "position_raw": None,
            "person_name": None,
            "address": None,
        }

    async def fake_transform(
        _settings: Settings,
        *,
        raw_fio: str | None,
        target_case: str,
        entity_kind: str,
        strip_ip_prefix: bool,
    ) -> PersonNameAIResult:
        calls.append((raw_fio, target_case, strip_ip_prefix))
        assert entity_kind == "individual_entrepreneur"
        assert strip_ip_prefix is True
        mapping = {
            ("ИП Абрамов Дмитрий Вадимович", "genitive"): "Абрамова Дмитрия Вадимовича",
            (
                "Индивидуальный предприниматель Суляндзига Аркадий Васильевич",
                "dative",
            ): "Суляндзиге Аркадию Васильевичу",
        }
        return PersonNameAIResult(
            status="ok",
            fio=mapping[(raw_fio, target_case)],
            preprocessed_fio=raw_fio,
            error_code=None,
            cache_hit=False,
        )

    monkeypatch.setattr(preview_header_enrichment, "fetch_datanewton_party_by_inn", fake_fetch)
    monkeypatch.setattr(preview_header_enrichment, "transform_person_name_with_ai", fake_transform)

    header = await preview_header_enrichment.rebuild_claim_preview_header(settings, claim)

    assert header["from_party"]["kind"] == "individual_entrepreneur"
    assert header["from_party"]["person_name"] == source_fio
    assert header["from_party"]["line2"] == source_fio
    assert header["from_party"]["rendered"] == {
        "line1": "От индивидуального предпринимателя",
        "line2": "Абрамова Дмитрия Вадимовича",
        "line3": None,
    }
    assert header["to_party"]["kind"] == "individual_entrepreneur"
    assert header["to_party"]["person_name"] is None
    assert header["to_party"]["line2"] is None
    assert header["to_party"]["rendered"] == {
        "line1": "Индивидуальному предпринимателю",
        "line2": "Суляндзиге Аркадию Васильевичу",
        "line3": None,
    }
    assert calls == [
        ("ИП Абрамов Дмитрий Вадимович", "genitive", True),
        (
            "Индивидуальный предприниматель Суляндзига Аркадий Васильевич",
            "dative",
            True,
        ),
    ]


@pytest.mark.parametrize(
    "status",
    ["invalid_response", "timeout", "gateway_error", "empty_input"],
)
async def test_rebuild_claim_preview_header_ip_ai_failure_uses_preprocessed_fio_for_line2(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    settings = _build_settings()
    source_fio = "ИП Абрамов Дмитрий Вадимович"
    claim = _build_claim(
        {
            "creditor_name": "ИП Абрамов Дмитрий Вадимович",
            "creditor_inn": "770123456789",
            "debtor_name": "OOO Vector",
            "debtor_inn": None,
        }
    )

    async def fake_fetch(_settings: Settings, inn: str) -> dict[str, object] | None:
        if inn != "770123456789":
            return None
        return {
            "kind": "individual_entrepreneur",
            "company_name": "ИП Абрамов Дмитрий Вадимович",
            "position_raw": None,
            "person_name": source_fio,
            "address": None,
        }

    async def fake_transform(
        _settings: Settings,
        *,
        raw_fio: str | None,
        target_case: str,
        entity_kind: str,
        strip_ip_prefix: bool,
    ) -> PersonNameAIResult:
        assert raw_fio == source_fio
        assert target_case == "genitive"
        assert entity_kind == "individual_entrepreneur"
        assert strip_ip_prefix is True
        return PersonNameAIResult(
            status=status,  # type: ignore[arg-type]
            fio=None,
            preprocessed_fio="Абрамов Дмитрий Вадимович",
            error_code=status,
            cache_hit=False,
        )

    monkeypatch.setattr(preview_header_enrichment, "fetch_datanewton_party_by_inn", fake_fetch)
    monkeypatch.setattr(preview_header_enrichment, "transform_person_name_with_ai", fake_transform)

    header = await preview_header_enrichment.rebuild_claim_preview_header(settings, claim)

    assert header["from_party"]["person_name"] == source_fio
    assert header["from_party"]["line2"] == source_fio
    assert header["from_party"]["rendered"]["line1"] == "От индивидуального предпринимателя"
    assert header["from_party"]["rendered"]["line2"] == "Абрамов Дмитрий Вадимович"
    assert header["from_party"]["rendered"]["line3"] is None


async def test_rebuild_claim_preview_header_ip_ai_failure_keeps_formatter_line2_when_preprocessed_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _build_settings()
    source_fio = "ИП Абрамов Дмитрий Вадимович"
    claim = _build_claim(
        {
            "creditor_name": "ИП Абрамов Дмитрий Вадимович",
            "creditor_inn": "770123456789",
            "debtor_name": "OOO Vector",
            "debtor_inn": None,
        }
    )

    async def fake_fetch(_settings: Settings, inn: str) -> dict[str, object] | None:
        if inn != "770123456789":
            return None
        return {
            "kind": "individual_entrepreneur",
            "company_name": "ИП Абрамов Дмитрий Вадимович",
            "position_raw": None,
            "person_name": source_fio,
            "address": None,
        }

    async def fake_transform(
        _settings: Settings,
        *,
        raw_fio: str | None,
        target_case: str,
        entity_kind: str,
        strip_ip_prefix: bool,
    ) -> PersonNameAIResult:
        return PersonNameAIResult(
            status="invalid_response",
            fio=None,
            preprocessed_fio=None,
            error_code="invalid_response",
            cache_hit=False,
        )

    monkeypatch.setattr(preview_header_enrichment, "fetch_datanewton_party_by_inn", fake_fetch)
    monkeypatch.setattr(preview_header_enrichment, "transform_person_name_with_ai", fake_transform)

    header = await preview_header_enrichment.rebuild_claim_preview_header(settings, claim)

    assert header["from_party"]["rendered"]["line1"] == "От индивидуального предпринимателя"
    assert header["from_party"]["rendered"]["line2"] == "Абрамов Дмитрий Вадимович"
    assert header["from_party"]["rendered"]["line3"] is None


async def test_rebuild_claim_preview_header_ip_without_usable_source_skips_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _build_settings()
    claim = _build_claim(
        {
            "creditor_name": None,
            "creditor_inn": "770123456789",
            "debtor_name": "OOO Vector",
            "debtor_inn": None,
        }
    )
    ai_call_count = 0

    async def fake_fetch(_settings: Settings, inn: str) -> dict[str, object] | None:
        if inn != "770123456789":
            return None
        return {
            "kind": "individual_entrepreneur",
            "company_name": None,
            "position_raw": None,
            "person_name": None,
            "address": None,
        }

    async def fake_transform(
        _settings: Settings,
        *,
        raw_fio: str | None,
        target_case: str,
        entity_kind: str,
        strip_ip_prefix: bool,
    ) -> PersonNameAIResult:
        nonlocal ai_call_count
        ai_call_count += 1
        return PersonNameAIResult(
            status="ok",
            fio="unused",
            preprocessed_fio=raw_fio,
            error_code=None,
            cache_hit=False,
        )

    monkeypatch.setattr(preview_header_enrichment, "fetch_datanewton_party_by_inn", fake_fetch)
    monkeypatch.setattr(preview_header_enrichment, "transform_person_name_with_ai", fake_transform)

    header = await preview_header_enrichment.rebuild_claim_preview_header(settings, claim)

    assert ai_call_count == 0
    assert header["from_party"]["kind"] == "individual_entrepreneur"
    assert header["from_party"]["person_name"] is None
    assert header["from_party"]["line2"] is None
    assert header["from_party"]["rendered"]["line1"] == "От индивидуального предпринимателя"
    assert header["from_party"]["rendered"]["line2"] is None
    assert header["from_party"]["rendered"]["line3"] is None


async def test_rebuild_claim_preview_header_skips_ai_when_feature_flag_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _build_settings(CLAIMS_FIO_AI_ENABLED=False)
    source_fio = "Петров Петр Петрович"
    claim = _build_claim(
        {
            "creditor_name": "OOO Alpha",
            "creditor_inn": "7701234567",
            "debtor_name": "OOO Vector",
            "debtor_inn": None,
        }
    )
    ai_call_count = 0

    async def fake_fetch(_settings: Settings, inn: str) -> dict[str, object] | None:
        if inn != "7701234567":
            return None
        return {
            "kind": "legal_entity",
            "company_name": "OOO Alpha",
            "position_raw": "генеральный директор",
            "person_name": source_fio,
            "address": None,
        }

    async def fake_transform(
        _settings: Settings,
        *,
        raw_fio: str | None,
        target_case: str,
        entity_kind: str,
        strip_ip_prefix: bool,
    ) -> PersonNameAIResult:
        nonlocal ai_call_count
        ai_call_count += 1
        return PersonNameAIResult(
            status="ok",
            fio="unused",
            preprocessed_fio=raw_fio,
            error_code=None,
            cache_hit=False,
        )

    monkeypatch.setattr(preview_header_enrichment, "fetch_datanewton_party_by_inn", fake_fetch)
    monkeypatch.setattr(preview_header_enrichment, "transform_person_name_with_ai", fake_transform)

    header = await preview_header_enrichment.rebuild_claim_preview_header(settings, claim)

    assert ai_call_count == 0
    assert header["from_party"]["rendered"]["line3"] == "Петрова Петра Петровича"
