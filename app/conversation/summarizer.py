from __future__ import annotations

import logging

from app.database.repository import Repository
from app.llm.client import OllamaClient
from app.models import ChatMessage

logger = logging.getLogger(__name__)

SUMMARIZE_PROMPT = (
    "Summarize the following conversation in 2-3 short paragraphs, "
    "capturing the main topics, decisions, and important details. "
    "Write the summary in the same language the conversation is in."
)


async def maybe_summarize(
    conversation_id: int,
    repository: Repository,
    ollama_client: OllamaClient,
    threshold: int,
    max_messages: int,
) -> None:
    try:
        count = await repository.get_message_count(conversation_id)
        if count <= threshold:
            return

        previous_summary = await repository.get_latest_summary(conversation_id)
        all_messages = await repository.get_recent_messages(conversation_id, count)
        old_messages = all_messages[: len(all_messages) - max_messages]

        if not old_messages:
            return

        prompt_parts = [SUMMARIZE_PROMPT]
        if previous_summary:
            prompt_parts.append(f"\nPrevious summary:\n{previous_summary}")
        prompt_parts.append("\nConversation to summarize:")
        for msg in old_messages:
            prompt_parts.append(f"{msg.role}: {msg.content}")

        summary_prompt = "\n".join(prompt_parts)
        messages = [ChatMessage(role="user", content=summary_prompt)]
        summary = await ollama_client.chat(messages)

        await repository.save_summary(conversation_id, summary, count)
        await repository.delete_old_messages(conversation_id, max_messages)

        logger.info(
            "Summarized conversation %d: %d messages → kept %d",
            conversation_id,
            count,
            max_messages,
        )
    except Exception:
        logger.exception("Summarization failed for conversation %d", conversation_id)
