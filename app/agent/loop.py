"""Agentic session loop: autonomous background execution.

Phase 4 refactor: the agent now has its own outer loop (max_iterations rounds)
separate from the inner tool loop (max 8 tool calls per round). Between rounds:
  - Old tool results are cleared to keep context lean
  - The task plan is re-injected so the agent stays oriented
  - Completion is detected before burning the next round

This gives us explicit control over the agent's state without reimplementing
tool dispatching (which stays in execute_tool_loop).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from app.agent.models import AgentSession, AgentStatus
from app.agent.persistence import append_to_session
from app.models import ChatMessage
from app.skills.executor import _clear_old_tool_results, execute_tool_loop

if TYPE_CHECKING:
    from app.llm.client import OllamaClient
    from app.mcp.manager import McpManager
    from app.skills.registry import SkillRegistry
    from app.whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Active sessions indexed by phone number - one concurrent session per user
_active_sessions: dict[str, AgentSession] = {}
# asyncio Tasks for each active session, so we can actually cancel them
_active_tasks: dict[str, asyncio.Task] = {}

# Tools per round: conservative cap so each round can do 1-2 meaningful actions
_TOOLS_PER_ROUND = 8

# Loop detection thresholds
_LOOP_WARNING_THRESHOLD = 3
_LOOP_CIRCUIT_BREAKER = 5
_LOOP_HISTORY_SIZE = 20

_AGENT_SYSTEM_PROMPT = """\
You are a senior software engineer working autonomously on this codebase.

OBJECTIVE: {objective}

WORKFLOW:
1. UNDERSTAND: list_source_files, read_source_file, search_source_code to learn the codebase.
2. PLAN: create_task_plan with concrete, small steps.
3. EXECUTE: Use preview_patch FIRST to verify diffs visualmente, then apply_patch for actual edits. Use write_source_file only for NEW files.
4. TEST: run_command("pytest ...") after EVERY code change.
5. FIX: if tests fail, read errors, fix, re-test (max 3 attempts per step).
6. DELIVER: git_commit, git_push when all tests pass.

RULES:
- Always test after edits. Never commit untested code.
- Prefer preview_patch before apply_patch to catch formatting/indentation mistakes.
- Use apply_patch for edits to existing files. Only use write_source_file for NEW files.
- Use conventional commit messages: "fix: ...", "feat: ...", "refactor: ..."
- If a step fails 3 times, skip it and move to the next. Note the failure in the plan.
- Ask for approval (request_user_approval) before destructive operations.
- After completing each step, call update_task_status to mark it done.
- For large files (>200 lines): use get_file_outline first, then read_lines for specific sections.
  Do NOT use read_source_file on files >200 lines — use the outline+read_lines pattern.
- When ALL steps are done, write a concise summary of what was accomplished.
"""

_PLAN_REMINDER = """\

--- CURRENT TASK PLAN ---
{task_plan}
--- END TASK PLAN ---

Continue executing the next pending [ ] step. Do not repeat steps already marked [x].
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


def _inject_task_plan(messages: list[ChatMessage], task_plan: str) -> None:
    """Insert or update the task plan reminder as the second system message.

    Replaces the previous plan reminder if one exists, to avoid duplication.
    Always keeps it right after the main system prompt (index 1).
    """
    plan_content = _PLAN_REMINDER.format(task_plan=task_plan)

    # Find and replace an existing plan reminder
    for i, msg in enumerate(messages):
        if msg.role == "system" and "CURRENT TASK PLAN" in msg.content:
            messages[i] = ChatMessage(role="system", content=plan_content)
            return

    # First time: insert right after the main system prompt
    insert_pos = 1 if messages and messages[0].role == "system" else 0
    messages.insert(insert_pos, ChatMessage(role="system", content=plan_content))


