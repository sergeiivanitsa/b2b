from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "dev"
    log_level: str = "INFO"
    gateway_shared_secret: str = Field(..., validation_alias="GATEWAY_SHARED_SECRET")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    gateway_clock_skew_seconds: int = Field(
        default=60, validation_alias="GATEWAY_CLOCK_SKEW_SECONDS"
    )
    gateway_nonce_ttl_seconds: int = Field(
        default=300, validation_alias="GATEWAY_NONCE_TTL_SECONDS"
    )
    openai_timeout_seconds: int = Field(default=30, validation_alias="OPENAI_TIMEOUT_SECONDS")

    @field_validator("gateway_shared_secret")
    @classmethod
    def _shared_secret_not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("GATEWAY_SHARED_SECRET must not be empty")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
