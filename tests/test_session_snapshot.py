from unittest.mock import AsyncMock

from app.commands.builtins import cmd_clear
from app.commands.context import CommandContext
from app.llm.client import ChatResponse
from app.memory.daily_log import DailyLog
from app.memory.markdown import MemoryFile


async def test_clear_saves_snapshot(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    conv_id = await repository.get_or_create_conversation("5491112345678")
    for i in range(5):
        role = "user" if i % 2 == 0 else "assistant"
        await repository.save_message(conv_id, role, f"Message {i}")

    ollama = AsyncMock()
    ollama.chat_with_tools = AsyncMock(return_value=ChatResponse(content="docker-migration-plan"))

    ctx = CommandContext(
        repository=repository,
        memory_file=memory_file,
        phone_number="5491112345678",
        ollama_client=ollama,
        daily_log=daily_log,
    )

    result = await cmd_clear("", ctx)
    assert "cleared" in result.lower()

    # Snapshot should exist
    snapshots_dir = tmp_path / "memory" / "snapshots"
    assert snapshots_dir.exists()
    snapshot_files = list(snapshots_dir.glob("*.md"))
    assert len(snapshot_files) == 1
    content = snapshot_files[0].read_text()
    assert "docker-migration-plan" in content
    assert "Message 0" in content

    # Daily log should have an entry about the session clear
    log_content = await daily_log.load_recent(days=1)
    assert log_content is not None
    assert "Session cleared" in log_content


async def test_clear_without_ollama_still_works(repository, tmp_path):
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    conv_id = await repository.get_or_create_conversation("5491112345678")
    await repository.save_message(conv_id, "user", "Hello")

    ctx = CommandContext(
        repository=repository,
        memory_file=memory_file,
        phone_number="5491112345678",
    )

    result = await cmd_clear("", ctx)
    assert "cleared" in result.lower()

    # Messages should be cleared
    messages = await repository.get_recent_messages(conv_id, 100)
    assert len(messages) == 0


async def test_clear_snapshot_fallback_slug_on_llm_error(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    conv_id = await repository.get_or_create_conversation("5491112345678")
    await repository.save_message(conv_id, "user", "Hello")
    await repository.save_message(conv_id, "assistant", "Hi there")

    ollama = AsyncMock()
    ollama.chat_with_tools = AsyncMock(side_effect=Exception("LLM down"))

    ctx = CommandContext(
        repository=repository,
        memory_file=memory_file,
        phone_number="5491112345678",
        ollama_client=ollama,
        daily_log=daily_log,
    )

    result = await cmd_clear("", ctx)
    assert "cleared" in result.lower()

    # Snapshot should still be saved with timestamp-based slug
    snapshots_dir = tmp_path / "memory" / "snapshots"
    snapshot_files = list(snapshots_dir.glob("*.md"))
    assert len(snapshot_files) == 1


async def test_clear_empty_conversation_no_snapshot(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    await repository.get_or_create_conversation("5491112345678")

    ollama = AsyncMock()

    ctx = CommandContext(
        repository=repository,
        memory_file=memory_file,
        phone_number="5491112345678",
        ollama_client=ollama,
        daily_log=daily_log,
    )

    result = await cmd_clear("", ctx)
    assert "cleared" in result.lower()

    # No snapshot should be created for empty conversation
    snapshots_dir = tmp_path / "memory" / "snapshots"
    assert not snapshots_dir.exists() or len(list(snapshots_dir.glob("*.md"))) == 0

    # LLM should not have been called
    ollama.chat_with_tools.assert_not_called()


async def test_clear_snapshot_filters_system_messages(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    conv_id = await repository.get_or_create_conversation("5491112345678")
    await repository.save_message(conv_id, "system", "System prompt")
    await repository.save_message(conv_id, "user", "Hello")
    await repository.save_message(conv_id, "assistant", "Hi!")

    ollama = AsyncMock()
    ollama.chat_with_tools = AsyncMock(return_value=ChatResponse(content="greeting-chat"))

    ctx = CommandContext(
        repository=repository,
        memory_file=memory_file,
        phone_number="5491112345678",
        ollama_client=ollama,
        daily_log=daily_log,
    )

    await cmd_clear("", ctx)

    snapshots_dir = tmp_path / "memory" / "snapshots"
    snapshot_files = list(snapshots_dir.glob("*.md"))
    assert len(snapshot_files) == 1
    content = snapshot_files[0].read_text()
    # System messages should not appear
    assert "System prompt" not in content
    assert "Hello" in content
    assert "Hi!" in content
