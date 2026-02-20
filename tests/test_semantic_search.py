"""Tests for semantic memory search integration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.db import init_db
from app.database.repository import Repository
from app.embeddings.indexer import backfill_embeddings, embed_memory
from app.llm.client import OllamaClient
from app.webhook.router import _get_memories


@pytest.fixture
async def vec_repo():
    conn, vec_available = await init_db(":memory:")
    if not vec_available:
        pytest.skip("sqlite-vec not available")
    yield Repository(conn), vec_available
    await conn.close()


@pytest.fixture
def mock_ollama():
    mock_http = AsyncMock()
    client = OllamaClient(
        http_client=mock_http,
        base_url="http://localhost:11434",
        model="test-model",
    )
    return client


def _make_embed_response(vectors):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"embeddings": vectors}
    return resp


async def test_embed_memory_and_search(vec_repo, mock_ollama):
    repo, _ = vec_repo
    mem_id = await repo.add_memory("User loves Python")

    # Mock embed for indexing
    mock_ollama._http.post = AsyncMock(return_value=_make_embed_response([[0.1] * 768]))
    await embed_memory(mem_id, "User loves Python", repo, mock_ollama, "nomic-embed-text")

    # Search with similar embedding
    mock_ollama._http.post = AsyncMock(return_value=_make_embed_response([[0.1] * 768]))
    results = await repo.search_similar_memories([0.1] * 768, top_k=5)
    assert "User loves Python" in results


async def test_backfill_embeddings(vec_repo, mock_ollama):
    repo, _ = vec_repo
    await repo.add_memory("Fact 1")
    await repo.add_memory("Fact 2")
    await repo.add_memory("Fact 3")

    mock_ollama._http.post = AsyncMock(
        return_value=_make_embed_response([[0.1] * 768, [0.2] * 768, [0.3] * 768])
    )

    count = await backfill_embeddings(repo, mock_ollama, "nomic-embed-text")
    assert count == 3

    # All should now be embedded
    unembedded = await repo.get_unembedded_memories()
    assert len(unembedded) == 0


async def test_get_memories_semantic(vec_repo, mock_ollama):
    repo, vec_available = vec_repo

    # Add memories and embed them
    mem_id = await repo.add_memory("Python programming")
    await repo.save_embedding(mem_id, [0.5] * 768)

    # Mock settings
    settings = MagicMock()
    settings.semantic_search_enabled = True
    settings.embedding_model = "nomic-embed-text"
    settings.semantic_search_top_k = 10

    # Mock embed for query
    mock_ollama._http.post = AsyncMock(return_value=_make_embed_response([[0.5] * 768]))

    results = await _get_memories(
        "Tell me about programming",
        settings,
        mock_ollama,
        repo,
        vec_available,
    )
    assert "Python programming" in results


async def test_get_memories_fallback_when_disabled(vec_repo, mock_ollama):
    repo, vec_available = vec_repo
    await repo.add_memory("All memories returned")

    settings = MagicMock()
    settings.semantic_search_enabled = False
    settings.semantic_search_top_k = 10

    results = await _get_memories(
        "query",
        settings,
        mock_ollama,
        repo,
        vec_available,
    )
    assert "All memories returned" in results


async def test_get_memories_fallback_on_embed_error(vec_repo, mock_ollama):
    repo, vec_available = vec_repo
    await repo.add_memory("Fallback memory")

    settings = MagicMock()
    settings.semantic_search_enabled = True
    settings.embedding_model = "nomic-embed-text"
    settings.semantic_search_top_k = 10  # must be int; MagicMock can't be bound as SQLite param

    # Simulate embed failure
    mock_ollama._http.post = AsyncMock(side_effect=Exception("embed failed"))

    results = await _get_memories(
        "query",
        settings,
        mock_ollama,
        repo,
        vec_available,
    )
    assert "Fallback memory" in results
