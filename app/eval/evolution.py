"""Prompt evolution — propose and evaluate prompt modifications.

Implements a lightweight MIPRO-like loop:
1. Diagnose a recurring failure pattern
2. Propose a targeted prompt modification via LLM
3. Save as draft (is_active=0) for human review
4. Human approves via /approve-prompt → activate_prompt_version() + invalidate_prompt_cache()
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.llm.client import OllamaClient

from app.models import ChatMessage

logger = logging.getLogger(__name__)


async def propose_prompt_change(
    prompt_name: str,
    diagnosis: str,
    proposed_change: str,
    ollama_client: OllamaClient,
    repository: object,
) -> dict:
    """Generate a prompt modification proposal using the LLM.

    Does NOT activate it — saves as draft (is_active=0).

    Returns dict with keys: version, content, prompt_name.
    """
    current_row = await repository.get_active_prompt_version(prompt_name)  # type: ignore[attr-defined]
    current_content: str = current_row["content"] if current_row else ""
    current_version: int = current_row["version"] if current_row else 0

    if not current_content:
        return {
            "error": (
                f"No active prompt version found for '{prompt_name}'. "
                "Save one first with /approve-prompt."
            )
        }

    system_msg = ChatMessage(
        role="system",
        content=(
            "You are a prompt engineer. You modify system prompts to fix specific issues. "
            "Make minimal, targeted changes that address the diagnosed problem without "
            "breaking existing behavior. Output ONLY the complete modified prompt text, "
            "nothing else."
        ),
    )
    user_msg = ChatMessage(
        role="user",
        content=(
            f"Current prompt:\n{current_content}\n\n"
            f"Problem diagnosed: {diagnosis}\n"
            f"Proposed change: {proposed_change}\n\n"
            f"Generate the complete modified prompt."
        ),
    )

    try:
        new_content = await ollama_client.chat([system_msg, user_msg])
        if hasattr(new_content, "content"):
            new_content = new_content.content
        new_content = str(new_content).strip()
    except Exception:
        logger.exception("LLM failed to generate prompt proposal")
        raise

    new_version = current_version + 1
    await repository.save_prompt_version(  # type: ignore[attr-defined]
        prompt_name=prompt_name,
        version=new_version,
        content=new_content,
        created_by="agent",
    )
    logger.info(
        "Prompt proposal saved: %s v%d (diagnosis: %.80s)",
        prompt_name, new_version, diagnosis,
    )
    return {"version": new_version, "content": new_content, "prompt_name": prompt_name}
