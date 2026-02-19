from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.commands.context import CommandContext
from app.commands.registry import CommandRegistry, CommandSpec
from app.models import ChatMessage

logger = logging.getLogger(__name__)


async def cmd_remember(args: str, context: CommandContext) -> str:
    if not args.strip():
        return "Usage: /remember <something to remember>"
    memory_id = await context.repository.add_memory(args.strip())
    memories = await context.repository.list_memories()
    await context.memory_file.sync(memories)

    # Embed the new memory (best-effort)
    if context.ollama_client and context.embed_model:
        from app.embeddings.indexer import embed_memory
        await embed_memory(
            memory_id, args.strip(), context.repository,
            context.ollama_client, context.embed_model,
        )

    return f"Remembered: {args.strip()}"


async def cmd_forget(args: str, context: CommandContext) -> str:
    if not args.strip():
        return "Usage: /forget <something to forget>"
    memory_id = await context.repository.remove_memory_return_id(args.strip())
    if memory_id is None:
        return f"No active memory found matching: {args.strip()}"
    memories = await context.repository.list_memories()
    await context.memory_file.sync(memories)

    # Remove embedding (best-effort)
    if context.embed_model:
        from app.embeddings.indexer import remove_memory_embedding
        await remove_memory_embedding(memory_id, context.repository)

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

    # Save snapshot before clearing (if we have the required dependencies)
    if context.ollama_client and context.daily_log:
        try:
            await _save_session_snapshot(conv_id, context)
        except Exception:
            logger.exception("Failed to save session snapshot")

    await context.repository.clear_conversation(conv_id)
    return "Conversation history cleared."


async def _save_session_snapshot(conv_id: int, context: CommandContext) -> None:
    """Save last messages as a snapshot before clearing."""
    messages = await context.repository.get_recent_messages(conv_id, 15)
    # Filter to user and assistant only
    messages = [m for m in messages if m.role in ("user", "assistant")]
    if not messages:
        return

    # Generate slug via LLM
    conversation_preview = "\n".join(f"{m.role}: {m.content[:100]}" for m in messages[:5])
    slug_prompt = (
        "Name this conversation in 3-5 words. Use lowercase and hyphens.\n"
        "Only output the name, nothing else.\n\n"
        f"{conversation_preview}"
    )
    try:
        slug = await context.ollama_client.chat_with_tools(
            [ChatMessage(role="user", content=slug_prompt)],
            think=False,
        )
        slug = slug.content.strip().lower().replace(" ", "-")
        # Sanitize: keep only alphanumeric and hyphens
        slug = "".join(c for c in slug if c.isalnum() or c == "-").strip("-")
        if not slug:
            raise ValueError("Empty slug")
    except Exception:
        slug = datetime.now(timezone.utc).strftime("%H%M%S")

    # Format snapshot content
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"# {slug}", f"## {date_str}", ""]
    for m in messages:
        label = "User" if m.role == "user" else "Assistant"
        lines.append(f"**{label}**: {m.content}")
        lines.append("")
    content = "\n".join(lines)

    path = await context.daily_log.save_snapshot(slug, content)

    # Also log a summary entry in today's daily log
    topic = slug.replace("-", " ")
    await context.daily_log.append(f"Session cleared: {topic} ({len(messages)} messages saved)")
    logger.info("Saved session snapshot: %s", path.name)


async def cmd_setup(args: str, context: CommandContext) -> str:
    await context.repository.reset_user_profile(context.phone_number)
    return (
        "Tu perfil ha sido reiniciado. "
        "Envíame cualquier mensaje y empezamos de cero."
    )


async def cmd_help(args: str, context: CommandContext) -> str:
    registry: CommandRegistry = context.registry
    lines = ["*Available commands:*"]
    for spec in registry.list_commands():
        lines.append(f"- {spec.usage} — {spec.description}")

    if context.skill_registry:
        skills = context.skill_registry.list_skills()
        if skills:
            lines.append("")
            lines.append("*Skills (just ask me!):*")
            for skill in skills:
                lines.append(f"- 🔧 {skill.name}: {skill.description}")

    if context.mcp_manager:
        mcp_summary = context.mcp_manager.get_tools_summary()
        if mcp_summary:
            lines.append("")
            lines.append("*MCP integrations (just ask me!):*")
            # get_tools grouped by server
            tools = context.mcp_manager.get_tools()
            by_server: dict[str, list] = {}
            for tool in tools.values():
                server = tool.skill_name.removeprefix("mcp::")
                by_server.setdefault(server, []).append(tool)
            for server, server_tools in by_server.items():
                desc = context.mcp_manager._server_descriptions.get(server, server)
                lines.append(f"- 📡 {server} ({desc})")
                for tool in server_tools:
                    lines.append(f"    - {tool.name}: {tool.description}")

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
        name="setup",
        description="Reiniciar tu perfil y volver a empezar el onboarding",
        usage="/setup",
        handler=cmd_setup,
    ))
    registry.register(CommandSpec(
        name="help",
        description="Mostrar comandos disponibles",
        usage="/help",
        handler=cmd_help,
    ))
