from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.skills.router import TOOL_CATEGORIES

if TYPE_CHECKING:
    from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


def register(registry: SkillRegistry) -> None:
    async def list_tool_categories() -> str:
        lines = []
        for category, tools in TOOL_CATEGORIES.items():
            lines.append(f"- {category}: {len(tools)} tools")
        return "\n".join(lines)

    async def list_category_tools(category: str) -> str:
        tools = TOOL_CATEGORIES.get(category.lower().strip())
        if tools is None:
            available = ", ".join(TOOL_CATEGORIES.keys())
            return f"Unknown category: {category}. Available: {available}"
        lines = [f"Tools in '{category}':"]
        for name in tools:
            lines.append(f"- {name}")
        return "\n".join(lines)

    registry.register_tool(
        name="list_tool_categories",
        description="List all available tool categories and how many tools each has",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
        handler=list_tool_categories,
        skill_name="tools",
    )

    registry.register_tool(
        name="list_category_tools",
        description="List the tools available in a specific category",
        parameters={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category name (e.g. time, math, weather, search, news, notes, files, memory, github, tools)",
                },
            },
            "required": ["category"],
        },
        handler=list_category_tools,
        skill_name="tools",
    )
