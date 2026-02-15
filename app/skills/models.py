from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[str]]
    skill_name: str | None = None


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    tool_name: str
    content: str
    success: bool = True


@dataclass
class SkillMetadata:
    name: str
    description: str
    version: int = 1
    tools: list[str] = field(default_factory=list)
    instructions: str = ""
