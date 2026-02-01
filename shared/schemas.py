from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatMetadata(BaseModel):
    company_id: int
    user_id: int
    conversation_id: int
    message_id: int


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str
    stream: bool = False
    timeout: int | None = None
    metadata: ChatMetadata


class ChatResponse(BaseModel):
    text: str
    usage: dict | None = None
    raw: dict | None = None


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