def _check_loop_detection(tool_history: list[tuple[str, str]]) -> str | None:
    """Detect if the agent is stuck in a loop.

    Returns a warning message if a loop is detected, or None if OK.
    Raises RuntimeError if circuit breaker threshold is reached.

    Args:
        tool_history: List of (tool_name, params_hash) tuples from recent calls.
    """
    if len(tool_history) < _LOOP_WARNING_THRESHOLD:
        return None

    # --- genericRepeat: same (name, hash) repeated N times ---
    from collections import Counter

    counts = Counter(tool_history[-_LOOP_HISTORY_SIZE:])
    for (tool_name, _), count in counts.most_common(3):
        if count >= _LOOP_CIRCUIT_BREAKER:
            logger.warning(
                "agent.loop.detected",
                extra={
                    "detector": "genericRepeat",
                    "repeated_tool": tool_name,
                    "count": count,
                    "action": "circuit_breaker",
                },
            )
            raise RuntimeError(
                f"Loop detected: {tool_name} called {count} times with same params. "
                "Aborting round to prevent infinite loop."
            )
        if count >= _LOOP_WARNING_THRESHOLD:
            logger.warning(
                "agent.loop.detected",
                extra={
                    "detector": "genericRepeat",
                    "repeated_tool": tool_name,
                    "count": count,
                    "action": "warning",
                },
            )
            return (
                f"⚠️ You have called `{tool_name}` {count} times with identical parameters. "
                "This looks like a loop. Try a different approach or skip this step."
            )

    # --- pingPong: A→B→A→B pattern ---
    recent = tool_history[-6:]
    if len(recent) >= 4:
        names = [t[0] for t in recent]
        # Check for alternating pattern: a,b,a,b
        if len(set(names[-4:])) == 2 and names[-4] == names[-2] and names[-3] == names[-1]:
            logger.warning(
                "agent.loop.detected",
                extra={
                    "detector": "pingPong",
                    "tools": f"{names[-2]}<->{names[-1]}",
                    "action": "warning",
                },
            )
            return (
                f"⚠️ Ping-pong detected: alternating between `{names[-2]}` and `{names[-1]}` "
                "without progress. Try a different approach."
            )

    return None


def _extract_tool_history(messages: list[ChatMessage]) -> list[tuple[str, str]]:
    """Extract (tool_name, params_hash) from recent assistant messages containing tool calls."""
    history: list[tuple[str, str]] = []
    for msg in messages:
        if msg.role != "assistant":
            continue
        # Tool calls are embedded in the message content as JSON by Ollama
        # We look for patterns like tool_name + params in the content
        content = msg.content
        if not content or len(content) < 5:
            continue
        # Create a rough hash of the content to detect repetition
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        # Use a simplified name — the first word or tool indicator
        name = content.split("(")[0].split(":")[0].strip()[:40] if content else "unknown"
        history.append((name, content_hash))
    return history[-_LOOP_HISTORY_SIZE:]


def _is_session_complete(session: AgentSession, last_reply: str) -> bool:
    """Heuristic: determine if the agent considers the session complete.

    Returns True when:
    - The task plan has no remaining [ ] steps (all done), OR
    - The reply contains a completion signal and there's no task plan

    This is a soft check — max_iterations is always the hard safety net.
    """
    # Primary signal: task plan exhausted
    if session.task_plan is not None:
        pending = session.task_plan.count("[ ]")
        if pending == 0:
            logger.info(
                "Agent session %s: task plan complete (no pending steps)",
                session.session_id,
            )
            return True
        return False  # Still has work to do — don't check text signals

    # Fallback: no task plan yet, look for completion signals in the text
    completion_signals = [
        "completad",
        "terminad",
        "finaliz",
        "listo",
        "done",
        "finished",
        "accomplished",
        "all done",
        "todo completo",
    ]
    lower_reply = last_reply.lower()
    return any(sig in lower_reply for sig in completion_signals)


