"""Tests for OllamaClient.embed() and sqlite-vec setup."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.llm.client import OllamaClient


@pytest.fixture
def ollama_client():
    mock_http = AsyncMock()
    return OllamaClient(
        http_client=mock_http,
        base_url="http://localhost:11434",
        model="test-model",
    )


async def test_embed_returns_vectors(ollama_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"embeddings": [[0.1] * 768, [0.2] * 768]}
    ollama_client._http.post = AsyncMock(return_value=mock_response)

    result = await ollama_client.embed(["hello", "world"], model="nomic-embed-text")

    assert len(result) == 2
    assert len(result[0]) == 768
    ollama_client._http.post.assert_awaited_once()
    call_args = ollama_client._http.post.call_args
    assert call_args[1]["json"]["model"] == "nomic-embed-text"
    assert call_args[1]["json"]["input"] == ["hello", "world"]


async def test_embed_uses_default_model(ollama_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"embeddings": [[0.5] * 768]}
    ollama_client._http.post = AsyncMock(return_value=mock_response)

    await ollama_client.embed(["test"])

    call_args = ollama_client._http.post.call_args
    assert call_args[1]["json"]["model"] == "test-model"
