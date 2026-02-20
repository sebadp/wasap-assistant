"""In-memory cache for active prompt versions.

Allows prompt versioning without changing the system prompt on every request.
The cache is invalidated when a new version is activated via /approve-prompt.

Usage:
    base_prompt = await get_active_prompt("system_prompt", repository, settings.system_prompt)
    invalidate_prompt_cache("system_prompt")  # after activating a new version
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# module-level cache: prompt_name → active content
_active_prompts: dict[str, str] = {}


async def get_active_prompt(
    prompt_name: str,
    repository: object,
    default: str,
) -> str:
    """Return the active prompt content, with in-memory cache.

    Falls back to `default` (from config.py) if no active version exists in DB.
    """
    if prompt_name not in _active_prompts:
        try:
            row = await repository.get_active_prompt_version(prompt_name)  # type: ignore[attr-defined]
            _active_prompts[prompt_name] = row["content"] if row else default
        except Exception:
            logger.exception("Failed to load active prompt %s from DB, using default", prompt_name)
            _active_prompts[prompt_name] = default
    return _active_prompts[prompt_name]


def invalidate_prompt_cache(prompt_name: str | None = None) -> None:
    """Invalidate the cache for a specific prompt, or all prompts."""
    if prompt_name:
        _active_prompts.pop(prompt_name, None)
        logger.debug("Prompt cache invalidated: %s", prompt_name)
    else:
        _active_prompts.clear()
        logger.debug("All prompt caches invalidated")
