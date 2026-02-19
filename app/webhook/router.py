from __future__ import annotations

import asyncio
import base64
import datetime
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.audio.transcriber import Transcriber
from app.commands.context import CommandContext
from app.commands.parser import parse_command
from app.config import Settings
from app.conversation.manager import ConversationManager
from app.conversation.summarizer import maybe_summarize
from app.formatting.whatsapp import markdown_to_whatsapp
from app.profiles.discovery import maybe_discover_profile_updates
from app.profiles.onboarding import handle_onboarding_message
from app.profiles.prompt_builder import build_system_prompt
from app.dependencies import (
    get_command_registry,
    get_conversation_manager,
    get_daily_log,
    get_memory_file,
    get_ollama_client,
    get_rate_limiter,
    get_repository,
    get_settings,
    get_skill_registry,
    get_transcriber,
    get_vec_available,
    get_whatsapp_client,
    get_mcp_manager,
)
from app.llm.client import OllamaClient
from app.memory.daily_log import DailyLog
from app.models import ChatMessage, Note, WhatsAppMessage
from app.skills.executor import execute_tool_loop
from app.skills.registry import SkillRegistry
from app.skills.router import classify_intent
from app.webhook.parser import extract_messages
from app.webhook.security import validate_signature
from app.whatsapp.client import WhatsAppClient

if TYPE_CHECKING:
    from app.commands.registry import CommandRegistry
    from app.mcp.manager import McpManager

logger = logging.getLogger(__name__)

router = APIRouter()

_in_flight: set[asyncio.Task] = set()


def _track_task(task: asyncio.Task) -> asyncio.Task:
    """Track a background task for graceful shutdown."""
    _in_flight.add(task)
    task.add_done_callback(_in_flight.discard)
    return task


async def wait_for_in_flight(timeout: float = 30.0) -> None:
    """Wait for all in-flight background tasks to complete."""
    if not _in_flight:
        return
    logger.info("Waiting for %d in-flight tasks (timeout=%.1fs)", len(_in_flight), timeout)
    done, pending = await asyncio.wait(_in_flight, timeout=timeout)
    if pending:
        logger.warning("%d tasks still running after timeout", len(pending))


@router.get("/webhook")
async def verify_webhook(
    request: Request,
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
) -> Response:
    settings = get_settings(request)
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(content=hub_challenge)
    return PlainTextResponse(content="Forbidden", status_code=403)


@router.post("/webhook")
async def incoming_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    settings = get_settings(request)
    body = await request.body()

    # Validate signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not validate_signature(body, signature, settings.whatsapp_app_secret):
        logger.warning("Invalid webhook signature")
        return Response(status_code=200)

    payload = await request.json()
    messages = extract_messages(payload)

    wa_client = get_whatsapp_client(request)
    ollama_client = get_ollama_client(request)
    conversation = get_conversation_manager(request)
    repository = get_repository(request)
    command_registry = get_command_registry(request)
    memory_file = get_memory_file(request)
    daily_log = get_daily_log(request)
    rate_limiter = get_rate_limiter(request)
    transcriber = get_transcriber(request)
    skill_registry = get_skill_registry(request)
    mcp_manager = get_mcp_manager(request)
    vec_available = get_vec_available(request)

    for msg in messages:
        logger.info("Incoming [%s] (%s): %s", msg.from_number, msg.type, msg.text[:80] if msg.text else "(empty)")
        if msg.from_number not in settings.allowed_phone_numbers:
            logger.warning("Message from non-whitelisted number: %s", msg.from_number)
            continue
        if not rate_limiter.is_allowed(msg.from_number):
            logger.warning("Rate limit exceeded for %s", msg.from_number)
            continue
        if await repository.try_claim_message(msg.message_id):
            logger.info("Duplicate message ignored: %s", msg.message_id)
            continue
        background_tasks.add_task(
            process_message,
            msg=msg,
            settings=settings,
            wa_client=wa_client,
            ollama_client=ollama_client,
            conversation=conversation,
            repository=repository,
            command_registry=command_registry,
            memory_file=memory_file,
            daily_log=daily_log,
            transcriber=transcriber,
            skill_registry=skill_registry,
            mcp_manager=mcp_manager,
            vec_available=vec_available,
        )

    return Response(status_code=200)


