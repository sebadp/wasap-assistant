"""Tests for auto-indexing lifecycle (6C)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.db import init_db
from app.database.repository import Repository
from app.embeddings.indexer import (
    embed_memory,
    remove_memory_embedding,
    embed_note,
    remove_note_embedding,
    backfill_embeddings,
    backfill_note_embeddings,
)
from app.llm.client import OllamaClient


@pytest.fixture
async def vec_repo():
    conn, vec_available = await init_db(":memory:")
    if not vec_available:
        pytest.skip("sqlite-vec not available")
    yield Repository(conn)
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


def _mock_embed(ollama, vectors):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"embeddings": vectors}
    ollama._http.post = AsyncMock(return_value=resp)


async def test_embed_memory_creates_embedding(vec_repo, mock_ollama):
    mem_id = await vec_repo.add_memory("Test fact")
    _mock_embed(mock_ollama, [[0.5] * 768])

    await embed_memory(mem_id, "Test fact", vec_repo, mock_ollama, "nomic-embed-text")

    # Verify embedding exists by searching
    results = await vec_repo.search_similar_memories([0.5] * 768, top_k=5)
    assert "Test fact" in results


async def test_embed_memory_best_effort_on_failure(vec_repo, mock_ollama):
    mem_id = await vec_repo.add_memory("Test fact")
    mock_ollama._http.post = AsyncMock(side_effect=Exception("Network error"))

    # Should not raise
    await embed_memory(mem_id, "Test fact", vec_repo, mock_ollama, "nomic-embed-text")


async def test_remove_memory_embedding_deletes(vec_repo, mock_ollama):
    mem_id = await vec_repo.add_memory("To remove")
    _mock_embed(mock_ollama, [[0.3] * 768])
    await embed_memory(mem_id, "To remove", vec_repo, mock_ollama, "nomic-embed-text")

    await remove_memory_embedding(mem_id, vec_repo)

    results = await vec_repo.search_similar_memories([0.3] * 768, top_k=5)
    assert len(results) == 0


async def test_embed_note_creates_embedding(vec_repo, mock_ollama):
    note_id = await vec_repo.save_note("Title", "Content")
    _mock_embed(mock_ollama, [[0.4] * 768])

    await embed_note(note_id, "Title: Content", vec_repo, mock_ollama, "nomic-embed-text")

    results = await vec_repo.search_similar_notes([0.4] * 768, top_k=5)
    assert len(results) == 1
    assert results[0].title == "Title"


async def test_remove_note_embedding_deletes(vec_repo, mock_ollama):
    note_id = await vec_repo.save_note("Title", "Content")
    _mock_embed(mock_ollama, [[0.4] * 768])
    await embed_note(note_id, "Title: Content", vec_repo, mock_ollama, "nomic-embed-text")

    await remove_note_embedding(note_id, vec_repo)

    results = await vec_repo.search_similar_notes([0.4] * 768, top_k=5)
    assert len(results) == 0


async def test_backfill_skips_already_embedded(vec_repo, mock_ollama):
    id1 = await vec_repo.add_memory("Already embedded")
    id2 = await vec_repo.add_memory("Not embedded")

    await vec_repo.save_embedding(id1, [0.1] * 768)

    _mock_embed(mock_ollama, [[0.2] * 768])
    count = await backfill_embeddings(vec_repo, mock_ollama, "nomic-embed-text")
    assert count == 1


async def test_backfill_notes(vec_repo, mock_ollama):
    await vec_repo.save_note("Note 1", "Content 1")
    await vec_repo.save_note("Note 2", "Content 2")

    _mock_embed(mock_ollama, [[0.1] * 768, [0.2] * 768])
    count = await backfill_note_embeddings(vec_repo, mock_ollama, "nomic-embed-text")
    assert count == 2
