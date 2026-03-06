from enum import StrEnum

from pydantic import BaseModel


class Platform(StrEnum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"


class IncomingMessage(BaseModel):
    platform: Platform
    user_id: str  # "5491234567890" or "tg_12345678"
    message_id: str
    timestamp: str
    text: str
    type: str  # "text" | "audio" | "image"
    media_id: str | None = None
    reply_to_message_id: str | None = None
