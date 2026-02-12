from __future__ import annotations

from app.commands.context import CommandContext
from app.commands.registry import CommandRegistry, CommandSpec


async def cmd_remember(args: str, context: CommandContext) -> str:
    if not args.strip():
        return "Usage: /remember <something to remember>"
    await context.repository.add_memory(args.strip())
    memories = await context.repository.list_memories()
    await context.memory_file.sync(memories)
    return f"Remembered: {args.strip()}"


async def cmd_forget(args: str, context: CommandContext) -> str:
    if not args.strip():
        return "Usage: /forget <something to forget>"
    removed = await context.repository.remove_memory(args.strip())
    if not removed:
        return f"No active memory found matching: {args.strip()}"
    memories = await context.repository.list_memories()
    await context.memory_file.sync(memories)
    return f"Forgot: {args.strip()}"


async def cmd_memories(args: str, context: CommandContext) -> str:
    memories = await context.repository.list_memories()
    if not memories:
        return "No memories saved yet. Use /remember <info> to save something."
    lines = ["*Memories:*"]
    for m in memories:
        if m.category:
            lines.append(f"- [{m.category}] {m.content}")
        else:
            lines.append(f"- {m.content}")
    return "\n".join(lines)


async def cmd_clear(args: str, context: CommandContext) -> str:
    conv_id = await context.repository.get_or_create_conversation(context.phone_number)
    await context.repository.clear_conversation(conv_id)
    return "Conversation history cleared."


async def cmd_help(args: str, context: CommandContext) -> str:
    registry: CommandRegistry = context.registry
    lines = ["*Available commands:*"]
    for spec in registry.list_commands():
        lines.append(f"- {spec.usage} — {spec.description}")
    return "\n".join(lines)


def register_builtins(registry: CommandRegistry) -> None:
    registry.register(CommandSpec(
        name="remember",
        description="Guardar información importante",
        usage="/remember <dato>",
        handler=cmd_remember,
    ))
    registry.register(CommandSpec(
        name="forget",
        description="Olvidar un recuerdo guardado",
        usage="/forget <dato>",
        handler=cmd_forget,
    ))
    registry.register(CommandSpec(
        name="memories",
        description="Listar todos los recuerdos",
        usage="/memories",
        handler=cmd_memories,
    ))
    registry.register(CommandSpec(
        name="memory",
        description="Listar todos los recuerdos",
        usage="/memory",
        handler=cmd_memories,
    ))
    registry.register(CommandSpec(
        name="clear",
        description="Borrar historial de conversación",
        usage="/clear",
        handler=cmd_clear,
    ))
    registry.register(CommandSpec(
        name="help",
        description="Mostrar comandos disponibles",
        usage="/help",
        handler=cmd_help,
    ))
