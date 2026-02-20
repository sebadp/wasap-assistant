from __future__ import annotations

import logging

from app.models import ChatMessage

logger = logging.getLogger(__name__)

# State order: pending → step_1 → step_2 → step_3 → naming → complete
STATES = ["pending", "step_1", "step_2", "step_3", "naming", "complete"]

# System prompt used for onboarding LLM calls
_ONBOARDING_SYSTEM = (
    "You are a warm, friendly personal assistant on WhatsApp. "
    "Be concise and conversational — this is a chat, not a form. "
    "Answer in the same language the user writes in."
)


async def handle_onboarding_message(
    user_reply: str,
    state: str,
    profile_data: dict,
    ollama_client,
) -> tuple[str, str, dict]:
    """Handle one onboarding step.

    Returns (next_state, response_text, updated_profile_data).
    """
    data = dict(profile_data)

    if state == "pending":
        # First contact — respond to the user's message and ask their name
        response = await _generate_intro(user_reply, ollama_client)
        return "step_1", response, data

    if state == "step_1":
        # Extract name from reply, then ask occupation
        name = await _extract_field("name", user_reply, ollama_client)
        if name:
            data["name"] = name
        response = await _ask_occupation(data, ollama_client)
        return "step_2", response, data

    if state == "step_2":
        # Extract occupation, then ask about use cases / goals
        occupation = await _extract_field("occupation or job role", user_reply, ollama_client)
        if occupation:
            data["occupation"] = occupation
        response = await _ask_use_cases(data, ollama_client)
        return "step_3", response, data

    if state == "step_3":
        # Extract use cases, then propose 2 assistant name options
        use_cases = await _extract_field("main use cases or goals", user_reply, ollama_client)
        if use_cases:
            data["use_cases"] = use_cases
        response = await _propose_names(data, ollama_client)
        return "naming", response, data

    if state == "naming":
        # Extract confirmed name from user reply
        assistant_name = await _extract_field(
            "assistant name chosen by the user",
            user_reply,
            ollama_client,
        )
        if not assistant_name:
            assistant_name = "Wasi"
        data["assistant_name"] = assistant_name
        response = await _generate_welcome(data, ollama_client)
        return "complete", response, data

    # Should not happen — if state is already complete, this won't be called
    logger.warning("handle_onboarding_message called with unexpected state: %s", state)
    return state, "", data


async def _generate_intro(user_first_message: str, ollama_client) -> str:
    """Generate a warm intro that responds to the first message and asks for the user's name."""
    prompt = (
        "The user just sent their first message to you on WhatsApp. "
        "Reply warmly: briefly acknowledge or respond to what they said, "
        "then introduce yourself as their new personal assistant and ask how they'd like you to address them (their name). "
        "Keep it short and friendly — 2-4 sentences.\n\n"
        f"User's first message: {user_first_message}"
    )
    messages = [
        ChatMessage(role="system", content=_ONBOARDING_SYSTEM),
        ChatMessage(role="user", content=prompt),
    ]
    response = await ollama_client.chat_with_tools(messages, think=False)
    return response.content.strip()


async def _ask_occupation(data: dict, ollama_client) -> str:
    """Ask the user about their occupation."""
    name = data.get("name", "")
    prompt = (
        f"You are onboarding a user{' named ' + name if name else ''}. "
        "Ask them briefly and conversationally what they do for work or study "
        "(their occupation or field). One short sentence."
    )
    messages = [
        ChatMessage(role="system", content=_ONBOARDING_SYSTEM),
        ChatMessage(role="user", content=prompt),
    ]
    response = await ollama_client.chat_with_tools(messages, think=False)
    return response.content.strip()


async def _ask_use_cases(data: dict, ollama_client) -> str:
    """Ask the user about their main use cases / goals."""
    name = data.get("name", "")
    occupation = data.get("occupation", "")
    context = ""
    if name:
        context += f"named {name} "
    if occupation:
        context += f"who works as {occupation} "
    prompt = (
        f"You are onboarding a user {context.strip()}. "
        "Ask them conversationally what they mainly want to use you for — "
        "what kinds of tasks, questions, or goals they have in mind. One short sentence."
    )
    messages = [
        ChatMessage(role="system", content=_ONBOARDING_SYSTEM),
        ChatMessage(role="user", content=prompt),
    ]
    response = await ollama_client.chat_with_tools(messages, think=False)
    return response.content.strip()


async def _propose_names(data: dict, ollama_client) -> str:
    """Propose 2 assistant name options and ask the user to pick or suggest their own."""
    name = data.get("name", "")
    occupation = data.get("occupation", "")
    use_cases = data.get("use_cases", "")
    profile_summary = (
        f"User name: {name or 'unknown'}\n"
        f"Occupation: {occupation or 'unknown'}\n"
        f"Main use cases: {use_cases or 'unknown'}"
    )
    prompt = (
        "Based on this user profile, propose exactly 2 short, friendly assistant names "
        "(like Aria, Max, Nova, Sam, Wasi, etc.) that feel personal and fitting. "
        "Then ask the user to pick one or suggest their own name. "
        "Format: propose the names naturally in a short message, not as a numbered list.\n\n"
        f"Profile:\n{profile_summary}"
    )
    messages = [
        ChatMessage(role="system", content=_ONBOARDING_SYSTEM),
        ChatMessage(role="user", content=prompt),
    ]
    response = await ollama_client.chat_with_tools(messages, think=False)
    return response.content.strip()


async def _generate_welcome(data: dict, ollama_client) -> str:
    """Generate a personalized welcome message once onboarding is complete."""
    name = data.get("name", "")
    assistant_name = data.get("assistant_name", "Wasi")
    use_cases = data.get("use_cases", "")
    prompt = (
        f"You are {assistant_name}, a personal WhatsApp assistant. "
        f"The user has just finished setup. "
        f"{'Their name is ' + name + '. ' if name else ''}"
        f"{'They want to use you for: ' + use_cases + '. ' if use_cases else ''}"
        "Write a short, warm welcome message (2-3 sentences) confirming you're ready to help. "
        "Mention your name."
    )
    messages = [
        ChatMessage(role="system", content=_ONBOARDING_SYSTEM),
        ChatMessage(role="user", content=prompt),
    ]
    response = await ollama_client.chat_with_tools(messages, think=False)
    return response.content.strip()


async def _extract_field(field_description: str, user_reply: str, ollama_client) -> str:
    """Extract a specific field value from a user's reply. Returns plain text."""
    prompt = (
        f"Extract the {field_description} from the user's message. "
        "Return only the extracted value as plain text — no explanation, no punctuation, "
        "no extra words. If you can't extract it clearly, return an empty string.\n\n"
        f"User message: {user_reply}"
    )
    messages = [
        ChatMessage(
            role="system",
            content="You are a precise information extractor. Output only the requested value.",
        ),
        ChatMessage(role="user", content=prompt),
    ]
    response = await ollama_client.chat_with_tools(messages, think=False)
    return response.content.strip()
