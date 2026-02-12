async def test_add_and_get_history(conversation_manager):
    await conversation_manager.add_message("123", "user", "hello")
    await conversation_manager.add_message("123", "assistant", "hi")

    history = await conversation_manager.get_history("123")
    assert len(history) == 2
    assert history[0].content == "hello"
    assert history[1].content == "hi"


async def test_trimming(repository):
    from app.conversation.manager import ConversationManager

    mgr = ConversationManager(repository=repository, max_messages=3)
    for i in range(5):
        await mgr.add_message("123", "user", f"msg{i}")

    history = await mgr.get_history("123")
    assert len(history) == 3
    assert history[0].content == "msg2"
    assert history[2].content == "msg4"


async def test_separate_conversations(conversation_manager):
    await conversation_manager.add_message("111", "user", "a")
    await conversation_manager.add_message("222", "user", "b")

    history_111 = await conversation_manager.get_history("111")
    history_222 = await conversation_manager.get_history("222")
    assert len(history_111) == 1
    assert len(history_222) == 1
    assert history_111[0].content == "a"


async def test_clear(conversation_manager):
    await conversation_manager.add_message("123", "user", "hello")
    await conversation_manager.clear("123")
    assert await conversation_manager.get_history("123") == []


async def test_empty_history(conversation_manager):
    assert await conversation_manager.get_history("nonexistent") == []


async def test_duplicate_detection(conversation_manager):
    # First message saves to DB — not a duplicate
    await conversation_manager.add_message("123", "user", "msg1", wa_message_id="wamid.1")
    assert await conversation_manager.is_duplicate("wamid.1") is True
    assert await conversation_manager.is_duplicate("wamid.2") is False


async def test_get_context_with_memories(conversation_manager, repository):
    await conversation_manager.add_message("123", "user", "hello")
    await repository.add_memory("Birthday is March 15")

    memories = await repository.get_active_memories()
    context = await conversation_manager.get_context("123", "You are helpful.", memories)

    assert context[0].role == "system"
    assert context[0].content == "You are helpful."
    assert context[1].role == "system"
    assert "Birthday is March 15" in context[1].content
    assert context[2].role == "user"
    assert context[2].content == "hello"


async def test_get_context_with_summary(conversation_manager, repository):
    conv_id = await conversation_manager.get_conversation_id("123")
    await repository.save_summary(conv_id, "We discussed weather.", 10)
    await conversation_manager.add_message("123", "user", "hello")

    context = await conversation_manager.get_context("123", "You are helpful.", [])

    assert context[0].role == "system"
    assert context[1].role == "system"
    assert "We discussed weather." in context[1].content
    assert context[2].role == "user"
