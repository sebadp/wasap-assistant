from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from app.skills.loader import scan_skills_directory
from app.skills.models import SkillMetadata, ToolCall, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


class SkillRegistry:
    def __init__(self, skills_dir: str = "data/skills"):
        self._skills_dir = skills_dir
        self._tools: dict[str, ToolDefinition] = {}
        self._skills: dict[str, SkillMetadata] = {}
        self._loaded_instructions: set[str] = set()

    def load_skills(self) -> None:
        """Scan skills directory and load metadata."""
        skills = scan_skills_directory(self._skills_dir)
        for skill in skills:
            self._skills[skill.name] = skill
            logger.info("Registered skill metadata: %s", skill.name)

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., Awaitable[str]],
        skill_name: str | None = None,
    ) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            skill_name=skill_name,
        )
        logger.info("Registered tool: %s (skill: %s)", name, skill_name or "builtin")

    def get_ollama_tools(self) -> list[dict]:
        """Return tool schemas in Ollama's expected format."""
        tools = []
        for tool in self._tools.values():
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return tools

    def get_tools_summary(self) -> str:
        """Return a compact summary of available tools for the system prompt."""
        if not self._tools:
            return ""
        lines = ["Available tools:"]
        for tool in self._tools.values():
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)

    async def execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call and return the result."""
        tool = self._tools.get(tool_call.name)
        if not tool:
            return ToolResult(
                tool_name=tool_call.name,
                content=f"Unknown tool: {tool_call.name}",
                success=False,
            )
        try:
            result = await tool.handler(**tool_call.arguments)
            return ToolResult(tool_name=tool_call.name, content=result)
        except Exception as e:
            logger.exception("Tool %s execution failed", tool_call.name)
            return ToolResult(
                tool_name=tool_call.name,
                content=f"Tool error: {e}",
                success=False,
            )

    def get_skill_instructions(self, tool_name: str) -> str | None:
        """Lazy-load skill instructions the first time a tool from that skill is used."""
        tool = self._tools.get(tool_name)
        if not tool or not tool.skill_name:
            return None

        skill = self._skills.get(tool.skill_name)
        if not skill or not skill.instructions:
            return None

        if tool.skill_name in self._loaded_instructions:
            return None

        self._loaded_instructions.add(tool.skill_name)
        return skill.instructions

    def list_skills(self) -> list[SkillMetadata]:
        """Return all loaded skill metadata."""
        return list(self._skills.values())

    def has_tools(self) -> bool:
        return len(self._tools) > 0

    def get_skill(self, name: str) -> SkillMetadata | None:
        return self._skills.get(name)

    def get_tools_for_skill(self, skill_name: str) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if t.skill_name == skill_name]
