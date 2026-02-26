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


# --- Deduplication ---


async def test_try_claim_message_first_time(repository):
    result = await repository.try_claim_message("wamid.new")
    assert result is False  # Not a duplicate


async def test_try_claim_message_duplicate(repository):
    await repository.try_claim_message("wamid.dup")
    result = await repository.try_claim_message("wamid.dup")
    assert result is True  # Duplicate


# --- Reply context ---


async def test_get_message_by_wa_id(repository):
    conv_id = await repository.get_or_create_conversation("123")
    await repository.save_message(conv_id, "user", "Hello!", wa_message_id="wamid.abc")

    msg = await repository.get_message_by_wa_id("wamid.abc")
    assert msg is not None
    assert msg.content == "Hello!"
    assert msg.role == "user"


async def test_get_message_by_wa_id_not_found(repository):
    msg = await repository.get_message_by_wa_id("wamid.nonexistent")
    assert msg is None


# --- Notes ---


async def test_save_and_list_notes(repository):
    note_id = await repository.save_note("Test Title", "Test content")
    assert note_id is not None

    notes = await repository.list_notes()
    assert len(notes) == 1
    assert notes[0].title == "Test Title"
    assert notes[0].content == "Test content"


async def test_search_notes(repository):
    await repository.save_note("Shopping List", "Buy milk and eggs")
    await repository.save_note("Todo", "Fix the bug")

    results = await repository.search_notes("milk")
    assert len(results) == 1
    assert results[0].title == "Shopping List"


async def test_search_notes_by_title(repository):
    await repository.save_note("Shopping List", "Buy stuff")
    await repository.save_note("Work Notes", "Meeting at 3pm")

    results = await repository.search_notes("Shopping")
    assert len(results) == 1
    assert results[0].title == "Shopping List"


async def test_delete_note(repository):
    note_id = await repository.save_note("To Delete", "Will be gone")
    deleted = await repository.delete_note(note_id)
    assert deleted is True

    notes = await repository.list_notes()
    assert len(notes) == 0


async def test_delete_nonexistent_note(repository):
    deleted = await repository.delete_note(999)
    assert deleted is False


async def test_get_note(repository):
    note_id = await repository.save_note("Full Note", "Complete content here")
    note = await repository.get_note(note_id)
    assert note is not None
    assert note.id == note_id
    assert note.title == "Full Note"
    assert note.content == "Complete content here"


async def test_get_note_not_found(repository):
    note = await repository.get_note(999)
    assert note is None


# --- Dashboard queries (Iteración 6) ---


async def _insert_trace(conn, trace_id: str, status: str = "completed") -> None:
    """Helper to insert a trace row directly."""
    await conn.execute(
        "INSERT INTO traces (id, phone_number, input_text, message_type, status) "
        "VALUES (?, '123', 'test', 'text', ?)",
        (trace_id, status),
    )
    await conn.commit()


async def test_get_failure_trend_returns_empty_when_no_traces(repository):
    rows = await repository.get_failure_trend(days=7)
    assert rows == []


async def test_get_failure_trend_counts_correctly(repository):
    await _insert_trace(repository._conn, "t1", "completed")
    await _insert_trace(repository._conn, "t2", "failed")
    await _insert_trace(repository._conn, "t3", "completed")

    rows = await repository.get_failure_trend(days=30)
    assert len(rows) == 1  # all inserted today
    row = rows[0]
    assert row["total"] == 3
    assert row["failed"] == 1


async def test_get_score_distribution_returns_empty_when_no_scores(repository):
    rows = await repository.get_score_distribution()
    assert rows == []


async def test_get_score_distribution_groups_by_check(repository):
    await _insert_trace(repository._conn, "trace_sd1", "completed")
    await repository._conn.execute(
        "INSERT INTO trace_scores (trace_id, name, value, source) VALUES (?, ?, ?, ?)",
        ("trace_sd1", "language_match", 1.0, "system"),
    )
    await repository._conn.execute(
        "INSERT INTO trace_scores (trace_id, name, value, source) VALUES (?, ?, ?, ?)",
        ("trace_sd1", "language_match", 0.0, "system"),
    )
    await repository._conn.execute(
        "INSERT INTO trace_scores (trace_id, name, value, source) VALUES (?, ?, ?, ?)",
        ("trace_sd1", "not_empty", 1.0, "system"),
    )
    await repository._conn.commit()

    rows = await repository.get_score_distribution()
    assert len(rows) == 2

    by_check = {r["check"]: r for r in rows}
    assert "language_match" in by_check
    assert by_check["language_match"]["count"] == 2
    assert by_check["language_match"]["failures"] == 1
    assert "not_empty" in by_check
    assert by_check["not_empty"]["failures"] == 0
