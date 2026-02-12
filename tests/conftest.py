import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.conversation.manager import ConversationManager
from app.llm.client import OllamaClient
from app.main import app
from app.whatsapp.client import WhatsAppClient

TEST_SETTINGS = Settings(
    whatsapp_access_token="test_token",
    whatsapp_phone_number_id="123456",
    whatsapp_verify_token="my_verify_token",
    whatsapp_app_secret="test_secret",
    allowed_phone_numbers=["5491112345678"],
    ollama_base_url="http://localhost:11434",
    ollama_model="test-model",
)


@pytest.fixture
def settings() -> Settings:
    return TEST_SETTINGS


@pytest.fixture
def conversation_manager() -> ConversationManager:
    return ConversationManager(max_messages=20)


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
    app.state.conversation_manager = ConversationManager(
        max_messages=settings.conversation_max_messages,
    )

    return TestClient(app, raise_server_exceptions=False)


def make_whatsapp_payload(
    from_number: str = "5491112345678",
    message_id: str = "wamid.test123",
    text: str = "Hello!",
) -> dict:
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
                            "messages": [
                                {
                                    "from": from_number,
                                    "id": message_id,
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
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