async def process_message(
    msg: WhatsAppMessage,
    settings: Settings,
    wa_client: WhatsAppClient,
    ollama_client: OllamaClient,
    conversation: ConversationManager,
    repository,
    command_registry,
    memory_file,
    daily_log: DailyLog,
    transcriber: Transcriber,
    skill_registry: SkillRegistry,
    mcp_manager: McpManager | None = None,
    vec_available: bool = False,
) -> None:
    # Parallelize initial WhatsApp calls (mark-read + typing indicator)
    try:
        await asyncio.gather(
            wa_client.mark_as_read(msg.message_id),
            wa_client.send_reaction(msg.message_id, msg.from_number, "\u23f3"),
        )
    except Exception:
        logger.debug("Failed to send initial WhatsApp signals")

    try:
        await _handle_message(
            msg, settings, wa_client, ollama_client,
            conversation, repository, command_registry,
            memory_file, daily_log, transcriber, skill_registry,
            mcp_manager=mcp_manager,
            vec_available=vec_available,
        )
    finally:
        # Remove typing indicator
        try:
            await wa_client.send_reaction(msg.message_id, msg.from_number, "")
        except Exception:
            logger.debug("Failed to remove typing reaction")


async def _get_query_embedding(
    user_text: str,
    settings: Settings,
    ollama_client: OllamaClient,
    vec_available: bool,
) -> list[float] | None:
    """Get query embedding for semantic search. Returns None on failure."""
    if settings.semantic_search_enabled and vec_available and user_text:
        try:
            result = await ollama_client.embed(
                [user_text], model=settings.embedding_model,
            )
            return result[0]
        except Exception:
            logger.warning("Failed to compute query embedding", exc_info=True)
    return None


async def _get_memories(
    user_text: str,
    settings: Settings,
    ollama_client: OllamaClient,
    repository,
    vec_available: bool,
    query_embedding: list[float] | None = None,
) -> list[str]:
    """Get relevant memories: semantic search if available, else all active."""
    if query_embedding is not None:
        try:
            return await repository.search_similar_memories(
                query_embedding, top_k=settings.semantic_search_top_k,
            )
        except Exception:
            logger.warning("Semantic memory search failed, falling back to all memories", exc_info=True)
    return await repository.get_active_memories(limit=settings.semantic_search_top_k)


async def _get_relevant_notes(
    query_embedding: list[float] | None,
    settings: Settings,
    repository,
    vec_available: bool,
) -> list[Note]:
    """Get relevant notes via semantic search if available."""
    if settings.semantic_search_enabled and vec_available and query_embedding:
        try:
            return await repository.search_similar_notes(
                query_embedding, top_k=5,
            )
        except Exception:
            logger.warning("Semantic note search failed", exc_info=True)
    return []


def _build_capabilities_section(
    skill_registry: SkillRegistry,
    command_registry: CommandRegistry,
    mcp_manager: McpManager | None,
) -> str | None:
    """Build a rich, structured capabilities section for the LLM context.

    Groups commands, skills (with their tools), and MCP servers so the
    agent knows what it can do and when to use each capability.
    """
    sections: list[str] = []

    # --- Commands (user-typed /slash commands) ---
    commands = command_registry.list_commands()
    if commands:
        cmd_lines = ["Commands (the user types these directly — if they ask how to save info, mention /remember):"]
        for cmd in commands:
            cmd_lines.append(f"  /{cmd.name} — {cmd.description}")
        sections.append("\n".join(cmd_lines))

    # --- Skills (tool-calling) ---
    skills = skill_registry.list_skills()
    if skills:
        skill_lines = ["Skills (you call these via tool calling):"]
        for skill in skills:
            tool_names = [t.name for t in skill_registry.get_tools_for_skill(skill.name)]
            tools_str = ", ".join(tool_names) if tool_names else "no tools registered"
            skill_lines.append(f"  {skill.name} — {skill.description}")
            skill_lines.append(f"    Tools: {tools_str}")
        sections.append("\n".join(skill_lines))

    # --- MCP Servers ---
    if mcp_manager:
        mcp_tools = mcp_manager.get_tools()
        if mcp_tools:
            by_server: dict[str, list[str]] = {}
            for tool in mcp_tools.values():
                server = tool.skill_name.removeprefix("mcp::")
                by_server.setdefault(server, []).append(f"{tool.name}: {tool.description}")

            mcp_lines = ["MCP Servers (external integrations):"]
            for server_name, tool_descs in by_server.items():
                desc = mcp_manager._server_descriptions.get(server_name, "")
                header = f"  {server_name} ({desc})" if desc else f"  {server_name}"
                mcp_lines.append(header)
                for td in tool_descs:
                    mcp_lines.append(f"    - {td}")
            sections.append("\n".join(mcp_lines))

    if not sections:
        return None

    header = "You have the following capabilities. Use them proactively when the user's message is relevant."
    return header + "\n\n" + "\n\n".join(sections)


