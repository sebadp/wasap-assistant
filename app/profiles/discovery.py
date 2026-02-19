from __future__ import annotations

import json
import logging

from app.models import ChatMessage

logger = logging.getLogger(__name__)

_DISCOVERY_SYSTEM = (
    "You are an information extractor. "
    "Read the conversation and extract factual information about the user. "
    "Return a JSON object with any of these fields you can confidently extract "
    "(omit fields you're unsure about): "
    "tech_context, interests, schedule, family, location, preferences, language. "
    "Values should be short strings. Return only the JSON object, nothing else."
)


async def maybe_discover_profile_updates(
    phone_number: str,
    message_count: int,
    interval: int,
    repository,
    ollama_client,
    settings,
) -> None:
    """Run profile discovery if message_count is a multiple of interval.

    Best-effort: errors are logged but never propagated.
    """
    if interval <= 0 or message_count % interval != 0:
        return

    try:
        await _run_discovery(phone_number, repository, ollama_client, settings)
    except Exception:
        logger.warning("Profile discovery failed for %s", phone_number, exc_info=True)


async def _run_discovery(phone_number: str, repository, ollama_client, settings) -> None:
    """Fetch recent messages, run LLM extraction, merge into profile."""
    # Get current profile
    profile_row = await repository.get_user_profile(phone_number)
    if profile_row["onboarding_state"] != "complete":
        # Don't run discovery during onboarding
        return

    current_data = profile_row["data"]

    # Fetch last 15 messages for this conversation
    conv_id = await repository.get_or_create_conversation(phone_number)
    messages = await repository.get_recent_messages(conv_id, 15)
    if not messages:
        return

    # Format conversation for LLM
    conversation_text = "\n".join(
        f"{m.role.capitalize()}: {m.content[:300]}"
        for m in messages
        if m.role in ("user", "assistant")
    )

    prompt = (
        f"Conversation:\n{conversation_text}\n\n"
        "Extract factual user profile information from this conversation. "
        "Return only a JSON object with new or updated fields. "
        "Do not repeat fields already known:\n"
        f"Already known: {json.dumps(current_data, ensure_ascii=False)}"
    )

    llm_messages = [
        ChatMessage(role="system", content=_DISCOVERY_SYSTEM),
        ChatMessage(role="user", content=prompt),
    ]

    response = await ollama_client.chat_with_tools(llm_messages, think=False)
    raw = response.content.strip()

    # Try to parse JSON
    new_fields = _parse_json_safe(raw)
    if not new_fields:
        logger.debug("Discovery for %s: no new fields extracted", phone_number)
        return

    # Merge: only add fields not already present
    updated_data = dict(current_data)
    added = []
    for key, value in new_fields.items():
        if key not in updated_data and isinstance(value, str) and value.strip():
            updated_data[key] = value.strip()
            added.append(key)

    if not added:
        return

    logger.info("Profile discovery for %s: added fields %s", phone_number, added)
    await repository.save_user_profile(phone_number, "complete", updated_data)


def _parse_json_safe(text: str) -> dict:
    """Try to parse JSON from LLM output. Returns empty dict on failure."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return {}
