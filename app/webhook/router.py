from __future__ import annotations

import asyncio
import base64
import logging

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.audio.transcriber import Transcriber
from app.commands.context import CommandContext
from app.commands.parser import parse_command
from app.config import Settings
from app.conversation.manager import ConversationManager
from app.conversation.summarizer import maybe_summarize
from app.formatting.whatsapp import markdown_to_whatsapp
from app.dependencies import (
    get_command_registry,
    get_conversation_manager,
    get_memory_file,
    get_ollama_client,
    get_rate_limiter,
    get_repository,
    get_settings,
    get_transcriber,
    get_whatsapp_client,
)
from app.llm.client import OllamaClient
from app.models import ChatMessage, WhatsAppMessage
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
    rate_limiter = get_rate_limiter(request)
    transcriber = get_transcriber(request)

    for msg in messages:
        logger.info("Incoming [%s] (%s): %s", msg.from_number, msg.type, msg.text[:80] if msg.text else "(empty)")
        if msg.from_number not in settings.allowed_phone_numbers:
            logger.warning("Message from non-whitelisted number: %s", msg.from_number)
            continue
        if not rate_limiter.is_allowed(msg.from_number):
            logger.warning("Rate limit exceeded for %s", msg.from_number)
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
            transcriber=transcriber,
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
    transcriber: Transcriber,
) -> None:
    try:
        await wa_client.mark_as_read(msg.message_id)
    except Exception:
        logger.exception("Failed to mark message as read")

    # Typing indicator: react with ⏳
    try:
        await wa_client.send_reaction(msg.message_id, msg.from_number, "\u23f3")
    except Exception:
        logger.debug("Failed to send typing reaction")

    try:
        await _handle_message(
            msg, settings, wa_client, ollama_client,
            conversation, repository, command_registry,
            memory_file, transcriber,
        )
    finally:
        # Remove typing indicator
        try:
            await wa_client.send_reaction(msg.message_id, msg.from_number, "")
        except Exception:
            logger.debug("Failed to remove typing reaction")


async def _handle_message(
    msg: WhatsAppMessage,
    settings: Settings,
    wa_client: WhatsAppClient,
    ollama_client: OllamaClient,
    conversation: ConversationManager,
    repository,
    command_registry,
    memory_file,
    transcriber: Transcriber,
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

    # Handle image: llava describes → qwen3 responds
    if msg.type == "image" and msg.media_id:
        try:
            image_bytes = await wa_client.download_media(msg.media_id)
            image_b64 = base64.b64encode(image_bytes).decode()

            # Step 1: llava describes the image (English is fine)
            vision_messages = [
                ChatMessage(role="user", content="Describe this image in detail.", images=[image_b64]),
            ]
            description = await ollama_client.chat(vision_messages, model=settings.vision_model)
            logger.info("Vision description [%s]: %s", msg.from_number, description[:120])

            # Step 2: pass description to qwen3 with conversation context
            user_text = msg.text or "Describe what you see in this image"
            history_text = f"[Image] {user_text}"
            await conversation.add_message(msg.from_number, "user", history_text, msg.message_id)

            # Build context with image description injected
            memories = await repository.get_active_memories()
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

    # Normal message flow (text or transcribed audio)
    user_text = msg.text
    if msg.type == "audio":
        user_text = f"[Audio] {msg.text}"

    await conversation.add_message(
        msg.from_number, "user", user_text, msg.message_id,
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
        await wa_client.send_message(msg.from_number, markdown_to_whatsapp(reply))
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