async def _get_active_projects_summary(phone_number: str, repository) -> str | None:
    """Build a brief projects status line for the LLM context. Returns None if no active projects."""
    try:
        projects = await repository.list_projects(phone_number, status="active")
        if not projects:
            return None
        capped = projects[:5]
        lines = ["Active projects:"]
        for p in capped:
            progress = await repository.get_project_progress(p.id)
            total = progress["total"]
            done = progress["done"]
            pct = int(done / total * 100) if total > 0 else 0
            lines.append(f"  - {p.name}: {done}/{total} tasks ({pct}%)")
        return "\n".join(lines)
    except Exception:
        logger.warning("Failed to fetch active projects summary", exc_info=True)
        return None


def _build_context(
    system_prompt: str,
    memories: list[str],
    relevant_notes: list[Note],
    daily_logs: str | None,
    skills_summary: str | None,
    summary: str | None,
    history: list[ChatMessage],
    projects_summary: str | None = None,
) -> list[ChatMessage]:
    """Build LLM context from pre-fetched data (sync, no DB calls)."""
    context = [ChatMessage(role="system", content=system_prompt)]
    if memories:
        memory_block = "Important user information:\n" + "\n".join(f"- {m}" for m in memories)
        context.append(ChatMessage(role="system", content=memory_block))
    if projects_summary:
        context.append(ChatMessage(role="system", content=projects_summary))
    if relevant_notes:
        notes_block = "Relevant notes:\n" + "\n".join(
            f"- [{n.id}] {n.title}: {n.content[:200]}" for n in relevant_notes
        )
        context.append(ChatMessage(role="system", content=notes_block))
    if daily_logs:
        context.append(ChatMessage(role="system", content=f"Recent activity log:\n{daily_logs}"))
    if skills_summary:
        context.append(ChatMessage(role="system", content=skills_summary))
    if summary:
        context.append(ChatMessage(role="system", content=f"Previous conversation summary:\n{summary}"))
    context.extend(history)
    return context


