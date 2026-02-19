"""Tests for MEMORY.md bidirectional watcher (6D)."""
import pytest

from app.database.db import init_db
from app.database.repository import Repository
from app.memory.markdown import MemoryFile
from app.memory.watcher import parse_memory_file, MemoryWatcher


def test_parse_memory_file_basic():
    content = """# Memories

- User likes Python
- [hobby] Plays guitar
- [food] Loves pizza
"""
    result = parse_memory_file(content)
    assert len(result) == 3
    assert result[0] == ("User likes Python", None)
    assert result[1] == ("Plays guitar", "hobby")
    assert result[2] == ("Loves pizza", "food")


def test_parse_memory_file_empty():
    assert parse_memory_file("") == []
    assert parse_memory_file("# Memories\n") == []


def test_parse_memory_file_ignores_non_list_lines():
    content = """# Memories

Some random text
- Valid memory
## Subtitle
- Another valid one
"""
    result = parse_memory_file(content)
    assert len(result) == 2


@pytest.fixture
async def watcher_setup(tmp_path):
    conn, _vec = await init_db(":memory:")
    repo = Repository(conn)
    mf = MemoryFile(path=str(tmp_path / "MEMORY.md"))
    yield repo, mf, tmp_path
    await conn.close()


async def test_sync_from_file_adds_new_memories(watcher_setup):
    repo, mf, tmp_path = watcher_setup
    import asyncio
    loop = asyncio.get_event_loop()
    watcher = MemoryWatcher(memory_file=mf, repository=repo, loop=loop)

    # Write a memory file manually
    (tmp_path / "MEMORY.md").write_text(
        "# Memories\n\n- New memory from file\n- [cat] Categorized memory\n",
        encoding="utf-8",
    )

    await watcher._sync_from_file()

    memories = await repo.list_memories()
    contents = [m.content for m in memories]
    assert "New memory from file" in contents
    assert "Categorized memory" in contents


async def test_sync_from_file_removes_deleted_memories(watcher_setup):
    repo, mf, tmp_path = watcher_setup
    import asyncio
    loop = asyncio.get_event_loop()
    watcher = MemoryWatcher(memory_file=mf, repository=repo, loop=loop)

    # Add memories via DB
    await repo.add_memory("Keep this")
    await repo.add_memory("Remove this")

    # Write file without "Remove this"
    (tmp_path / "MEMORY.md").write_text(
        "# Memories\n\n- Keep this\n",
        encoding="utf-8",
    )

    await watcher._sync_from_file()

    memories = await repo.list_memories()
    contents = [m.content for m in memories]
    assert "Keep this" in contents
    assert "Remove this" not in contents


async def test_sync_guard_prevents_loop(watcher_setup):
    repo, mf, tmp_path = watcher_setup
    import asyncio
    loop = asyncio.get_event_loop()
    watcher = MemoryWatcher(memory_file=mf, repository=repo, loop=loop)

    # Set guard
    watcher.set_sync_guard()

    # Write a file
    (tmp_path / "MEMORY.md").write_text(
        "# Memories\n\n- Should not sync\n",
        encoding="utf-8",
    )

    # _on_file_changed should skip when guard is set
    watcher._on_file_changed()
    # No memories should have been added (sync was skipped)
    memories = await repo.list_memories()
    assert len(memories) == 0

    watcher.clear_sync_guard()


async def test_memory_file_sync_with_watcher(watcher_setup):
    repo, mf, tmp_path = watcher_setup
    import asyncio
    loop = asyncio.get_event_loop()
    watcher = MemoryWatcher(memory_file=mf, repository=repo, loop=loop)
    mf.set_watcher(watcher)

    await repo.add_memory("Test memory")
    memories = await repo.list_memories()
    await mf.sync(memories)

    # File should exist and contain the memory
    content = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "Test memory" in content

    # Guard should be cleared after sync
    assert not watcher._syncing.is_set()
