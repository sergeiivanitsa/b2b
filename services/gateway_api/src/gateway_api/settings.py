from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.constants import AI_EXPLANATION_MODEL_PROFILE, MODEL_GPT_5_2


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
    ai_explanation_model_profile: str = Field(
        default=AI_EXPLANATION_MODEL_PROFILE,
        validation_alias="AI_EXPLANATION_MODEL_PROFILE",
    )
    ai_explanation_model: str = Field(
        default=MODEL_GPT_5_2,
        validation_alias="AI_EXPLANATION_MODEL",
    )

    @field_validator("gateway_shared_secret")
    @classmethod
    def _shared_secret_not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("GATEWAY_SHARED_SECRET must not be empty")
        return value

    @field_validator("ai_explanation_model_profile")
    @classmethod
    def _validate_ai_explanation_profile(cls, value: str) -> str:
        normalized = value.strip()
        if normalized != AI_EXPLANATION_MODEL_PROFILE:
            raise ValueError("AI_EXPLANATION_MODEL_PROFILE is not supported")
        return normalized

    @field_validator("ai_explanation_model")
    @classmethod
    def _validate_ai_explanation_model(cls, value: str) -> str:
        normalized = value.strip()
        if normalized != MODEL_GPT_5_2:
            raise ValueError("AI_EXPLANATION_MODEL is not supported")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
