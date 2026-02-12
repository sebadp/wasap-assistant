from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.commands.context import CommandContext
from app.commands.parser import parse_command
from app.config import Settings
from app.conversation.manager import ConversationManager
from app.conversation.summarizer import maybe_summarize
from app.dependencies import (
    get_command_registry,
    get_conversation_manager,
    get_memory_file,
    get_ollama_client,
    get_repository,
    get_settings,
    get_whatsapp_client,
)
from app.llm.client import OllamaClient
from app.models import WhatsAppMessage
from app.webhook.parser import extract_messages
from app.webhook.security import validate_signature
from app.whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)

router = APIRouter()


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

    for msg in messages:
        logger.info("Incoming [%s]: %s", msg.from_number, msg.text[:80] if msg.text else "(empty)")
        if msg.from_number not in settings.allowed_phone_numbers:
            logger.warning("Message from non-whitelisted number: %s", msg.from_number)
            continue
        if await conversation.is_duplicate(msg.message_id):
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
) -> None:
    try:
        await wa_client.mark_as_read(msg.message_id)
    except Exception:
        logger.exception("Failed to mark message as read")

    # Check for commands
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

    # Normal message flow
    await conversation.add_message(
        msg.from_number, "user", msg.text, msg.message_id,
    )

    memories = await repository.get_active_memories()
    context = await conversation.get_context(
        msg.from_number, settings.system_prompt, memories,
    )

    try:
        reply = await ollama_client.chat(context)
    except Exception:
        logger.exception("Ollama chat failed")
        reply = "Sorry, I'm having trouble processing your message right now. Please try again later."

    await conversation.add_message(msg.from_number, "assistant", reply)

    try:
        await wa_client.send_message(msg.from_number, reply)
    except Exception:
        logger.exception("Failed to send WhatsApp message")

    # Summarize in background if needed
    conv_id = await conversation.get_conversation_id(msg.from_number)
    asyncio.create_task(
        maybe_summarize(
            conversation_id=conv_id,
            repository=repository,
            ollama_client=ollama_client,
            threshold=settings.summary_threshold,
            max_messages=settings.conversation_max_messages,
        )
    )
