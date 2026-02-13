from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.audio.transcriber import Transcriber
from app.commands.builtins import register_builtins
from app.commands.registry import CommandRegistry
from app.config import Settings
from app.conversation.manager import ConversationManager
from app.database.db import init_db
from app.database.repository import Repository
from app.health.router import router as health_router
from app.llm.client import OllamaClient
from app.logging_config import configure_logging
from app.memory.markdown import MemoryFile
from app.webhook.rate_limiter import RateLimiter
from app.webhook.router import router as webhook_router
from app.whatsapp.client import WhatsAppClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()

    configure_logging(level=settings.log_level, json_format=settings.log_json)

    http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))

    # Database
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    db_conn = await init_db(settings.database_path)
    repository = Repository(db_conn)

    # Memory file
    memory_file = MemoryFile(path="data/MEMORY.md")

    # Command registry
    command_registry = CommandRegistry()
    register_builtins(command_registry)

    app.state.settings = settings
    app.state.http_client = http_client
    app.state.rate_limiter = RateLimiter(
        max_requests=settings.rate_limit_max,
        window_seconds=settings.rate_limit_window,
    )
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
    app.state.repository = repository
    app.state.memory_file = memory_file
    app.state.command_registry = command_registry
    app.state.conversation_manager = ConversationManager(
        repository=repository,
        max_messages=settings.conversation_max_messages,
    )
    app.state.transcriber = Transcriber(
        model_size=settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )

    yield

    await db_conn.close()
    await http_client.aclose()


app = FastAPI(title="WasAP", lifespan=lifespan)
app.include_router(health_router)
app.include_router(webhook_router)
