from app.models import WhatsAppMessage, WhatsAppReaction

_SUPPORTED_TYPES = {"text", "audio", "image"}


def extract_messages(payload: dict) -> list[WhatsAppMessage]:
    """Extract text, audio, and image messages from a WhatsApp webhook payload."""
    messages: list[WhatsAppMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                msg_type = msg.get("type")
                if msg_type not in _SUPPORTED_TYPES:
                    continue

                text = ""
                media_id = None

                if msg_type == "text":
                    text = msg["text"]["body"]
                elif msg_type == "audio":
                    media_id = msg["audio"]["id"]
                elif msg_type == "image":
                    media_id = msg["image"]["id"]
                    caption = msg["image"].get("caption")
                    if caption:
                        text = caption

                reply_to = msg.get("context", {}).get("id")

                messages.append(
                    WhatsAppMessage(
                        from_number=msg["from"],
                        message_id=msg["id"],
                        timestamp=msg["timestamp"],
                        text=text,
                        type=msg_type,
                        media_id=media_id,
                        reply_to_message_id=reply_to,
                    )
                )
    return messages


def extract_reactions(payload: dict) -> list[WhatsAppReaction]:
    """Extract reactions from a WhatsApp webhook payload.

    Reactions are NOT added to _SUPPORTED_TYPES — they bypass the normal
    message pipeline (dedup, rate limit, _handle_message) entirely.
    """
    reactions: list[WhatsAppReaction] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                if msg.get("type") != "reaction":
                    continue
                reaction = msg.get("reaction", {})
                reacted_id = reaction.get("message_id")
                emoji = reaction.get("emoji")
                if not reacted_id or not emoji:
                    continue
                reactions.append(WhatsAppReaction(
                    from_number=msg["from"],
                    reacted_message_id=reacted_id,
                    emoji=emoji,
                ))
    return reactions
