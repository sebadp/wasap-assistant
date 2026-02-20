from unittest.mock import AsyncMock

from app.conversation.summarizer import maybe_summarize


async def test_no_summarize_below_threshold(repository):
    conv_id = await repository.get_or_create_conversation("123")
    for i in range(5):
        await repository.save_message(conv_id, "user", f"msg{i}")

    ollama = AsyncMock()
    await maybe_summarize(conv_id, repository, ollama, threshold=40, max_messages=20)

    ollama.chat.assert_not_called()


async def test_summarize_above_threshold(repository):
    conv_id = await repository.get_or_create_conversation("123")
    for i in range(10):
        await repository.save_message(conv_id, "user", f"msg{i}")

    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value="Summary of conversation.")

    await maybe_summarize(conv_id, repository, ollama, threshold=5, max_messages=3)

    ollama.chat.assert_called_once()
    summary = await repository.get_latest_summary(conv_id)
    assert summary == "Summary of conversation."

    # Old messages should be deleted, only last 3 kept
    messages = await repository.get_recent_messages(conv_id, 100)
    assert len(messages) == 3
    assert messages[0].content == "msg7"


async def test_summarize_includes_previous_summary(repository):
    conv_id = await repository.get_or_create_conversation("123")
    await repository.save_summary(conv_id, "Previous summary here.", 5)
    for i in range(10):
        await repository.save_message(conv_id, "user", f"msg{i}")

    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value="Updated summary.")

    await maybe_summarize(conv_id, repository, ollama, threshold=5, max_messages=3)

    # Verify previous summary was included in the prompt
    call_args = ollama.chat.call_args[0][0]
    prompt_text = call_args[0].content
    assert "Previous summary here." in prompt_text


async def test_summarize_handles_error(repository):
    conv_id = await repository.get_or_create_conversation("123")
    for i in range(10):
        await repository.save_message(conv_id, "user", f"msg{i}")

    ollama = AsyncMock()
    ollama.chat = AsyncMock(side_effect=Exception("LLM down"))

    # Should not raise
    await maybe_summarize(conv_id, repository, ollama, threshold=5, max_messages=3)

    # Messages should not be deleted if summarization failed
    messages = await repository.get_recent_messages(conv_id, 100)
    assert len(messages) == 10
