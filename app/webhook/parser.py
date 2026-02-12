from app.models import WhatsAppMessage


def extract_messages(payload: dict) -> list[WhatsAppMessage]:
    """Extract text messages from a WhatsApp webhook payload."""
    messages: list[WhatsAppMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue
                messages.append(
                    WhatsAppMessage(
                        from_number=msg["from"],
                        message_id=msg["id"],
                        timestamp=msg["timestamp"],
                        text=msg["text"]["body"],
                        type=msg["type"],
                    )
                )
    return messages
