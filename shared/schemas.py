from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from shared.constants import (
    COMPANY_CARD_NARRATIVE_MAX_OUTPUT_TOKENS,
    COMPANY_CARD_NARRATIVE_MAX_TIMEOUT_SECONDS,
    COMPANY_CARD_NARRATIVE_MODEL_PROFILE,
    COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME,
)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str
    content: str


class ChatMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: int
    user_id: int
    conversation_id: int
    message_id: int


class JsonSchemaDefinition(BaseModel):
    """The strict response-format shape accepted by the structured gateway mode."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    strict: Literal[True]
    schema_: dict[str, Any] = Field(alias="schema")


class JsonSchemaResponseFormat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["json_schema"]
    json_schema: JsonSchemaDefinition


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage]
    model: str | None = None
    stream: bool = False
    timeout: int | None = None
    metadata: ChatMetadata | None = None
    model_profile: str | None = None
    response_format: JsonSchemaResponseFormat | None = None
    max_output_tokens: int | None = None
    gateway_dispatch_id: UUID | None = None

    @model_validator(mode="before")
    @classmethod
    def _strict_narrative_wire_integers(cls, value: object) -> object:
        """Do not let Pydantic coerce narrative wire limits.

        Legacy and scoring-explanation requests intentionally retain their
        existing coercion behaviour.  The task-specific narrative contract is
        the only mode whose signed JSON requires exact integer leaves.
        """

        if (
            isinstance(value, dict)
            and value.get("model_profile") == COMPANY_CARD_NARRATIVE_MODEL_PROFILE
        ):
            for field_name in ("timeout", "max_output_tokens"):
                if type(value.get(field_name)) is not int:
                    raise ValueError(
                        f"narrative {field_name} must be an exact integer"
                    )
        return value

    @field_validator("gateway_dispatch_id", mode="before")
    @classmethod
    def _canonical_narrative_dispatch_id(cls, value: object) -> object:
        if value is None:
            return value
        if isinstance(value, UUID):
            return value
        if not isinstance(value, str):
            raise ValueError("gateway_dispatch_id must be a canonical UUID")
        try:
            parsed = UUID(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("gateway_dispatch_id must be a canonical UUID") from exc
        if str(parsed) != value:
            raise ValueError("gateway_dispatch_id must be a canonical UUID")
        return parsed

    @model_validator(mode="after")
    def _validate_mode(self) -> "ChatRequest":
        if not self.messages:
            raise ValueError("messages must not be empty")

        is_legacy = self.model is not None
        structured_fields_present = any(
            value is not None
            for value in (
                self.model_profile,
                self.response_format,
                self.max_output_tokens,
            )
        )
        if is_legacy:
            if not self.model.strip():
                raise ValueError("legacy model must not be empty")
            if self.metadata is None:
                raise ValueError("legacy metadata is required")
            if structured_fields_present or self.gateway_dispatch_id is not None:
                raise ValueError("legacy requests cannot include structured fields")
            return self

        if self.metadata is not None:
            raise ValueError("structured requests must not include metadata")
        if not self.model_profile or not self.model_profile.strip():
            raise ValueError("structured model_profile is required")
        if self.response_format is None:
            raise ValueError("structured response_format is required")
        if self.max_output_tokens is None or self.max_output_tokens <= 0:
            raise ValueError("structured max_output_tokens must be positive")
        if self.stream:
            raise ValueError("structured requests cannot stream")
        if self.model_profile == COMPANY_CARD_NARRATIVE_MODEL_PROFILE:
            if self.gateway_dispatch_id is None:
                raise ValueError("narrative structured requests require dispatch id")
            if self.response_format.json_schema.name != COMPANY_CARD_NARRATIVE_OUTPUT_SCHEMA_NAME:
                raise ValueError("narrative structured requests require the narrative schema")
            if self.timeout is None or not 1 <= self.timeout <= COMPANY_CARD_NARRATIVE_MAX_TIMEOUT_SECONDS:
                raise ValueError("narrative timeout is out of bounds")
            if not 1 <= self.max_output_tokens <= COMPANY_CARD_NARRATIVE_MAX_OUTPUT_TOKENS:
                raise ValueError("narrative max_output_tokens is out of bounds")
        if self.gateway_dispatch_id is not None and self.model_profile != COMPANY_CARD_NARRATIVE_MODEL_PROFILE:
            raise ValueError("dispatch id is reserved for narrative structured requests")
        return self


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    usage: dict | None = None
    raw: dict | None = None
    model_profile: str | None = None
    resolved_model: str | None = None
    gateway_dispatch_id: UUID | None = None

    @field_validator("gateway_dispatch_id", mode="before")
    @classmethod
    def _canonical_narrative_dispatch_echo(cls, value: object) -> object:
        if value is None or isinstance(value, UUID):
            return value
        if not isinstance(value, str):
            raise ValueError("gateway_dispatch_id must be a canonical UUID")
        try:
            parsed = UUID(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("gateway_dispatch_id must be a canonical UUID") from exc
        if str(parsed) != value:
            raise ValueError("gateway_dispatch_id must be a canonical UUID")
        return parsed


class ChatStreamDelta(BaseModel):
    text: str


class ChatStreamFinal(BaseModel):
    text: str
    usage: dict | None = None


class ChatStreamError(BaseModel):
    code: str
    message: str
    retryable: bool
    type: str | None = None
