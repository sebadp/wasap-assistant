import json
from unittest.mock import AsyncMock

from app.memory.consolidator import consolidate_memories
from app.memory.markdown import MemoryFile


async def test_consolidate_skips_below_minimum(repository, tmp_path):
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    # Add fewer than minimum memories
    for i in range(5):
        await repository.add_memory(f"Fact {i}")

    ollama = AsyncMock()
    result = await consolidate_memories(repository, ollama, memory_file, min_memories=8)

    assert result == 0
    ollama.chat.assert_not_called()


async def test_consolidate_removes_duplicates(repository, tmp_path):
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    ids = []
    for i in range(10):
        mid = await repository.add_memory(f"Fact {i}")
        ids.append(mid)

    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value=json.dumps({
        "remove_ids": [ids[2], ids[5]],
    }))

    result = await consolidate_memories(repository, ollama, memory_file, min_memories=8)

    assert result == 2
    remaining = await repository.get_active_memories()
    assert len(remaining) == 8
    assert "Fact 2" not in remaining
    assert "Fact 5" not in remaining

    # MEMORY.md should be synced
    assert (tmp_path / "MEMORY.md").exists()


async def test_consolidate_nothing_to_remove(repository, tmp_path):
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    for i in range(10):
        await repository.add_memory(f"Unique fact {i}")

    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value=json.dumps({"remove_ids": []}))

    result = await consolidate_memories(repository, ollama, memory_file, min_memories=8)

    assert result == 0
    remaining = await repository.get_active_memories()
    assert len(remaining) == 10


async def test_consolidate_ignores_invalid_ids(repository, tmp_path):
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    for i in range(10):
        await repository.add_memory(f"Fact {i}")

    ollama = AsyncMock()
    # Include IDs that don't exist
    ollama.chat = AsyncMock(return_value=json.dumps({
        "remove_ids": [9999, "not_an_id", -1],
    }))

    result = await consolidate_memories(repository, ollama, memory_file, min_memories=8)

    assert result == 0
    remaining = await repository.get_active_memories()
    assert len(remaining) == 10


async def test_consolidate_handles_invalid_json(repository, tmp_path):
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    for i in range(10):
        await repository.add_memory(f"Fact {i}")

    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value="This is not JSON at all")

    result = await consolidate_memories(repository, ollama, memory_file, min_memories=8)

    assert result == 0


async def test_consolidate_handles_code_fenced_json(repository, tmp_path):
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    ids = []
    for i in range(10):
        mid = await repository.add_memory(f"Fact {i}")
        ids.append(mid)

    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value=f'```json\n{{"remove_ids": [{ids[0]}]}}\n```')

    result = await consolidate_memories(repository, ollama, memory_file, min_memories=8)

    assert result == 1
    remaining = await repository.get_active_memories()
    assert "Fact 0" not in remaining
