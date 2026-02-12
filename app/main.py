import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.config import Settings
from app.conversation.manager import ConversationManager
from app.health.router import router as health_router
from app.llm.client import OllamaClient
from app.webhook.router import router as webhook_router
from app.whatsapp.client import WhatsAppClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))

    app.state.settings = settings
    app.state.http_client = http_client
    app.state.whatsapp_client = WhatsAppClient(
        http_client=http_client,
        access_token=settings.whatsapp_access_token,
        phone_number_id=settings.whatsapp_phone_number_id,
    )
    app.state.ollama_client = OllamaClient(
        http_client=http_client,
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
    )
    app.state.conversation_manager = ConversationManager(
        max_messages=settings.conversation_max_messages,
    )

    yield

    await http_client.aclose()


app = FastAPI(title="WasAP", lifespan=lifespan)
app.include_router(health_router)
app.include_router(webhook_router)
