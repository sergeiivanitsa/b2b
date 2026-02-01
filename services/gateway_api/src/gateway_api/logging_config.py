import logging
import logging.config
import re

from .request_id import get_request_id

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SECRET_KV_RE = re.compile(
    r"(?i)\b(authorization|token|secret|cookie|set-cookie|api_key|apikey|password)\b\s*[:=]\s*([^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]+=*")
_CONTENT_JSON_RE = re.compile(r'(?i)("content"\s*:\s*")[^"]*(")')
_CONTENT_KV_RE = re.compile(r"(?i)(\bcontent\b\s*[:=]\s*)([^\s,;]+)")


def _redact_text(text: str) -> str:
    text = _EMAIL_RE.sub("[redacted_email]", text)
    text = _CONTENT_JSON_RE.sub(r"\1[redacted]\2", text)
    text = _CONTENT_KV_RE.sub(r"\1[redacted]", text)
    text = _BEARER_RE.sub("Bearer [redacted]", text)
    text = _SECRET_KV_RE.sub(r"\1=[redacted]", text)
    return text


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = _redact_text(message)
        record.args = ()
        return True


def configure_logging(log_level: str) -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_id": {"()": "gateway_api.logging_config.RequestIdFilter"},
                "redact": {"()": "gateway_api.logging_config.RedactionFilter"},
            },
            "formatters": {
                "standard": {
                    "format": "%(levelname)s %(name)s request_id=%(request_id)s %(message)s"
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "filters": ["request_id", "redact"],
                    "level": log_level,
                }
            },
            "loggers": {
                "uvicorn": {
                    "handlers": ["console"],
                    "level": log_level,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["console"],
                    "level": log_level,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": log_level,
                    "propagate": False,
                },
            },
            "root": {"handlers": ["console"], "level": log_level},
        }
    )
