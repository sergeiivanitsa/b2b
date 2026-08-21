import json

import pytest
from pydantic import ValidationError

from company_report_signal_test_helpers import complete_company_report
from product_api.company_reports.schemas import (
    CompanyReportCreateRequest,
    assert_public_payload_is_safe,
    build_public_signals,
    build_public_snapshot,
)
from product_api.company_reports.service import (
    InvalidCompanyReportIdentifierError,
    validate_company_report_inn,
)
from product_api.company_reports.signals import evaluate_signals


def test_request_models_forbid_extra_fields():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CompanyReportCreateRequest.model_validate(
            {"inn": "7700000000", "provider": "datanewton"}
        )


@pytest.mark.parametrize("value", ["7700000000000", "770000000000000", "abc"])
def test_identifier_helper_rejects_non_inn_identifiers(value):
    with pytest.raises(InvalidCompanyReportIdentifierError):
        validate_company_report_inn(value)


def test_public_projection_is_allowlisted_and_keeps_decimal_exactness():
    report = complete_company_report(report_version="2")
    snapshot = build_public_snapshot(report)
    assert snapshot.report_version == "2"
    signals = build_public_signals(evaluate_signals(report))
    payload = {
        "report": snapshot.model_dump(mode="json"),
        "signals": signals.model_dump(mode="json"),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert_public_payload_is_safe(payload)
    for forbidden in (
        "raw_payload",
        "headers",
        "authorization",
        "api_key",
        "apikey",
        "provider_limit_metadata",
        "request_id",
        "endpoint",
        "response_hash",
        "worker_token",
        "lease_expires_at",
        "safe_error_type",
    ):
        assert forbidden not in serialized.lower()
    assert snapshot.completeness.ratio == report.completeness.ratio
