from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
            if structured_fields_present:
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
        return self


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    usage: dict | None = None
    raw: dict | None = None
    model_profile: str | None = None
    resolved_model: str | None = None


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
