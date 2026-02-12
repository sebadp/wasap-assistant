from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.llm.client import OllamaClient
from app.models import ChatMessage


@pytest.fixture
def ollama_client() -> OllamaClient:
    mock_http = AsyncMock()
    return OllamaClient(
        http_client=mock_http,
        base_url="http://localhost:11434",
        model="test-model",
    )


@pytest.mark.asyncio
async def test_chat(ollama_client):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "message": {"role": "assistant", "content": "Hello there!"}
    }
    ollama_client._http.post = AsyncMock(return_value=mock_response)

    messages = [ChatMessage(role="user", content="Hi")]
    result = await ollama_client.chat(messages)

    assert result == "Hello there!"
    ollama_client._http.post.assert_called_once()
    call_kwargs = ollama_client._http.post.call_args
    payload = call_kwargs.kwargs["json"]
    assert payload["model"] == "test-model"
    assert payload["stream"] is False


@pytest.mark.asyncio
async def test_is_available_success(ollama_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    ollama_client._http.get = AsyncMock(return_value=mock_response)

    assert await ollama_client.is_available() is True


@pytest.mark.asyncio
async def test_is_available_failure(ollama_client):
    ollama_client._http.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    assert await ollama_client.is_available() is False