async def run_agent_session(
    session: AgentSession,
    ollama_client: OllamaClient,
    skill_registry: SkillRegistry,
    wa_client: WhatsAppClient,
    mcp_manager: McpManager | None = None,
) -> None:
    """Run a full agentic session in the background.

    Phase 4 architecture:
    - Outer loop: up to max_iterations rounds (controlled here)
    - Inner loop: up to _TOOLS_PER_ROUND tool calls per round (in execute_tool_loop)
    - Between rounds: task plan re-injected, old tool results cleared

    The agent iterates: Think → Call Tools → Observe → Update Plan → Loop
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

        # Build dynamic context from optional bootstrap files
        bootstrap_files = ["SOUL.md", "USER.md", "TOOLS.md"]
        for bs_file in bootstrap_files:
            bs_path = _PROJECT_ROOT / bs_file
            if bs_path.exists():
                try:
                    content = bs_path.read_text(encoding="utf-8")
                    system_content += f"\n\n--- {bs_file} ---\n{content}\n"
                except Exception as e:
                    logger.warning("Could not read bootstrap file %s: %s", bs_file, e)

        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_content),
            ChatMessage(role="user", content=session.objective),
        ]

        # Build a session-scoped registry with HITL + task-memory tools.
        # This prevents concurrent sessions from overwriting each other's closures.
        session_registry = _register_session_tools(session, skill_registry, wa_client)

        reply = ""

        # --- Outer agent loop ---
        for iteration in range(session.max_iterations):
            session.iteration = iteration
            logger.info(
                "Agent session %s — round %d/%d",
                session.session_id,
                iteration + 1,
                session.max_iterations,
            )

            # Re-inject task plan before each round so the agent stays oriented.
            # The first round may not have a plan yet (agent creates it on round 1).
            if session.task_plan:
                _inject_task_plan(messages, session.task_plan)

            # Run one round of tool execution
            reply = await execute_tool_loop(
                messages=messages,
                ollama_client=ollama_client,
                skill_registry=session_registry,
                mcp_manager=mcp_manager,
                max_tools=_TOOLS_PER_ROUND,
            )

            # Append the agent's reply to the working history
            messages.append(ChatMessage(role="assistant", content=reply))

            logger.debug(
                "Agent session %s round %d reply: %r",
                session.session_id,
                iteration + 1,
                reply[:150],
            )

            # Check for completion before clearing context
            if _is_session_complete(session, reply):
                logger.info(
                    "Agent session %s: detected completion at round %d",
                    session.session_id,
                    iteration + 1,
                )
                break

            # --- Loop detection ---
            tool_history = _extract_tool_history(messages)
            try:
                loop_warning = _check_loop_detection(tool_history)
                if loop_warning:
                    messages.append(ChatMessage(role="system", content=loop_warning))
            except RuntimeError as e:
                logger.error("Agent session %s: circuit breaker — %s", session.session_id, e)
                messages.append(ChatMessage(role="system", content=str(e)))
                break

            # --- Progress update via WhatsApp ---
            if session.task_plan:
                done = session.task_plan.count("[x]")
                total = done + session.task_plan.count("[ ]")
                logger.info(
                    "agent.progress",
                    extra={
                        "session_id": session.session_id,
                        "iteration": iteration + 1,
                        "steps_done": done,
                        "steps_total": total,
                    },
                )
                try:
                    await wa_client.send_message(
                        session.phone_number,
                        f"🔧 Round {iteration + 1}: {done}/{total} steps done",
                    )
                except Exception:
                    pass  # Best-effort, don't break the agent loop

            # --- Session Persistence ---
            try:
                round_data = {
                    "iteration": iteration + 1,
                    "task_plan": session.task_plan,
                    "reply": reply,
                    "messages": [
                        m.model_dump() if hasattr(m, "model_dump") else m.dict()
                        for m in messages[-4:]  # Save recent context
                    ],
                }
                append_to_session(session.phone_number, session.session_id, round_data)
            except Exception as e:
                logger.error("Error saving session round: %s", e)

            # Tool result clearing between rounds:
            # Keep only the last 2 raw tool results — older ones become 1-line summaries.
            # This is the key difference from the old single-call approach.
            _clear_old_tool_results(messages, keep_last_n=2)

        # --- Session ended (completion or max_iterations) ---
        session.status = AgentStatus.COMPLETED
        logger.info(
            "Agent session %s completed after %d round(s)",
            session.session_id,
            session.iteration + 1,
        )

        # Final task plan summary (if present)
        final_message = reply
        if session.task_plan:
            done = session.task_plan.count("[x]")
            pending = session.task_plan.count("[ ]")
            plan_status = f"_Plan: {done} pasos completados, {pending} pendientes._\n\n"
            final_message = plan_status + reply

        # Send final result to the user via WhatsApp
        from app.formatting.markdown_to_wa import markdown_to_whatsapp

        await wa_client.send_message(
            session.phone_number,
            markdown_to_whatsapp(f"✅ *Sesión agéntica completada*\n\n{final_message}"),
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
