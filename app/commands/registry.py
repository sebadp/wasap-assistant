from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class CommandSpec:
    name: str
    description: str
    usage: str
    handler: Callable  # async function(args: str, context: CommandContext) -> str


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, CommandSpec] = {}

    def register(self, spec: CommandSpec) -> None:
        self._commands[spec.name] = spec

    def get(self, name: str) -> CommandSpec | None:
        return self._commands.get(name)

    def list_commands(self) -> list[CommandSpec]:
        return list(self._commands.values())
