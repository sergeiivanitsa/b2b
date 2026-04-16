import logging

from product_api.logging_config import _redact_text, configure_logging


def test_redact_masks_datanewton_query_key():
    message = (
        "HTTP Request: GET "
        "https://api.datanewton.ru/v1/counterparty?key=SECRET123&inn=7701234567"
    )

    redacted = _redact_text(message)

    assert "SECRET123" not in redacted
    assert "key=[redacted]" in redacted


def test_configure_logging_sets_httpx_loggers_to_warning():
    configure_logging("INFO")

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
