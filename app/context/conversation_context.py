"""ConversationContext: state object that flows through the message pipeline.

Replaces the ad-hoc variable passing in _handle_message. Every subsystem reads
from this object instead of receiving individual parameters.

Key design decisions:
- Built in one call via ConversationContext.build() that runs DB fetches in parallel
- Immutable after construction (scratchpad is the only mutable field)
- Carries routing state (sticky_categories) so the classifier can fall back intelligently
- Carries user_facts for tool loop injection without extra DB queries
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.context.fact_extractor import extract_facts

if TYPE_CHECKING:
    from app.conversation.manager import ConversationManager
    from app.database.repository import Repository
    from app.models import ChatMessage, Note

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """State snapshot for a single user message, built before the pipeline starts."""

    # Identity
    phone_number: str
    user_text: str
    conv_id: int

    # Pre-fetched data (built in parallel during .build())
    user_facts: dict[str, str] = field(default_factory=dict)
    """Structured key→value facts extracted from memories (e.g. github_username='sebadp')."""

    memories: list[str] = field(default_factory=list)
    """All active memory strings for this user."""

    history: list[ChatMessage] = field(default_factory=list)
    """Recent conversation messages (up to max_messages)."""

    summary: str | None = None
    """Latest conversation summary, if any."""

    daily_logs: str | None = None
    """Recent activity logs injected into context."""

    relevant_notes: list[Note] = field(default_factory=list)
    """Semantically relevant notes for this message."""

    # Routing state
    sticky_categories: list[str] = field(default_factory=list)
    """Categories from the last turn that used tools. Used as fallback for ambiguous follow-ups."""

    current_categories: list[str] = field(default_factory=list)
    """Resolved categories for this turn (set after classify_intent)."""

    # Tool loop state (written during execution, read at the end)
    scratchpad: str = ""
    """Structured notes the agent writes during the tool loop for cross-iteration coherence."""

    # Embeddings (optional)
    query_embedding: list[float] | None = None

    @classmethod
    async def build(
        cls,
        phone_number: str,
        user_text: str,
        repository: Repository,
        conversation_manager: ConversationManager,
    ) -> ConversationContext:
        """Build a ConversationContext by fetching all data in parallel.

        This replaces the scattered Phase A/B fetches in _handle_message with
        a single, predictable, testable async factory.
        """
        conv_id = await conversation_manager.get_conversation_id(phone_number)

        async def _none() -> None:
            return None

        async def _empty_list() -> list[str]:
            return []

        # Parallel fetches — all independent of each other
        memories_raw, history, summary, sticky = await asyncio.gather(
            repository.get_active_memories(),
            conversation_manager.get_history(phone_number),
            repository.get_latest_summary(conv_id) if conv_id else _none(),
            repository.get_sticky_categories(conv_id) if conv_id else _empty_list(),
        )

        user_facts = extract_facts(memories_raw)
        if user_facts:
            logger.debug(
                "ConversationContext: extracted %d user facts: %s",
                len(user_facts),
                list(user_facts.keys()),
            )

        return cls(
            phone_number=phone_number,
            user_text=user_text,
            conv_id=conv_id or 0,
            user_facts=user_facts,
            memories=memories_raw,
            history=history,
            summary=summary,
            sticky_categories=sticky or [],
        )
