import json
from unittest.mock import AsyncMock

from app.conversation.summarizer import (
    _is_duplicate,
    flush_to_memory,
    maybe_summarize,
)
from app.memory.daily_log import DailyLog
from app.memory.markdown import MemoryFile
from app.models import ChatMessage


def test_is_duplicate_exact_match():
    assert _is_duplicate("user likes pizza", ["user likes pizza"])


def test_is_duplicate_similar():
    assert _is_duplicate("user likes pizza", ["User likes pizza"])


def test_is_duplicate_different():
    assert not _is_duplicate("user likes pizza", ["the weather is cold today"])


def test_is_duplicate_empty_existing():
    assert not _is_duplicate("user likes pizza", [])


async def test_flush_extracts_facts_and_events(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    ollama = AsyncMock()
    ollama.chat = AsyncMock(
        return_value=json.dumps(
            {
                "facts": ["User prefers dark mode", "User's name is Carlos"],
                "events": ["Discussed migration to Postgres"],
            }
        )
    )

    old_messages = [
        ChatMessage(role="user", content="I prefer dark mode"),
        ChatMessage(role="assistant", content="Got it, dark mode preference noted"),
        ChatMessage(role="user", content="My name is Carlos"),
        ChatMessage(role="assistant", content="Nice to meet you Carlos"),
    ]

    count = await flush_to_memory(old_messages, repository, ollama, daily_log, memory_file)

    assert count == 2
    memories = await repository.get_active_memories()
    assert "User prefers dark mode" in memories
    assert "User's name is Carlos" in memories

    # Check daily log was written
    log_content = await daily_log.load_recent(days=1)
    assert log_content is not None
    assert "Discussed migration to Postgres" in log_content

    # Check MEMORY.md was synced
    assert (tmp_path / "MEMORY.md").exists()


async def test_flush_deduplicates_facts(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    # Pre-existing memory
    await repository.add_memory("User prefers dark mode")

    ollama = AsyncMock()
    ollama.chat = AsyncMock(
        return_value=json.dumps(
            {
                "facts": ["User prefers dark mode", "User speaks Spanish"],
                "events": [],
            }
        )
    )

    old_messages = [ChatMessage(role="user", content="test")]
    count = await flush_to_memory(old_messages, repository, ollama, daily_log, memory_file)

    # Only the non-duplicate should be added
    assert count == 1
    memories = await repository.get_active_memories()
    assert len(memories) == 2
    assert "User speaks Spanish" in memories


async def test_flush_handles_empty_response(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    ollama = AsyncMock()
    ollama.chat = AsyncMock(
        return_value=json.dumps(
            {
                "facts": [],
                "events": [],
            }
        )
    )

    old_messages = [ChatMessage(role="user", content="Hello")]
    count = await flush_to_memory(old_messages, repository, ollama, daily_log, memory_file)

    assert count == 0


async def test_flush_handles_invalid_json(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value="This is not JSON")

    old_messages = [ChatMessage(role="user", content="Hello")]
    count = await flush_to_memory(old_messages, repository, ollama, daily_log, memory_file)

    assert count == 0


async def test_flush_handles_code_fenced_json(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value='```json\n{"facts": ["Likes cats"], "events": []}\n```')

    old_messages = [ChatMessage(role="user", content="I love cats")]
    count = await flush_to_memory(old_messages, repository, ollama, daily_log, memory_file)

    assert count == 1
    memories = await repository.get_active_memories()
    assert "Likes cats" in memories


async def test_flush_skips_non_string_facts(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    ollama = AsyncMock()
    ollama.chat = AsyncMock(
        return_value=json.dumps(
            {
                "facts": ["Valid fact", 123, None, "", "Another valid"],
                "events": [42, "Valid event"],
            }
        )
    )

    old_messages = [ChatMessage(role="user", content="test")]
    count = await flush_to_memory(old_messages, repository, ollama, daily_log, memory_file)

    assert count == 2
    memories = await repository.get_active_memories()
    assert "Valid fact" in memories
    assert "Another valid" in memories


async def test_maybe_summarize_with_flush(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    conv_id = await repository.get_or_create_conversation("123")
    for i in range(10):
        await repository.save_message(conv_id, "user", f"msg{i}")

    ollama = AsyncMock()
    # First call: flush_to_memory, second call: summarize
    ollama.chat = AsyncMock(
        side_effect=[
            json.dumps({"facts": ["Extracted fact"], "events": ["Some event"]}),
            "Summary of conversation.",
        ]
    )

    await maybe_summarize(
        conv_id,
        repository,
        ollama,
        threshold=5,
        max_messages=3,
        daily_log=daily_log,
        memory_file=memory_file,
        flush_enabled=True,
    )

    # Flush should have extracted the fact
    memories = await repository.get_active_memories()
    assert "Extracted fact" in memories

    # Summary should still work
    summary = await repository.get_latest_summary(conv_id)
    assert summary == "Summary of conversation."

    # Old messages should be deleted
    messages = await repository.get_recent_messages(conv_id, 100)
    assert len(messages) == 3


async def test_maybe_summarize_flush_disabled(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    conv_id = await repository.get_or_create_conversation("123")
    for i in range(10):
        await repository.save_message(conv_id, "user", f"msg{i}")

    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value="Summary.")

    await maybe_summarize(
        conv_id,
        repository,
        ollama,
        threshold=5,
        max_messages=3,
        daily_log=daily_log,
        memory_file=memory_file,
        flush_enabled=False,
    )

    # Only one call (summarize), no flush
    ollama.chat.assert_called_once()


async def test_maybe_summarize_flush_error_does_not_block_summarize(repository, tmp_path):
    daily_log = DailyLog(memory_dir=str(tmp_path / "memory"))
    memory_file = MemoryFile(path=str(tmp_path / "MEMORY.md"))

    conv_id = await repository.get_or_create_conversation("123")
    for i in range(10):
        await repository.save_message(conv_id, "user", f"msg{i}")

    ollama = AsyncMock()
    # First call (flush) fails, second call (summarize) works
    ollama.chat = AsyncMock(
        side_effect=[
            Exception("LLM down"),
            "Summary despite flush failure.",
        ]
    )

    await maybe_summarize(
        conv_id,
        repository,
        ollama,
        threshold=5,
        max_messages=3,
        daily_log=daily_log,
        memory_file=memory_file,
        flush_enabled=True,
    )

    # Summary should still be saved
    summary = await repository.get_latest_summary(conv_id)
    assert summary == "Summary despite flush failure."
