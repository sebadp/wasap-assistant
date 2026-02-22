"""Context compaction and management utilities."""

import logging

from app.llm.client import OllamaClient
from app.models import ChatMessage

logger = logging.getLogger(__name__)


async def compact_tool_output(
    tool_name: str,
    text: str,
    user_request: str,
    ollama_client: OllamaClient,
    max_length: int = 4000,
) -> str:
    """Implement intelligent summarization for tool outputs that exceed max_length.

    If the text is too large, an auxiliary LLM prompt is sent to summarize the data
    based on what the user originally asked, preserving context window size and
    preventing context rot or hallucinations.
    """
    if len(text) <= max_length:
        return text

    logger.warning(
        "Tool '%s' returned %d characters (limit %d). Initiating intelligent compaction.",
        tool_name,
        len(text),
        max_length,
    )

    prompt = (
        f"The tool '{tool_name}' just returned a massive payload of {len(text)} characters.\n"
        f'The user\'s original request was: "{user_request}"\n\n'
        "Your task: Summarize this payload concisely, extracting ONLY the most relevant "
        "fields or items that answer the user's request. Discard irrelevant metadata, "
        "huge text blocks, or deeply nested JSON unless it specifically answers what the "
        "user is looking for.\n\n"
        "At the end of your summary, add a brief note indicating that this is a "
        "summary and more detailed data is available if they ask for it.\n\n"
        f"--- RAW PAYLOAD START ---\n{text[:15000]}\n--- RAW PAYLOAD END (truncated if massive) ---"
    )

    try:
        messages = [
            ChatMessage(
                role="system",
                content="You are an internal context-compactor agent. Return a clean, concise summary of the data.",
            ),
            ChatMessage(role="user", content=prompt),
        ]

        # Use the default model; compaction doesn't need special model settings
        summary = await ollama_client.chat(messages, model=None)

        if not summary or summary.isspace():
            raise ValueError("Empty summary from LLM")

        logger.info("Successfully compacted tool output to %d chars.", len(summary))
        return summary
    except Exception as e:
        logger.error("Failed to compact tool output with LLM: %s", e, exc_info=True)
        # Safe fallback: structural hard cut
        return text[:max_length] + "\n...[Output truncated due to length/compaction failure]"
