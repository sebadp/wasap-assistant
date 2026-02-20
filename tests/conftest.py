import asyncio
import hashlib
import hmac
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.commands.builtins import register_builtins
from app.commands.registry import CommandRegistry
from app.config import Settings
from app.conversation.manager import ConversationManager
from app.database.db import init_db
from app.database.repository import Repository
from app.llm.client import OllamaClient
from app.main import app
from app.memory.daily_log import DailyLog
from app.memory.markdown import MemoryFile
from app.skills.registry import SkillRegistry
from app.webhook.rate_limiter import RateLimiter
from app.whatsapp.client import WhatsAppClient

TEST_SETTINGS = Settings(
    whatsapp_access_token="test_token",
    whatsapp_phone_number_id="123456",
    whatsapp_verify_token="my_verify_token",
    whatsapp_app_secret="test_secret",
    allowed_phone_numbers=["5491112345678"],
    ollama_base_url="http://localhost:11434",
    ollama_model="test-model",
    database_path=":memory:",
)


@pytest.fixture
def settings() -> Settings:
    return TEST_SETTINGS


# --- Async fixtures for unit tests ---


@pytest.fixture
async def db_connection():
    conn, _vec = await init_db(":memory:")
    yield conn
    await conn.close()


@pytest.fixture
async def repository(db_connection):
    return Repository(db_connection)


@pytest.fixture
def memory_file(tmp_path):
    return MemoryFile(path=str(tmp_path / "MEMORY.md"))


@pytest.fixture
def command_registry():
    registry = CommandRegistry()
    register_builtins(registry)
    return registry


@pytest.fixture
async def conversation_manager(repository) -> ConversationManager:
    return ConversationManager(repository=repository, max_messages=20)


# --- Sync fixture for TestClient-based integration tests ---


@pytest.fixture
def client(settings: Settings) -> TestClient:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "message": {"role": "assistant", "content": "Mock reply"}
    }

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_response)
    mock_http.get = AsyncMock()

    # Create DB connection for TestClient tests
    tmp_dir = tempfile.mkdtemp()
    db_path = str(Path(tmp_dir) / "test.db")

    conn, _vec = asyncio.run(init_db(db_path))
    repository = Repository(conn)
    memory_path = str(Path(tmp_dir) / "MEMORY.md")
    memory_file = MemoryFile(path=memory_path)
    command_registry = CommandRegistry()
    register_builtins(command_registry)

    app.state.settings = settings
    app.state.http_client = mock_http
    app.state.whatsapp_client = WhatsAppClient(
        http_client=mock_http,
        access_token=settings.whatsapp_access_token,
        phone_number_id=settings.whatsapp_phone_number_id,
    )
    app.state.ollama_client = OllamaClient(
        http_client=mock_http,
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
    app.state.rate_limiter = RateLimiter(
        max_requests=settings.rate_limit_max,
        window_seconds=settings.rate_limit_window,
    )

    mock_transcriber = MagicMock()
    mock_transcriber.transcribe_async = AsyncMock(return_value="Transcribed text")
    app.state.transcriber = mock_transcriber

    app.state.skill_registry = SkillRegistry(skills_dir="/nonexistent")
    app.state.mcp_manager = None
    app.state.daily_log = DailyLog(memory_dir=str(Path(tmp_dir) / "memory"))
    app.state.vec_available = False

    yield TestClient(app, raise_server_exceptions=False)

    # Teardown: stop the aiosqlite worker thread to prevent process hang.
    # aiosqlite 0.22+ uses a non-daemon Thread; without closing it, pytest
    # hangs waiting for the thread after all tests complete.
    conn.stop()


def make_whatsapp_payload(
    from_number: str = "5491112345678",
    message_id: str = "wamid.test123",
    text: str = "Hello!",
    msg_type: str = "text",
    media_id: str | None = None,
    caption: str | None = None,
    reply_to: str | None = None,
) -> dict:
    msg: dict = {
        "from": from_number,
        "id": message_id,
        "timestamp": "1700000000",
        "type": msg_type,
    }
    if reply_to:
        msg["context"] = {"id": reply_to}
    if msg_type == "text":
        msg["text"] = {"body": text}
    elif msg_type == "audio":
        msg["audio"] = {"id": media_id or "audio_media_id", "mime_type": "audio/ogg"}
    elif msg_type == "image":
        img: dict = {"id": media_id or "image_media_id", "mime_type": "image/jpeg"}
        if caption:
            img["caption"] = caption
        msg["image"] = img

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "BIZ_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "1234567890",
                                "phone_number_id": "123456",
                            },
                            "messages": [msg],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def sign_payload(payload_bytes: bytes, secret: str = "test_secret") -> str:
    sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"
