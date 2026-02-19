import asyncio
import logging
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
from app.models import ChatMessage
from app.memory.daily_log import DailyLog
from app.memory.markdown import MemoryFile
from app.skills.registry import SkillRegistry
from app.skills.tools import register_builtin_tools
from app.webhook.rate_limiter import RateLimiter
from app.webhook.router import router as webhook_router, wait_for_in_flight
from app.whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()

    configure_logging(level=settings.log_level, json_format=settings.log_json)

    http_client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0))

    # Database
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    db_conn, vec_available = await init_db(
        settings.database_path,
        embedding_dims=settings.embedding_dimensions,
    )
    repository = Repository(db_conn)

    # Memory
    memory_file = MemoryFile(path="data/MEMORY.md")
    daily_log = DailyLog(memory_dir=settings.memory_dir)

    # Command registry
    command_registry = CommandRegistry()
    register_builtins(command_registry)

    app.state.vec_available = vec_available
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
    app.state.daily_log = daily_log
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

    # Skills
    skill_registry = SkillRegistry(skills_dir=settings.skills_dir)
    skill_registry.load_skills()
    register_builtin_tools(
        skill_registry, repository,
        ollama_client=app.state.ollama_client,
        embed_model=settings.embedding_model if settings.semantic_search_enabled and vec_available else None,
        vec_available=vec_available,
    )
    app.state.skill_registry = skill_registry

    # MCP Manager
    from app.mcp.manager import McpManager
    mcp_manager = McpManager(config_path=settings.mcp_config_path)
    await mcp_manager.initialize()
    app.state.mcp_manager = mcp_manager

    # Scheduler Skill
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.skills.tools.scheduler_tools import set_scheduler

    scheduler = AsyncIOScheduler()
    scheduler.start()
    set_scheduler(scheduler, app.state.whatsapp_client)
    app.state.scheduler = scheduler

    # Memory file watcher (bidirectional sync)
    memory_watcher = None
    if settings.memory_file_watch_enabled:
        try:
            import asyncio
            from app.memory.watcher import MemoryWatcher
            memory_watcher = MemoryWatcher(
                memory_file=memory_file,
                repository=repository,
                loop=asyncio.get_event_loop(),
            )
            memory_file.set_watcher(memory_watcher)
            memory_watcher.start()
        except ImportError:
            import logging
            logging.getLogger(__name__).warning(
                "watchdog not installed, MEMORY.md file watching disabled. "
                "Install with: pip install watchdog"
            )
    app.state.memory_watcher = memory_watcher

    # Backfill embeddings at startup
    if vec_available and settings.semantic_search_enabled:
        from app.embeddings.indexer import backfill_embeddings, backfill_note_embeddings
        try:
            await backfill_embeddings(
                repository, app.state.ollama_client, settings.embedding_model,
            )
            await backfill_note_embeddings(
                repository, app.state.ollama_client, settings.embedding_model,
            )
        except Exception:
            import logging
            logging.getLogger(__name__).warning("Embedding backfill failed at startup", exc_info=True)

    # Warmup: pre-load Ollama models to avoid cold-start on first message
    try:
        await asyncio.gather(
            app.state.ollama_client.embed(["warmup"], model=settings.embedding_model),
            app.state.ollama_client.chat_with_tools(
                [ChatMessage(role="user", content="hi")], think=False,
            ),
        )
        logger.info("Ollama models warmed up")
    except Exception:
        logger.warning("Model warmup failed (non-critical)", exc_info=True)

    yield

    await wait_for_in_flight(timeout=30.0)
    if memory_watcher:
        memory_watcher.stop()
    scheduler.shutdown()
    await mcp_manager.cleanup()
    await db_conn.close()
    await http_client.aclose()


app = FastAPI(title="WasAP", lifespan=lifespan)
app.include_router(health_router)
app.include_router(webhook_router)
