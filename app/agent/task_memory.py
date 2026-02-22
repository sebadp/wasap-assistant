"""Task memory tools for agentic sessions.

Registers three tools that the LLM can call during an agent session:
- get_task_plan: Read the current task plan
- create_task_plan: Create or replace the task plan with a markdown checklist
- update_task_status: Mark a specific task item as done or pending
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.models import AgentSession
    from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


def register_task_memory_tools(
    skill_registry: SkillRegistry,
    session_getter: Callable[[], AgentSession | None],
) -> None:
    """Register the three task-memory tools in the skill registry."""

    async def get_task_plan() -> str:
        """Read the current task plan for this agent session."""
        session = session_getter()
        if not session:
            return "No active agent session."
        if not session.task_plan:
            return "No task plan created yet. Use create_task_plan to create one."
        return session.task_plan

    async def create_task_plan(plan: str) -> str:
        """Create or overwrite the task plan for this agent session.

        Use a markdown checklist format:
        - [ ] Step 1
        - [ ] Step 2
        - [ ] Step 3
        """
        session = session_getter()
        if not session:
            return "Error: No active agent session."
        pending_count = plan.count("[ ]")
        session.task_plan = plan
        logger.info(
            "Agent session %s: task plan created with %d steps",
            session.session_id,
            pending_count,
        )
        return f"✅ Task plan created with {pending_count} pending steps."

    async def update_task_status(task_index: int, done: bool = True) -> str:
        """Mark a specific task as done [x] or pending [ ] by its 1-based index.

        Example: update_task_status(task_index=2, done=True) marks the 2nd task done.
        """
        session = session_getter()
        if not session:
            return "Error: No active agent session."
        if not session.task_plan:
            return "Error: No task plan exists. Call create_task_plan first."

        lines = session.task_plan.split("\n")
        task_count = 0
        for i, line in enumerate(lines):
            if "[ ]" in line or "[x]" in line:
                task_count += 1
                if task_count == task_index:
                    if done:
                        lines[i] = line.replace("[ ]", "[x]", 1)
                    else:
                        lines[i] = line.replace("[x]", "[ ]", 1)
                    session.task_plan = "\n".join(lines)
                    logger.info(
                        "Agent session %s: task %d marked %s",
                        session.session_id,
                        task_index,
                        "done" if done else "pending",
                    )
                    return (
                        f"✅ Task {task_index} marked as {'done' if done else 'pending'}.\n"
                        f"Current plan:\n{session.task_plan}"
                    )

        return (
            f"Error: Task {task_index} not found "
            f"(plan has {task_count} total tasks). "
            "Use get_task_plan to see the current plan."
        )

    skill_registry.register_tool(
        name="get_task_plan",
        description=(
            "Read the current task plan for this agent session. "
            "Use this at the start of each iteration to re-orient yourself."
        ),
        parameters={"type": "object", "properties": {}},
        handler=get_task_plan,
        skill_name="agent",
    )

    skill_registry.register_tool(
        name="create_task_plan",
        description=(
            "Create or overwrite the task plan for this agent session. "
            "Use a markdown checklist: '- [ ] Step 1\\n- [ ] Step 2'. "
            "Call this at the beginning of the session before executing steps."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan": {
                    "type": "string",
                    "description": "Markdown checklist with [ ] for pending and [x] for done steps",
                },
            },
            "required": ["plan"],
        },
        handler=create_task_plan,
        skill_name="agent",
    )

    skill_registry.register_tool(
        name="update_task_status",
        description=(
            "Mark a specific task as done [x] or pending [ ] by its 1-based index number. "
            "Example: task_index=1 marks the first task in the plan."
        ),
        parameters={
            "type": "object",
            "properties": {
                "task_index": {
                    "type": "integer",
                    "description": "1-based index of the task to update",
                },
                "done": {
                    "type": "boolean",
                    "description": "True to mark done [x], False to mark pending [ ]. Defaults to True.",
                    "default": True,
                },
            },
            "required": ["task_index"],
        },
        handler=update_task_status,
        skill_name="agent",
    )
