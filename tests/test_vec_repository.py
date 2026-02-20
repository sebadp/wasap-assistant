"""Tests for sqlite-vec repository methods."""
import pytest

from app.database.db import init_db
from app.database.repository import Repository


@pytest.fixture
async def vec_db():
    """DB with sqlite-vec loaded."""
    conn, vec_available = await init_db(":memory:")
    if not vec_available:
        pytest.skip("sqlite-vec not available")
    yield conn, vec_available
    await conn.close()


@pytest.fixture
async def vec_repo(vec_db):
    conn, _ = vec_db
    return Repository(conn)


async def test_save_and_search_memory_embedding(vec_repo):
    # Add a memory
    mem_id = await vec_repo.add_memory("User likes Python")

    # Save embedding
    embedding = [0.1] * 768
    await vec_repo.save_embedding(mem_id, embedding)

    # Search
    query_emb = [0.1] * 768
    results = await vec_repo.search_similar_memories(query_emb, top_k=5)
    assert len(results) == 1
    assert results[0] == "User likes Python"


async def test_delete_embedding(vec_repo):
    mem_id = await vec_repo.add_memory("Temporary memory")
    await vec_repo.save_embedding(mem_id, [0.5] * 768)

    # Verify it's searchable
    results = await vec_repo.search_similar_memories([0.5] * 768, top_k=5)
    assert len(results) == 1

    # Delete embedding
    await vec_repo.delete_embedding(mem_id)
    results = await vec_repo.search_similar_memories([0.5] * 768, top_k=5)
    assert len(results) == 0


async def test_search_excludes_inactive_memories(vec_repo):
    mem_id = await vec_repo.add_memory("Active memory")
    await vec_repo.save_embedding(mem_id, [0.3] * 768)

    # Deactivate memory
    await vec_repo.remove_memory("Active memory")

    # Search should not return inactive memory
    results = await vec_repo.search_similar_memories([0.3] * 768, top_k=5)
    assert len(results) == 0


async def test_get_unembedded_memories(vec_repo):
    id1 = await vec_repo.add_memory("Memory 1")
    id2 = await vec_repo.add_memory("Memory 2")
    await vec_repo.save_embedding(id1, [0.1] * 768)

    unembedded = await vec_repo.get_unembedded_memories()
    assert len(unembedded) == 1
    assert unembedded[0] == (id2, "Memory 2")


async def test_remove_memory_return_id(vec_repo):
    mem_id = await vec_repo.add_memory("To forget")
    returned_id = await vec_repo.remove_memory_return_id("To forget")
    assert returned_id == mem_id

    # Not found
    result = await vec_repo.remove_memory_return_id("Nonexistent")
    assert result is None


async def test_note_embedding_crud(vec_repo):
    note_id = await vec_repo.save_note("Title", "Content")
    await vec_repo.save_note_embedding(note_id, [0.2] * 768)

    results = await vec_repo.search_similar_notes([0.2] * 768, top_k=5)
    assert len(results) == 1
    assert results[0].title == "Title"

    await vec_repo.delete_note_embedding(note_id)
    results = await vec_repo.search_similar_notes([0.2] * 768, top_k=5)
    assert len(results) == 0


async def test_get_unembedded_notes(vec_repo):
    id1 = await vec_repo.save_note("Note 1", "Content 1")
    id2 = await vec_repo.save_note("Note 2", "Content 2")
    await vec_repo.save_note_embedding(id1, [0.1] * 768)

    unembedded = await vec_repo.get_unembedded_notes()
    assert len(unembedded) == 1
    assert unembedded[0] == (id2, "Note 2", "Content 2")


async def test_init_db_returns_vec_available():
    conn, vec_available = await init_db(":memory:")
    if not vec_available:
        await conn.close()
        pytest.skip("sqlite-vec not available in this environment")
    assert vec_available is True
    await conn.close()
