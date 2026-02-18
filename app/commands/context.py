from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.commands.registry import CommandRegistry
    from app.database.repository import Repository
    from app.memory.markdown import MemoryFile


@dataclass
class CommandContext:
    repository: Repository
    memory_file: MemoryFile
    phone_number: str
    registry: Any = field(default=None, repr=False)
    skill_registry: Any = field(default=None, repr=False)
    mcp_manager: Any = field(default=None, repr=False)
