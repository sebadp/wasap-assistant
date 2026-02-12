import pytest


async def test_get_or_create_conversation(repository):
    conv_id = await repository.get_or_create_conversation("5491112345678")
    assert conv_id is not None
    # Idempotent
    same_id = await repository.get_or_create_conversation("5491112345678")
    assert same_id == conv_id


async def test_different_numbers_different_conversations(repository):
    id1 = await repository.get_or_create_conversation("111")
    id2 = await repository.get_or_create_conversation("222")
    assert id1 != id2


async def test_save_and_get_messages(repository):
    conv_id = await repository.get_or_create_conversation("123")
    await repository.save_message(conv_id, "user", "hello")
    await repository.save_message(conv_id, "assistant", "hi there")

    messages = await repository.get_recent_messages(conv_id, 10)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "hello"
    assert messages[1].role == "assistant"
    assert messages[1].content == "hi there"


async def test_get_recent_messages_limit(repository):
    conv_id = await repository.get_or_create_conversation("123")
    for i in range(5):
        await repository.save_message(conv_id, "user", f"msg{i}")

    messages = await repository.get_recent_messages(conv_id, 3)
    assert len(messages) == 3
    assert messages[0].content == "msg2"
    assert messages[2].content == "msg4"


async def test_get_message_count(repository):
    conv_id = await repository.get_or_create_conversation("123")
    assert await repository.get_message_count(conv_id) == 0
    await repository.save_message(conv_id, "user", "hello")
    await repository.save_message(conv_id, "assistant", "hi")
    assert await repository.get_message_count(conv_id) == 2


async def test_is_duplicate(repository):
    conv_id = await repository.get_or_create_conversation("123")
    assert await repository.is_duplicate("wamid.1") is False
    await repository.save_message(conv_id, "user", "hello", wa_message_id="wamid.1")
    assert await repository.is_duplicate("wamid.1") is True
    assert await repository.is_duplicate("wamid.2") is False


async def test_clear_conversation(repository):
    conv_id = await repository.get_or_create_conversation("123")
    await repository.save_message(conv_id, "user", "hello")
    await repository.save_message(conv_id, "assistant", "hi")
    await repository.save_summary(conv_id, "summary", 2)

    await repository.clear_conversation(conv_id)

    assert await repository.get_message_count(conv_id) == 0
    assert await repository.get_latest_summary(conv_id) is None


async def test_save_and_get_summary(repository):
    conv_id = await repository.get_or_create_conversation("123")
    assert await repository.get_latest_summary(conv_id) is None

    await repository.save_summary(conv_id, "First summary", 10)
    assert await repository.get_latest_summary(conv_id) == "First summary"

    await repository.save_summary(conv_id, "Second summary", 20)
    assert await repository.get_latest_summary(conv_id) == "Second summary"


async def test_add_memory(repository):
    mem_id = await repository.add_memory("Birthday is March 15")
    assert mem_id is not None

    memories = await repository.list_memories()
    assert len(memories) == 1
    assert memories[0].content == "Birthday is March 15"
    assert memories[0].active is True


async def test_add_memory_with_category(repository):
    await repository.add_memory("Prefers Spanish", category="language")
    memories = await repository.list_memories()
    assert len(memories) == 1
    assert memories[0].category == "language"


async def test_remove_memory(repository):
    await repository.add_memory("Birthday is March 15")
    removed = await repository.remove_memory("Birthday is March 15")
    assert removed is True

    memories = await repository.list_memories()
    assert len(memories) == 0


async def test_remove_nonexistent_memory(repository):
    removed = await repository.remove_memory("does not exist")
    assert removed is False


async def test_get_active_memories(repository):
    await repository.add_memory("Fact 1")
    await repository.add_memory("Fact 2")
    await repository.remove_memory("Fact 1")

    active = await repository.get_active_memories()
    assert active == ["Fact 2"]


async def test_delete_old_messages(repository):
    conv_id = await repository.get_or_create_conversation("123")
    for i in range(10):
        await repository.save_message(conv_id, "user", f"msg{i}")

    deleted = await repository.delete_old_messages(conv_id, keep_last=3)
    assert deleted == 7

    messages = await repository.get_recent_messages(conv_id, 10)
    assert len(messages) == 3
    assert messages[0].content == "msg7"
