from app.models import Memory


async def test_sync_writes_file(memory_file):
    memories = [
        Memory(id=1, content="Birthday is March 15", created_at="2024-01-01"),
        Memory(id=2, content="Prefers Spanish", created_at="2024-01-02"),
    ]
    await memory_file.sync(memories)

    content = memory_file._path.read_text()
    assert "# Memories" in content
    assert "- Birthday is March 15" in content
    assert "- Prefers Spanish" in content


async def test_sync_empty_memories(memory_file):
    await memory_file.sync([])
    content = memory_file._path.read_text()
    assert "# Memories" in content
    lines = [l for l in content.strip().split("\n") if l.startswith("- ")]
    assert len(lines) == 0


async def test_sync_with_categories(memory_file):
    memories = [
        Memory(id=1, content="data with cat", category="personal", created_at="2024-01-01"),
        Memory(id=2, content="data without cat", created_at="2024-01-02"),
    ]
    await memory_file.sync(memories)

    content = memory_file._path.read_text()
    assert "- [personal] data with cat" in content
    assert "- data without cat" in content


async def test_sync_overwrites_previous(memory_file):
    memories1 = [Memory(id=1, content="old data", created_at="2024-01-01")]
    await memory_file.sync(memories1)

    memories2 = [Memory(id=2, content="new data", created_at="2024-01-02")]
    await memory_file.sync(memories2)

    content = memory_file._path.read_text()
    assert "old data" not in content
    assert "new data" in content
