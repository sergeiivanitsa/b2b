import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_generate_preview_and_get_preview(async_client, engine, monkeypatch):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    patch_resp = await async_client.patch(
        f"/claims/{created['claim_id']}",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        json={
            "case_type": "supply",
            "normalized_data": {
                "creditor_name": "OOO Alpha",
                "creditor_inn": "7701234567",
                "debtor_name": "OOO Vector",
                "debtor_inn": "780123456789",
                "contract_signed": True,
                "debt_amount": 380000,
                "payment_due_date": "2026-02-01",
                "documents_mentioned": ["contract"],
            },
        },
    )
    assert patch_resp.status_code == 200

    decision = {
        "generation_state": "ready",
        "risk_flags": [],
        "allowed_blocks": ["header", "facts", "demands"],
        "blocked_blocks": [],
        "missing_fields": [],
    }

    async def fake_generate_claim_preview(
        _settings, *, claim_id, input_text, case_type, normalized_data, decision
    ):
        return {
            "generated_preview_text": "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё",
            "used_fallback": False,
            "error_code": None,
        }

    from product_api.routers import public_claims as public_claims_router

    monkeypatch.setattr(public_claims_router, "evaluate_claim_rules", lambda **_: decision)
    monkeypatch.setattr(
        public_claims_router,
        "generate_claim_preview",
        fake_generate_claim_preview,
    )

    generate_resp = await async_client.post(
        f"/claims/{created['claim_id']}/generate-preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert generate_resp.status_code == 200
    preview = generate_resp.json()
    assert preview["claim_id"] == created["claim_id"]
    assert preview["generation_state"] == "ready"
    assert preview["generated_preview_text"] == "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё"
    assert preview["preview_header"]["from_party"]["line1"] == "Руководителя OOO Alpha"
    assert preview["preview_header"]["to_party"]["line1"] == "Индивидуальному предпринимателю"

    get_preview_resp = await async_client.get(
        f"/claims/{created['claim_id']}/preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert get_preview_resp.status_code == 200
    get_payload = get_preview_resp.json()
    assert get_payload["generated_preview_text"] == "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё"
    assert get_payload["preview_header"]["from_party"]["line1"] == "Руководителя OOO Alpha"
    assert get_payload["preview_header"]["to_party"]["line1"] == "Индивидуальному предпринимателю"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text(
                "SELECT generation_state, risk_flags_json, allowed_blocks_json, "
                "blocked_blocks_json, generated_preview_text "
                "FROM claims WHERE id = :id"
            ),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        assert row[0] == "ready"
        assert row[1] == []
        assert row[2] == ["header", "facts", "demands"]
        assert row[3] == []
        assert row[4] == "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё"


@pytest.mark.parametrize(
    ("source_fio", "expected_from_line3", "expected_to_line3"),
    [
        pytest.param(
            "АБДУСАМАТОВ АЗАМАТ КАРОМАТОВИЧ",
            "Абдусаматова Азамата Кароматовича",
            "Абдусаматову Азамату Кароматовичу",
            id="all_caps_male_structured_inflect",
        ),
        pytest.param(
            "ИЛЬИНА ЮЛИЯ СЕРГЕЕВНА",
            "Ильиной Юлии Сергеевны",
            "Ильиной Юлии Сергеевне",
            id="all_caps_female_structured_inflect",
        ),
        pytest.param(
            "СМИРНОВА ЛЮБОВЬ ИВАНОВНА",
            "Смирнова Любовь Ивановна",
            "Смирнова Любовь Ивановна",
            id="all_caps_structured_normalize_only",
        ),
        pytest.param(
            "IVANOV IVAN IVANOVICH",
            "IVANOV IVAN IVANOVICH",
            "IVANOV IVAN IVANOVICH",
            id="latin_raw_fallback",
        ),
        pytest.param(
            "Петров П.П.",
            "Петров П.П.",
            "Петров П.П.",
            id="initials_raw_fallback",
        ),
        pytest.param(
            "Иванов Иван",
            "Иванов Иван",
            "Иванов Иван",
            id="not_three_words_raw_fallback",
        ),
        pytest.param(
            "ИВАНОВ-ПЕТРОВ ИВАН ИВАНОВИЧ",
            "ИВАНОВ-ПЕТРОВ ИВАН ИВАНОВИЧ",
            "ИВАНОВ-ПЕТРОВ ИВАН ИВАНОВИЧ",
            id="hyphen_raw_fallback",
        ),
        pytest.param(
            "ИВАНИЦА СЕРГЕЙ ПЕТРОВИЧ",
            "Иваницы Сергея Петровича",
            "Иванице Сергею Петровичу",
            id="ivanitsa_male_all_caps_override",
        ),
        pytest.param(
            "ИВАНИЦА АННА ПЕТРОВНА",
            "Иваница Анны Петровны",
            "Иваница Анне Петровне",
            id="ivanitsa_female_all_caps_override",
        ),
    ],
)
async def test_generate_and_get_preview_keep_line3_consistent_with_write_path_contract(
    async_client,
    engine,
    monkeypatch,
    source_fio: str,
    expected_from_line3: str,
    expected_to_line3: str,
):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    from product_api.claims import datanewton_client
    from product_api.routers import public_claims as public_claims_router

    monkeypatch.setattr(public_claims_router.settings, "datanewton_enabled", True)
    monkeypatch.setattr(public_claims_router.settings, "datanewton_api_key", "test-key")
    monkeypatch.setattr(
        public_claims_router.settings,
        "datanewton_counterparty_filters",
        ["MANAGER_BLOCK", "ADDRESS_BLOCK"],
    )
    monkeypatch.setattr(public_claims_router.settings, "datanewton_cache_ttl_seconds", 0)
    monkeypatch.setattr(datanewton_client, "_client_singleton", None)

    payloads_by_inn = {
        "7701234567": {
            "data": {
                "company": {
                    "company_names": {"short_name": "OOO Alpha"},
                    "managers": [
                        {
                            "fio": source_fio,
                            "position": "генеральный директор",
                        }
                    ],
                    "address": {"line_address": "Moscow"},
                }
            }
        },
        "7801234567": {
            "data": {
                "company": {
                    "company_names": {"short_name": "OOO Vector"},
                    "managers": [
                        {
                            "fio": source_fio,
                            "position": "директор",
                        }
                    ],
                    "address": {"line_address": "Saint Petersburg"},
                }
            }
        },
    }

    class FakeResponse:
        def __init__(self, payload: dict):
            self.status_code = 200
            self._payload = payload
            self.text = str(payload)

        def json(self) -> dict:
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, params=None):
            request_params = dict(params or {})
            inn = request_params.get("inn")
            payload = payloads_by_inn.get(inn)
            if payload is None:
                raise AssertionError(f"Unexpected inn: {inn}")
            return FakeResponse(payload)

    monkeypatch.setattr(datanewton_client.httpx, "AsyncClient", FakeAsyncClient)

    patch_resp = await async_client.patch(
        f"/claims/{created['claim_id']}",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
        json={
            "case_type": "supply",
            "normalized_data": {
                "creditor_name": "OOO Alpha",
                "creditor_inn": "7701234567",
                "debtor_name": "OOO Vector",
                "debtor_inn": "7801234567",
                "contract_signed": True,
                "debt_amount": 380000,
                "payment_due_date": "2026-02-01",
                "documents_mentioned": ["contract"],
            },
        },
    )
    assert patch_resp.status_code == 200
    patch_payload = patch_resp.json()
    assert patch_payload["preview_header"]["format_version"] == 2
    assert patch_payload["preview_header"]["from_party"]["rendered"]["line2"] == "OOO Alpha"
    assert patch_payload["preview_header"]["to_party"]["rendered"]["line2"] == "OOO Vector"
    assert patch_payload["preview_header"]["from_party"]["rendered"]["line3"] == expected_from_line3
    assert patch_payload["preview_header"]["to_party"]["rendered"]["line3"] == expected_to_line3

    decision = {
        "generation_state": "ready",
        "risk_flags": [],
        "allowed_blocks": ["header", "facts", "demands"],
        "blocked_blocks": [],
        "missing_fields": [],
    }

    async def fake_generate_claim_preview(
        _settings, *, claim_id, input_text, case_type, normalized_data, decision
    ):
        return {
            "generated_preview_text": "Р§РµСЂРЅРѕРІРёРє РїСЂРµС‚РµРЅР·РёРё",
            "used_fallback": False,
            "error_code": None,
        }

    monkeypatch.setattr(public_claims_router, "evaluate_claim_rules", lambda **_: decision)
    monkeypatch.setattr(
        public_claims_router,
        "generate_claim_preview",
        fake_generate_claim_preview,
    )

    generate_resp = await async_client.post(
        f"/claims/{created['claim_id']}/generate-preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert generate_resp.status_code == 200
    generate_payload = generate_resp.json()
    assert generate_payload["preview_header"]["format_version"] == 2
    assert generate_payload["preview_header"]["from_party"]["person_name"] == source_fio
    assert generate_payload["preview_header"]["from_party"]["line2"] == source_fio
    assert generate_payload["preview_header"]["to_party"]["person_name"] == source_fio
    assert generate_payload["preview_header"]["to_party"]["line2"] == source_fio
    assert generate_payload["preview_header"]["from_party"]["rendered"]["line2"] == "OOO Alpha"
    assert generate_payload["preview_header"]["to_party"]["rendered"]["line2"] == "OOO Vector"
    assert generate_payload["preview_header"]["from_party"]["rendered"]["line3"] == expected_from_line3
    assert generate_payload["preview_header"]["to_party"]["rendered"]["line3"] == expected_to_line3

    get_preview_resp = await async_client.get(
        f"/claims/{created['claim_id']}/preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert get_preview_resp.status_code == 200
    get_payload = get_preview_resp.json()
    assert get_payload["preview_header"]["format_version"] == 2
    assert get_payload["preview_header"]["from_party"]["rendered"]["line2"] == "OOO Alpha"
    assert get_payload["preview_header"]["to_party"]["rendered"]["line2"] == "OOO Vector"
    assert get_payload["preview_header"]["from_party"]["rendered"]["line3"] == expected_from_line3
    assert get_payload["preview_header"]["to_party"]["rendered"]["line3"] == expected_to_line3

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text("SELECT preview_header_json FROM claims WHERE id = :id"),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        saved_header = row[0]

    assert saved_header["format_version"] == 2
    assert saved_header["from_party"]["person_name"] == source_fio
    assert saved_header["from_party"]["line2"] == source_fio
    assert saved_header["from_party"]["rendered"]["line2"] == "OOO Alpha"
    assert saved_header["from_party"]["rendered"]["line3"] == expected_from_line3
    assert saved_header["to_party"]["person_name"] == source_fio
    assert saved_header["to_party"]["line2"] == source_fio
    assert saved_header["to_party"]["rendered"]["line2"] == "OOO Vector"
    assert saved_header["to_party"]["rendered"]["line3"] == expected_to_line3


async def test_generate_preview_insufficient_data_blocks(async_client, engine, monkeypatch):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    decision = {
        "generation_state": "insufficient_data",
        "risk_flags": ["case_type_uncertain"],
        "allowed_blocks": ["header", "facts"],
        "blocked_blocks": ["legal_basis"],
        "missing_fields": ["creditor_name", "debt_amount"],
    }

    from product_api.routers import public_claims as public_claims_router

    monkeypatch.setattr(public_claims_router, "evaluate_claim_rules", lambda **_: decision)

    generate_resp = await async_client.post(
        f"/claims/{created['claim_id']}/generate-preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert generate_resp.status_code == 409
    assert generate_resp.json()["detail"]["code"] == "insufficient_data"

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text(
                "SELECT generation_state, generated_preview_text FROM claims WHERE id = :id"
            ),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        assert row[0] == "insufficient_data"
        assert row[1] is None


async def test_get_preview_upgrades_legacy_header_full_raw_without_mutating_stored_payload(
    async_client,
    engine,
):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    legacy_header = {
        "from_party": {
            "kind": "legal_entity",
            "company_name": "ООО «Stored Alpha»",
            "position_raw": "генеральный директор",
            "person_name": "Петров Петр Петрович",
            "line1": "Генерального директора ООО «Stored Alpha»",
            "line2": "Петров Петр Петрович",
        },
        "to_party": {
            "kind": "legal_entity",
            "company_name": "ООО «Stored Vector»",
            "position_raw": "director",
            "person_name": "Ivanov Ivan Ivanovich",
            "line1": "Директору ООО «Stored Vector»",
            "line2": "Ivanov Ivan Ivanovich",
        },
    }
    normalized_data = {
        "creditor_name": "Fallback Alpha",
        "debtor_name": "Fallback Vector",
        "missing_fields": [],
    }
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await session.execute(
            text(
                "UPDATE claims "
                "SET generation_state = :generation_state, "
                "generated_preview_text = :generated_preview_text, "
                "normalized_data_json = :normalized_data_json, "
                "preview_header_json = :preview_header_json "
                "WHERE id = :id"
            ),
            {
                "generation_state": "ready",
                "generated_preview_text": "Draft preview text",
                "normalized_data_json": normalized_data,
                "preview_header_json": legacy_header,
                "id": created["claim_id"],
            },
        )
        await session.commit()

    get_preview_resp = await async_client.get(
        f"/claims/{created['claim_id']}/preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert get_preview_resp.status_code == 200
    payload = get_preview_resp.json()
    assert payload["preview_header"]["format_version"] == 2
    assert payload["preview_header"]["from_party"]["line1"] == "Генерального директора ООО «Stored Alpha»"
    assert payload["preview_header"]["from_party"]["line2"] == "Петров Петр Петрович"
    assert payload["preview_header"]["from_party"]["rendered"] == {
        "line1": "От генерального директора",
        "line2": "ООО «Stored Alpha»",
        "line3": "Петров Петр Петрович",
    }
    assert payload["preview_header"]["to_party"]["line1"] == "Директору ООО «Stored Vector»"
    assert payload["preview_header"]["to_party"]["line2"] == "Ivanov Ivan Ivanovich"
    assert payload["preview_header"]["to_party"]["rendered"] == {
        "line1": "Директору",
        "line2": "ООО «Stored Vector»",
        "line3": "Ivanov Ivan Ivanovich",
    }

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text("SELECT preview_header_json FROM claims WHERE id = :id"),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        stored_header = row[0]

    assert stored_header == legacy_header
    assert "format_version" not in stored_header
    assert "rendered" not in stored_header["from_party"]
    assert "rendered" not in stored_header["to_party"]


async def test_get_preview_upgrades_legacy_header_with_normalized_fallback_without_mutation(
    async_client,
    engine,
):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    legacy_header = {
        "from_party": {
            "kind": "legal_entity",
            "company_name": None,
            "position_raw": None,
            "person_name": None,
            "line1": "Руководителя ООО «Old Alpha»",
            "line2": None,
        },
        "to_party": {
            "kind": "legal_entity",
            "company_name": None,
            "position_raw": None,
            "person_name": None,
            "line1": "Руководителю ООО «Old Vector»",
            "line2": None,
        },
    }
    normalized_data = {
        "creditor_name": "Fallback Alpha",
        "debtor_name": "Fallback Vector",
        "missing_fields": [],
    }
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await session.execute(
            text(
                "UPDATE claims "
                "SET generation_state = :generation_state, "
                "generated_preview_text = :generated_preview_text, "
                "normalized_data_json = :normalized_data_json, "
                "preview_header_json = :preview_header_json "
                "WHERE id = :id"
            ),
            {
                "generation_state": "ready",
                "generated_preview_text": "Draft preview text",
                "normalized_data_json": normalized_data,
                "preview_header_json": legacy_header,
                "id": created["claim_id"],
            },
        )
        await session.commit()

    get_preview_resp = await async_client.get(
        f"/claims/{created['claim_id']}/preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert get_preview_resp.status_code == 200
    payload = get_preview_resp.json()
    assert payload["preview_header"]["format_version"] == 2
    assert payload["preview_header"]["from_party"]["line1"] == "Руководителя ООО «Old Alpha»"
    assert payload["preview_header"]["from_party"]["line2"] is None
    assert payload["preview_header"]["from_party"]["rendered"] == {
        "line1": "От руководителя",
        "line2": "Fallback Alpha",
        "line3": None,
    }
    assert payload["preview_header"]["to_party"]["line1"] == "Руководителю ООО «Old Vector»"
    assert payload["preview_header"]["to_party"]["line2"] is None
    assert payload["preview_header"]["to_party"]["rendered"] == {
        "line1": "Руководителю",
        "line2": "Fallback Vector",
        "line3": None,
    }

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text("SELECT preview_header_json FROM claims WHERE id = :id"),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        stored_header = row[0]

    assert stored_header == legacy_header
    assert "format_version" not in stored_header
    assert "rendered" not in stored_header["from_party"]
    assert "rendered" not in stored_header["to_party"]


async def test_get_preview_upgrades_legacy_broken_header_with_emergency_bridge_without_mutation(
    async_client,
    engine,
):
    create_resp = await async_client.post(
        "/claims",
        json={"input_text": "OOO Vector did not pay for delivery"},
    )
    assert create_resp.status_code == 200
    created = create_resp.json()

    legacy_header = {
        "from_party": {
            "line1": "Рук. ООО «Альфа»",
            "line2": "Петров П.П.",
        },
        "to_party": {
            "line1": "Кому: ???",
            "line2": None,
        },
    }
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        await session.execute(
            text(
                "UPDATE claims "
                "SET generation_state = :generation_state, "
                "generated_preview_text = :generated_preview_text, "
                "normalized_data_json = :normalized_data_json, "
                "preview_header_json = :preview_header_json "
                "WHERE id = :id"
            ),
            {
                "generation_state": "ready",
                "generated_preview_text": "Draft preview text",
                "normalized_data_json": None,
                "preview_header_json": legacy_header,
                "id": created["claim_id"],
            },
        )
        await session.commit()

    get_preview_resp = await async_client.get(
        f"/claims/{created['claim_id']}/preview",
        headers={"X-Claim-Edit-Token": created["edit_token"]},
    )
    assert get_preview_resp.status_code == 200
    payload = get_preview_resp.json()
    assert payload["preview_header"]["format_version"] == 2
    assert payload["preview_header"]["from_party"]["line1"] == "Рук. ООО «Альфа»"
    assert payload["preview_header"]["from_party"]["line2"] == "Петров П.П."
    assert payload["preview_header"]["from_party"]["rendered"] == {
        "line1": "Рук. ООО «Альфа»",
        "line2": None,
        "line3": "Петров П.П.",
    }
    assert payload["preview_header"]["to_party"]["line1"] == "Кому: ???"
    assert payload["preview_header"]["to_party"]["line2"] is None
    assert payload["preview_header"]["to_party"]["rendered"] == {
        "line1": "Кому: ???",
        "line2": None,
        "line3": None,
    }

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        claim_row = await session.execute(
            text("SELECT preview_header_json FROM claims WHERE id = :id"),
            {"id": created["claim_id"]},
        )
        row = claim_row.first()
        assert row is not None
        stored_header = row[0]

    assert stored_header == legacy_header
    assert "format_version" not in stored_header
    assert "rendered" not in stored_header["from_party"]
    assert "rendered" not in stored_header["to_party"]
