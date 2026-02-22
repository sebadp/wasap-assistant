"""Agentic session loop: autonomous background execution."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

from app.agent.models import AgentSession, AgentStatus
from app.models import ChatMessage
from app.skills.executor import execute_tool_loop

if TYPE_CHECKING:
    from app.llm.client import OllamaClient
    from app.mcp.manager import McpManager
    from app.skills.registry import SkillRegistry
    from app.whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)

# Active sessions indexed by phone number - one concurrent session per user
_active_sessions: dict[str, AgentSession] = {}
# asyncio Tasks for each active session, so we can actually cancel them
_active_tasks: dict[str, asyncio.Task] = {}

_AGENT_SYSTEM_PROMPT = """\
You are in AGENT MODE. You have been given an objective by the user and must complete \
it autonomously using the available tools.

OBJECTIVE: {objective}

RULES:
1. Break the objective into small, concrete steps using create_task_plan first.
2. Execute one step at a time using tools.
3. After completing each step, call update_task_status to mark it done.
4. If you need user input before a critical action, call request_user_approval.
5. Never loop on the same action — if a tool fails, try a different approach or skip.
6. When ALL steps are done, write a concise summary of what was accomplished.
"""

_PLAN_REMINDER = """
--- CURRENT TASK PLAN ---
{task_plan}
--- END TASK PLAN ---
"""


def _register_session_tools(
    session: AgentSession,
    skill_registry: SkillRegistry,
    wa_client: WhatsAppClient,
) -> SkillRegistry:
    """Create a session-scoped copy of the registry and register HITL + task-memory tools.

    Returns a new SkillRegistry derived from skill_registry so that concurrent
    agent sessions do not overwrite each other's handler closures.
    """
    from app.agent.hitl import request_user_approval as _hitl_request
    from app.agent.task_memory import register_task_memory_tools
    from app.skills.registry import SkillRegistry as _Reg

    # Shallow copy: inherits all existing tools, skills metadata, and adds session-specific ones on top
    session_registry = _Reg(skills_dir=skill_registry._skills_dir)  # type: ignore[attr-defined]
    session_registry._tools = dict(skill_registry._tools)  # type: ignore[attr-defined]  # copy tool map
    session_registry._skills = dict(skill_registry._skills)  # type: ignore[attr-defined]  # copy skill metadata for get_skill_instructions()
    session_registry._loaded_instructions = set(skill_registry._loaded_instructions)  # type: ignore[attr-defined]

    # Register the three task-memory tools
    register_task_memory_tools(session_registry, lambda: session)

    # Register the HITL approval tool
    async def request_user_approval(question: str) -> str:
        """Pause the agent session and send a question to the user via WhatsApp.

        The session will resume as soon as the user replies.
        Use this before irreversible actions (commits, pushes, file overwrites).
        """
        session.status = AgentStatus.WAITING_USER
        try:
            result = await _hitl_request(
                phone_number=session.phone_number,
                question=question,
                wa_client=wa_client,
            )
        finally:
            session.status = AgentStatus.RUNNING
        return result

    session_registry.register_tool(
        name="request_user_approval",
        description=(
            "Pause the agent session and ask the user a question via WhatsApp. "
            "The session resumes when the user replies. "
            "Use this before irreversible actions like commits or file deletions."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user. Be specific about what you need approval for.",
                },
            },
            "required": ["question"],
        },
        handler=request_user_approval,
        skill_name="agent",
    )

    return session_registry


async def run_agent_session(
    session: AgentSession,
    ollama_client: OllamaClient,
    skill_registry: SkillRegistry,
    wa_client: WhatsAppClient,
    mcp_manager: McpManager | None = None,
) -> None:
    """Run a full agentic session in the background.

    The agent iterates: Think → Call Tools → Observe → Loop
    until the objective is complete or max_iterations is reached.
    Proactively sends the result to the user via WhatsApp when done.
    """
    _active_sessions[session.phone_number] = session
    current_task = asyncio.current_task()
    if current_task is not None:
        _active_tasks[session.phone_number] = current_task
    logger.info(
        "Agent session %s started for %s: %s",
        session.session_id,
        session.phone_number,
        session.objective[:80],
    )

    try:
        system_content = _AGENT_SYSTEM_PROMPT.format(objective=session.objective)

        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_content),
            ChatMessage(role="user", content=session.objective),
        ]

        # Build a session-scoped registry with HITL + task-memory tools.
        # This prevents concurrent sessions from overwriting each other's closures.
        session_registry = _register_session_tools(session, skill_registry, wa_client)

        # Run the tool loop with elevated max_tools to allow multi-step autonomy
        reply = await execute_tool_loop(
            messages=messages,
            ollama_client=ollama_client,
            skill_registry=session_registry,
            mcp_manager=mcp_manager,
            max_tools=session.max_iterations,
        )

        session.status = AgentStatus.COMPLETED
        logger.info("Agent session %s completed", session.session_id)

        # Send final result to the user via WhatsApp
        from app.formatting.markdown_to_wa import markdown_to_whatsapp

        await wa_client.send_message(
            session.phone_number,
            markdown_to_whatsapp(f"✅ *Sesión agéntica completada*\n\n{reply}"),
        )

    except asyncio.CancelledError:
        session.status = AgentStatus.CANCELLED
        logger.info("Agent session %s cancelled", session.session_id)
        await wa_client.send_message(
            session.phone_number,
            "🛑 Sesión agéntica cancelada.",
        )
    except Exception:
        session.status = AgentStatus.FAILED
        logger.exception("Agent session %s failed", session.session_id)
        await wa_client.send_message(
            session.phone_number,
            "❌ La sesión agéntica falló inesperadamente. Usa /debug para investigar.",
        )
    finally:
        _active_sessions.pop(session.phone_number, None)
        _active_tasks.pop(session.phone_number, None)


def get_active_session(phone_number: str) -> AgentSession | None:
    """Return the active agent session for this user, or None."""
    return _active_sessions.get(phone_number)


def cancel_session(phone_number: str) -> bool:
    """Cancel the active agent session for this phone number.

    Cancels the underlying asyncio.Task so the loop actually stops,
    not just setting a status flag. Also handles WAITING_USER state.
    Returns True if a session was found and cancel was requested.
    """
    session = _active_sessions.get(phone_number)
    cancellable = {AgentStatus.RUNNING, AgentStatus.WAITING_USER}
    if session and session.status in cancellable:
        session.status = AgentStatus.CANCELLED
        task = _active_tasks.get(phone_number)
        if task and not task.done():
            task.cancel()
        return True
    return False


def create_session(
    phone_number: str,
    objective: str,
    max_iterations: int = 15,
) -> AgentSession:
    """Create a new AgentSession with a fresh random session ID."""
    return AgentSession(
        session_id=uuid.uuid4().hex,
        phone_number=phone_number,
        objective=objective,
        max_iterations=max_iterations,
    )
