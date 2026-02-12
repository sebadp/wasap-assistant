from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.config import Settings
from app.conversation.manager import ConversationManager
from app.dependencies import (
    get_conversation_manager,
    get_ollama_client,
    get_settings,
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

    for msg in messages:
        logger.info("Incoming [%s]: %s", msg.from_number, msg.text[:80] if msg.text else "(empty)")
        if msg.from_number not in settings.allowed_phone_numbers:
            logger.warning("Message from non-whitelisted number: %s", msg.from_number)
            continue
        if conversation.is_duplicate(msg.message_id):
            logger.info("Duplicate message ignored: %s", msg.message_id)
            continue
        background_tasks.add_task(
            process_message,
            msg=msg,
            settings=settings,
            wa_client=wa_client,
            ollama_client=ollama_client,
            conversation=conversation,
        )

    return Response(status_code=200)


async def process_message(
    msg: WhatsAppMessage,
    settings: Settings,
    wa_client: WhatsAppClient,
    ollama_client: OllamaClient,
    conversation: ConversationManager,
) -> None:
    try:
        await wa_client.mark_as_read(msg.message_id)
    except Exception:
        logger.exception("Failed to mark message as read")

    conversation.add_message(
        msg.from_number,
        ChatMessage(role="user", content=msg.text),
    )

    history = conversation.get_history(msg.from_number)
    llm_messages = [
        ChatMessage(role="system", content=settings.system_prompt),
        *history,
    ]

    try:
        reply = await ollama_client.chat(llm_messages)
    except Exception:
        logger.exception("Ollama chat failed")
        reply = "Sorry, I'm having trouble processing your message right now. Please try again later."

    conversation.add_message(
        msg.from_number,
        ChatMessage(role="assistant", content=reply),
    )

    try:
        await wa_client.send_message(msg.from_number, reply)
    except Exception:
        logger.exception("Failed to send WhatsApp message")
