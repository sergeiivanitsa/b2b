from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "dev"
    log_level: str = "INFO"
    database_url: str = Field(..., validation_alias="DATABASE_URL")
    gateway_url: str = Field(..., validation_alias="GATEWAY_URL")
    gateway_shared_secret: str = Field(..., validation_alias="GATEWAY_SHARED_SECRET")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    superadmin_email: str | None = Field(default=None, validation_alias="SUPERADMIN_EMAIL")
    auth_token_secret: str = Field(..., validation_alias="AUTH_TOKEN_SECRET")
    auth_token_ttl_seconds: int = Field(
        default=900, validation_alias="AUTH_TOKEN_TTL_SECONDS"
    )
    claim_edit_token_secret: str = Field(..., validation_alias="CLAIM_EDIT_TOKEN_SECRET")
    claims_price_rub: int = Field(default=990, validation_alias="CLAIMS_PRICE_RUB")
    claims_upload_dir: str = Field(..., validation_alias="CLAIMS_UPLOAD_DIR")
    claims_max_file_size_bytes: int = Field(
        default=10 * 1024 * 1024,
        validation_alias="CLAIMS_MAX_FILE_SIZE_BYTES",
    )
    claims_allowed_upload_extensions: list[str] = Field(
        default=[
            ".pdf",
            ".doc",
            ".docx",
            ".rtf",
            ".jpg",
            ".jpeg",
            ".png",
        ],
        validation_alias="CLAIMS_ALLOWED_UPLOAD_EXTENSIONS",
    )
    claims_allowed_upload_mime_types: list[str] = Field(
        default=[
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/rtf",
            "text/rtf",
            "image/jpeg",
            "image/png",
        ],
        validation_alias="CLAIMS_ALLOWED_UPLOAD_MIME_TYPES",
    )
    claims_admin_emails: list[str] = Field(
        default=[],
        validation_alias="CLAIMS_ADMIN_EMAILS",
    )
    invite_token_secret: str = Field(..., validation_alias="INVITE_TOKEN_SECRET")
    session_secret: str = Field(..., validation_alias="SESSION_SECRET")
    session_ttl_seconds: int = Field(default=1209600, validation_alias="SESSION_TTL_SECONDS")
    session_cookie_name: str = Field(default="session", validation_alias="SESSION_COOKIE_NAME")
    cookie_secure: bool = Field(default=False, validation_alias="COOKIE_SECURE")
    cookie_samesite: str = Field(default="lax", validation_alias="COOKIE_SAMESITE")
    email_from: str = Field(..., validation_alias="EMAIL_FROM")
    smtp_host: str = Field("", validation_alias="SMTP_HOST")
    smtp_port: int = Field(587, validation_alias="SMTP_PORT")
    smtp_user: str = Field("", validation_alias="SMTP_USER")
    smtp_password: str = Field("", validation_alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(True, validation_alias="SMTP_USE_TLS")
    app_base_url: str = Field("http://localhost:8000", validation_alias="APP_BASE_URL")
    invite_ttl_seconds: int = Field(default=604800, validation_alias="INVITE_TTL_SECONDS")
    chat_context_limit: int = Field(default=20, validation_alias="CHAT_CONTEXT_LIMIT")
    gateway_timeout_seconds: int = Field(default=30, validation_alias="GATEWAY_TIMEOUT_SECONDS")
    max_message_chars: int = Field(default=4000, validation_alias="MAX_MESSAGE_CHARS")
    rate_limit_company_rpm: int = Field(default=60, validation_alias="RATE_LIMIT_COMPANY_RPM")
    rate_limit_user_rpm: int = Field(default=30, validation_alias="RATE_LIMIT_USER_RPM")
    rate_limit_ip_rpm: int = Field(default=120, validation_alias="RATE_LIMIT_IP_RPM")

    @model_validator(mode="after")
    def _no_openai_key_in_product_api(self) -> "Settings":
        if self.openai_api_key:
            raise ValueError("OPENAI_API_KEY must not be set in product_api")
        return self

    @field_validator("superadmin_email")
    @classmethod
    def _email_like(cls, value: str | None) -> str | None:
        if value and "@" not in value:
            raise ValueError("email must contain '@'")
        return value

    @field_validator("cookie_samesite")
    @classmethod
    def _validate_samesite(cls, value: str) -> str:
        value = value.lower()
        if value not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be one of: lax, strict, none")
        return value

    @field_validator("claims_price_rub")
    @classmethod
    def _validate_claims_price(cls, value: int) -> int:
        if value < 0:
            raise ValueError("CLAIMS_PRICE_RUB must be >= 0")
        return value

    @field_validator("claims_upload_dir")
    @classmethod
    def _validate_claims_upload_dir(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("CLAIMS_UPLOAD_DIR must not be empty")
        return normalized

    @field_validator("claims_max_file_size_bytes")
    @classmethod
    def _validate_claims_max_file_size_bytes(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("CLAIMS_MAX_FILE_SIZE_BYTES must be > 0")
        return value

    @field_validator("claims_allowed_upload_extensions", mode="before")
    @classmethod
    def _parse_claims_allowed_upload_extensions(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            parts = [item.strip().lower() for item in value.split(",")]
            return [item for item in parts if item]
        return value

    @field_validator("claims_allowed_upload_extensions")
    @classmethod
    def _validate_claims_allowed_upload_extensions(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("CLAIMS_ALLOWED_UPLOAD_EXTENSIONS must contain strings only")
            candidate = item.strip().lower()
            if not candidate:
                continue
            if not candidate.startswith("."):
                candidate = f".{candidate}"
            if not candidate[1:].isalnum():
                raise ValueError(
                    "CLAIMS_ALLOWED_UPLOAD_EXTENSIONS must contain alphanumeric extensions only"
                )
            if candidate not in normalized:
                normalized.append(candidate)
        if not normalized:
            raise ValueError("CLAIMS_ALLOWED_UPLOAD_EXTENSIONS must not be empty")
        return normalized

    @field_validator("claims_allowed_upload_mime_types", mode="before")
    @classmethod
    def _parse_claims_allowed_upload_mime_types(
        cls, value: str | list[str]
    ) -> list[str]:
        if isinstance(value, str):
            parts = [item.strip().lower() for item in value.split(",")]
            return [item for item in parts if item]
        return value

    @field_validator("claims_allowed_upload_mime_types")
    @classmethod
    def _validate_claims_allowed_upload_mime_types(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("CLAIMS_ALLOWED_UPLOAD_MIME_TYPES must contain strings only")
            candidate = item.strip().lower()
            if not candidate:
                continue
            normalized.append(candidate)
        if not normalized:
            raise ValueError("CLAIMS_ALLOWED_UPLOAD_MIME_TYPES must not be empty")
        return normalized

    @field_validator("claims_admin_emails", mode="before")
    @classmethod
    def _parse_claims_admin_emails(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            parts = [item.strip().lower() for item in value.split(",")]
            return [item for item in parts if item]
        return value

    @field_validator("claims_admin_emails")
    @classmethod
    def _validate_claims_admin_emails(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("CLAIMS_ADMIN_EMAILS must contain strings only")
            candidate = item.strip().lower()
            if not candidate:
                continue
            if "@" not in candidate:
                raise ValueError("CLAIMS_ADMIN_EMAILS must contain valid emails")
            if candidate not in normalized:
                normalized.append(candidate)
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
