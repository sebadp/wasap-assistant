import logging
from contextvars import ContextVar
from typing import TYPE_CHECKING

from app.skills.registry import SkillRegistry

if TYPE_CHECKING:
    from app.database.repository import Repository

logger = logging.getLogger(__name__)

_current_user_phone: ContextVar[str | None] = ContextVar("_current_user_phone", default=None)


def set_current_user(phone_number: str) -> None:
    _current_user_phone.set(phone_number)


def register(registry: SkillRegistry, repository: "Repository") -> None:
    async def get_recent_messages(limit: int = 10, offset: int = 0) -> str:
        # Clamp parameters to prevent unbounded queries
        limit = max(1, min(limit, 50))
        offset = max(0, offset)

        phone = _current_user_phone.get()
        if not phone:
            return "No user context available."

        # Use a read-only lookup to avoid write side effects
        conv_id = await repository.get_conversation_id(phone)
        if not conv_id:
            return "The conversation history is empty."

        # Get one extra message to see if there are more
        rows = await repository.get_messages_paginated(conv_id, limit + 1, offset)

        if not rows:
            if offset == 0:
                return "The conversation history is empty."
            return f"No messages found at offset {offset}."

        has_more = len(rows) > limit
        messages = rows[:limit]

        lines = []
        # Reverse to show chronological order within this page
        for role, content, created_at in reversed(messages):
            # Try to trim just the time part for compactness if it's a full ISO format
            ts = created_at[:16] if created_at else "unknown"
            # Format content to not break output excessively
            content_preview = content.replace("\n", " ")
            if len(content_preview) > 500:
                content_preview = content_preview[:500] + "... (truncated)"

            lines.append(f"[{ts}] {role.upper()}: {content_preview}")

        result = "\n".join(lines)
        if has_more:
            result += f"\n\n(There are older messages. Use offset={offset + limit} to see more.)"

        return result

    registry.register_tool(
        name="get_recent_messages",
        description="Get recent messages from the conversation history, supporting pagination. Use this to review past context.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of messages to retrieve (default: 10, max: 50)",
                    "default": 10,
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of messages to skip to go further back in time (default: 0 = most recent)",
                    "default": 0,
                },
            },
        },
        handler=get_recent_messages,
        skill_name="conversation",
    )
