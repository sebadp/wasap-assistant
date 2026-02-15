from __future__ import annotations

from app.database.repository import Repository
from app.models import ChatMessage


class ConversationManager:
    def __init__(self, repository: Repository, max_messages: int = 20):
        self._repo = repository
        self._max_messages = max_messages

    async def is_duplicate(self, wa_message_id: str) -> bool:
        return await self._repo.is_duplicate(wa_message_id)

    async def add_message(
        self,
        phone_number: str,
        role: str,
        content: str,
        wa_message_id: str | None = None,
    ) -> None:
        conv_id = await self._repo.get_or_create_conversation(phone_number)
        await self._repo.save_message(conv_id, role, content, wa_message_id)

    async def get_history(self, phone_number: str) -> list[ChatMessage]:
        conv_id = await self._repo.get_or_create_conversation(phone_number)
        return await self._repo.get_recent_messages(conv_id, self._max_messages)

    async def get_context(
        self,
        phone_number: str,
        system_prompt: str,
        memories: list[str],
        skills_summary: str | None = None,
    ) -> list[ChatMessage]:
        conv_id = await self._repo.get_or_create_conversation(phone_number)
        summary = await self._repo.get_latest_summary(conv_id)
        history = await self._repo.get_recent_messages(conv_id, self._max_messages)

        context = [ChatMessage(role="system", content=system_prompt)]
        if memories:
            memory_block = "Important user information:\n" + "\n".join(f"- {m}" for m in memories)
            context.append(ChatMessage(role="system", content=memory_block))
        if skills_summary:
            context.append(ChatMessage(role="system", content=skills_summary))
        if summary:
            context.append(ChatMessage(role="system", content=f"Previous conversation summary:\n{summary}"))
        context.extend(history)
        return context

    async def clear(self, phone_number: str) -> None:
        conv_id = await self._repo.get_or_create_conversation(phone_number)
        await self._repo.clear_conversation(conv_id)

    async def get_conversation_id(self, phone_number: str) -> int:
        return await self._repo.get_or_create_conversation(phone_number)
