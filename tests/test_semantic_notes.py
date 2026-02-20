"""Tests for semantic notes search (6E)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.db import init_db
from app.database.repository import Repository
from app.llm.client import OllamaClient
from app.models import Note
from app.webhook.router import _get_relevant_notes


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
    return OllamaClient(
        http_client=mock_http,
        base_url="http://localhost:11434",
        model="test-model",
    )


async def test_get_relevant_notes_returns_semantic_results(vec_repo):
    repo, vec_available = vec_repo
    note_id = await repo.save_note("Python tips", "Use list comprehensions")
    await repo.save_note_embedding(note_id, [0.5] * 768)

    settings = MagicMock()
    settings.semantic_search_enabled = True

    notes = await _get_relevant_notes(
        [0.5] * 768,
        settings,
        repo,
        vec_available,
    )
    assert len(notes) == 1
    assert notes[0].title == "Python tips"


async def test_get_relevant_notes_empty_without_embedding(vec_repo):
    repo, vec_available = vec_repo

    settings = MagicMock()
    settings.semantic_search_enabled = True

    notes = await _get_relevant_notes(
        None,
        settings,
        repo,
        vec_available,
    )
    assert notes == []


async def test_get_relevant_notes_empty_when_disabled(vec_repo):
    repo, vec_available = vec_repo
    note_id = await repo.save_note("Note", "Content")
    await repo.save_note_embedding(note_id, [0.5] * 768)

    settings = MagicMock()
    settings.semantic_search_enabled = False

    notes = await _get_relevant_notes(
        [0.5] * 768,
        settings,
        repo,
        vec_available,
    )
    assert notes == []


async def test_conversation_manager_includes_notes():
    """Test that get_context includes relevant_notes in output."""
    from app.conversation.manager import ConversationManager

    conn, _ = await init_db(":memory:")
    repo = Repository(conn)
    cm = ConversationManager(repository=repo, max_messages=20)

    notes = [Note(id=1, title="Test", content="test content")]
    context = await cm.get_context(
        "5491112345678",
        "System prompt",
        [],
        relevant_notes=notes,
    )

    # Find the notes block
    notes_msg = [m for m in context if "Relevant notes" in m.content]
    assert len(notes_msg) == 1
    assert "Test" in notes_msg[0].content
    assert "test content" in notes_msg[0].content

    await conn.close()
