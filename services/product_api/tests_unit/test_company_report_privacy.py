import json

import pytest

from company_report_orchestrator_test_helpers import successful_fake_provider
from product_api.company_reports import build_company_report


@pytest.mark.asyncio
async def test_report_repr_and_serialization_are_safe():
    report = await build_company_report(
        "7700000000",
        provider=successful_fake_provider(),
        request_id="privacy-request",
    )
    rendered = repr(report)
    serialized = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)

    assert "7700000000" not in rendered
    assert "ООО Синтетика Альфа" not in rendered
    assert "Тестов Тест Тестович" not in rendered
    assert "raw_payload" not in serialized
    assert "api-secret" not in serialized