async def _handle_message(
    msg: WhatsAppMessage,
    settings: Settings,
    wa_client: WhatsAppClient,
    ollama_client: OllamaClient,
    conversation: ConversationManager,
    repository,
    command_registry,
    memory_file,
    daily_log: DailyLog,
    transcriber: Transcriber,
    skill_registry: SkillRegistry,
    mcp_manager: McpManager | None = None,
    vec_available: bool = False,
) -> None:
    # Handle audio: transcribe to text
    if msg.type == "audio" and msg.media_id:
        try:
            audio_bytes = await wa_client.download_media(msg.media_id)
            transcription = await transcriber.transcribe_async(audio_bytes)
            logger.info("Transcribed audio [%s]: %s", msg.from_number, transcription[:80])
            msg = msg.model_copy(update={"text": transcription})
        except Exception:
            logger.exception("Audio transcription failed")
            await wa_client.send_message(msg.from_number, "Sorry, I couldn't process that audio. Please try again.")
            return

    # Load user profile early (after audio transcription, so audio can feed into onboarding)
    profile_row = await repository.get_user_profile(msg.from_number)
    in_onboarding = (
        settings.onboarding_enabled
        and profile_row["onboarding_state"] != "complete"
    )

    # Handle image: llava describes → used as onboarding answer OR qwen3 responds normally
    if msg.type == "image" and msg.media_id:
        try:
            image_bytes = await wa_client.download_media(msg.media_id)
            image_b64 = base64.b64encode(image_bytes).decode()

            # Step 1: llava describes the image
            vision_messages = [
                ChatMessage(role="user", content="Describe this image in detail.", images=[image_b64]),
            ]
            description = await ollama_client.chat(vision_messages, model=settings.vision_model)
            logger.info("Vision description [%s]: %s", msg.from_number, description[:120])

            if in_onboarding:
                # During onboarding: use image description as the user's answer to current step
                user_text = description
                next_state, reply, new_data = await handle_onboarding_message(
                    user_text,
                    profile_row["onboarding_state"],
                    profile_row["data"],
                    ollama_client,
                )
                await repository.save_user_profile(msg.from_number, next_state, new_data)
                await wa_client.send_message(msg.from_number, reply)
                return

            # Normal image flow: pass description to qwen3 with conversation context
            user_text = msg.text or "Describe what you see in this image"
            history_text = f"[Image] {user_text}"
            await conversation.add_message(msg.from_number, "user", history_text, msg.message_id)

            # Build context with image description injected
            query_emb = await _get_query_embedding(
                user_text, settings, ollama_client, vec_available,
            )
            memories = await _get_memories(
                user_text, settings, ollama_client, repository, vec_available,
                query_embedding=query_emb,
            )
            context = await conversation.get_context(
                msg.from_number, settings.system_prompt, memories,
            )
            # Add image description as context for qwen3
            context.append(ChatMessage(
                role="user",
                content=f"[The user sent an image. Description: {description}]\n\n{user_text}",
            ))

            reply = await ollama_client.chat(context)
            await conversation.add_message(msg.from_number, "assistant", reply)
            await wa_client.send_message(msg.from_number, markdown_to_whatsapp(reply))
        except Exception:
            logger.exception("Image processing failed")
            await wa_client.send_message(msg.from_number, "Sorry, I couldn't process that image. Please try again.")
        return

    # Check for commands (text-based only)
    parsed = parse_command(msg.text)
    if parsed:
        cmd_name, cmd_args = parsed
        spec = command_registry.get(cmd_name)
        if spec:
            ctx = CommandContext(
                repository=repository,
                memory_file=memory_file,
                phone_number=msg.from_number,
                registry=command_registry,
                skill_registry=skill_registry,
                mcp_manager=mcp_manager,
                ollama_client=ollama_client,
                daily_log=daily_log,
                embed_model=settings.embedding_model if settings.semantic_search_enabled and vec_available else None,
            )
            try:
                reply = await spec.handler(cmd_args, ctx)
            except Exception:
                logger.exception("Command %s failed", cmd_name)
                reply = "Sorry, that command failed. Please try again."
        else:
            reply = f"Unknown command: /{cmd_name}. Type /help for available commands."
        try:
            await wa_client.send_message(msg.from_number, reply)
        except Exception:
            logger.exception("Failed to send WhatsApp message")
        return

    # Onboarding interception: handle before normal flow
    if in_onboarding:
        try:
            next_state, reply, new_data = await handle_onboarding_message(
                msg.text,
                profile_row["onboarding_state"],
                profile_row["data"],
                ollama_client,
            )
            await repository.save_user_profile(msg.from_number, next_state, new_data)
            await wa_client.send_message(msg.from_number, reply)
        except Exception:
            logger.exception("Onboarding step failed")
            await wa_client.send_message(
                msg.from_number,
                "Sorry, something went wrong. Please try again.",
            )
        return

    # Normal message flow (text or transcribed audio)
    user_text = msg.text
    if msg.type == "audio":
        user_text = f"[Audio] {msg.text}"

    # Inject current date + user profile into system prompt
    # (date only — for current time the LLM should call get_current_datetime)
    now = datetime.datetime.now(datetime.timezone.utc)
    current_date = now.strftime("%Y-%m-%d")
    system_prompt_with_date = build_system_prompt(
        settings.system_prompt, profile_row["data"], current_date,
    )

    # Reply context: prepend quoted message if replying (sequential, needs result before Phase A)
    if msg.reply_to_message_id:
        quoted = await repository.get_message_by_wa_id(msg.reply_to_message_id)
        if quoted:
            user_text = f'[Replying to: "{quoted.content[:200]}"]\n{user_text}'

    # Get/create conversation once (populates the manager's cache)
    conv_id = await conversation.get_conversation_id(msg.from_number)

    # Determine if tools are available (used for classify_task)
    has_tools = skill_registry.has_tools() or bool(mcp_manager and mcp_manager.get_tools())

    # Kick off classify_intent in parallel with Phase A/B (LLM call, 1-3s)
    classify_task: asyncio.Task[list[str]] | None = None
    if has_tools:
        classify_task = asyncio.create_task(classify_intent(user_text, ollama_client))

    # Phase A (parallel): embed query || save user message || load daily logs
    query_embedding, _, daily_logs = await asyncio.gather(
        _get_query_embedding(user_text, settings, ollama_client, vec_available),
        repository.save_message(conv_id, "user", user_text, msg.message_id),
        daily_log.load_recent(days=settings.daily_log_days),
    )

    # Phase B (parallel): search memories || search notes || get summary || get history || active projects
    memories, relevant_notes, summary, history, projects_summary = await asyncio.gather(
        _get_memories(user_text, settings, ollama_client, repository, vec_available, query_embedding),
        _get_relevant_notes(query_embedding, settings, repository, vec_available),
        repository.get_latest_summary(conv_id),
        repository.get_recent_messages(conv_id, settings.conversation_max_messages),
        _get_active_projects_summary(msg.from_number, repository),
    )

    # Capabilities summary (sync, fast)
    skills_summary = _build_capabilities_section(skill_registry, command_registry, mcp_manager)

    # Phase C: await classify_task (should be mostly done by now)
    pre_classified: list[str] | None = None
    if classify_task is not None:
        try:
            pre_classified = await classify_task
        except Exception:
            logger.warning("classify_intent task failed, executor will retry", exc_info=True)

    # Phase D: build context (sync) → main LLM call (~3-8s)
    context = _build_context(
        system_prompt_with_date, memories, relevant_notes, daily_logs,
        skills_summary, summary, history,
        projects_summary=projects_summary,
    )

    # Set current user context for tools that need it (e.g. scheduler, projects)
    from app.skills.tools.scheduler_tools import set_current_user
    from app.skills.tools.project_tools import set_current_user as set_project_user
    set_current_user(msg.from_number, received_at=now)
    set_project_user(msg.from_number)

    try:
        if has_tools:
            reply = await execute_tool_loop(
                context, ollama_client, skill_registry,
                mcp_manager=mcp_manager,
                max_tools=settings.max_tools_per_call,
                pre_classified_categories=pre_classified,
            )
        else:
            reply = await ollama_client.chat(context)
    except Exception:
        logger.exception("Ollama chat failed")
        reply = "Sorry, I'm having trouble processing your message right now. Please try again later."

    await repository.save_message(conv_id, "assistant", reply)

    try:
        await wa_client.send_message(msg.from_number, markdown_to_whatsapp(reply))
    except Exception:
        logger.exception("Failed to send WhatsApp message")

    # Increment profile message count and maybe run progressive discovery
    if settings.onboarding_enabled:
        new_count = await repository.increment_profile_message_count(msg.from_number)
        _track_task(asyncio.create_task(
            maybe_discover_profile_updates(
                msg.from_number,
                new_count,
                settings.profile_discovery_interval,
                repository,
                ollama_client,
                settings,
            )
        ))

    # Summarize in background if needed
    _track_task(asyncio.create_task(
        maybe_summarize(
            conversation_id=conv_id,
            repository=repository,
            ollama_client=ollama_client,
            threshold=settings.summary_threshold,
            max_messages=settings.conversation_max_messages,
            daily_log=daily_log,
            memory_file=memory_file,
            flush_enabled=settings.memory_flush_enabled,
            embed_model=settings.embedding_model if settings.semantic_search_enabled and vec_available else None,
        )
    ))
