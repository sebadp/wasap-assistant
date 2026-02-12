from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str  # "system", "user", or "assistant"
    content: str


class WhatsAppMessage(BaseModel):
    from_number: str
    message_id: str
    timestamp: str
    text: str
    type: str


class OllamaCheck(BaseModel):
    available: bool


class HealthResponse(BaseModel):
    status: str
    checks: OllamaCheck


class Memory(BaseModel):
    id: int
    content: str
    category: str | None = None
    active: bool = True
    created_at: str = ""
