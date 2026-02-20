from datetime import UTC, datetime, timedelta

from app.memory.daily_log import DailyLog


async def test_append_creates_file(tmp_path):
    log = DailyLog(memory_dir=str(tmp_path))
    await log.append("Test entry")

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    file_path = tmp_path / f"{today}.md"
    assert file_path.exists()
    content = file_path.read_text()
    assert f"# {today}" in content
    assert "Test entry" in content


async def test_append_multiple_entries(tmp_path):
    log = DailyLog(memory_dir=str(tmp_path))
    await log.append("First entry")
    await log.append("Second entry")

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    file_path = tmp_path / f"{today}.md"
    content = file_path.read_text()
    assert "First entry" in content
    assert "Second entry" in content
    # Header should appear only once
    assert content.count(f"# {today}") == 1


async def test_append_includes_timestamp(tmp_path):
    log = DailyLog(memory_dir=str(tmp_path))
    await log.append("Timed entry")

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    file_path = tmp_path / f"{today}.md"
    content = file_path.read_text()
    # Should have format "- HH:MM — entry"
    assert "— Timed entry" in content


async def test_load_recent_no_logs(tmp_path):
    log = DailyLog(memory_dir=str(tmp_path))
    result = await log.load_recent()
    assert result is None


async def test_load_recent_returns_today(tmp_path):
    log = DailyLog(memory_dir=str(tmp_path))
    await log.append("Today's entry")

    result = await log.load_recent(days=1)
    assert result is not None
    assert "Today's entry" in result


async def test_load_recent_returns_multiple_days(tmp_path):
    today = datetime.now(UTC)
    yesterday = today - timedelta(days=1)

    # Write yesterday's log manually
    yesterday_file = tmp_path / f"{yesterday.strftime('%Y-%m-%d')}.md"
    yesterday_file.write_text(f"# {yesterday.strftime('%Y-%m-%d')}\n\n- 10:00 — Yesterday event\n")

    log = DailyLog(memory_dir=str(tmp_path))
    await log.append("Today event")

    result = await log.load_recent(days=2)
    assert result is not None
    assert "Today event" in result
    assert "Yesterday event" in result


async def test_load_recent_skips_missing_days(tmp_path):
    log = DailyLog(memory_dir=str(tmp_path))
    await log.append("Only today")

    result = await log.load_recent(days=5)
    assert result is not None
    assert "Only today" in result


async def test_save_snapshot(tmp_path):
    log = DailyLog(memory_dir=str(tmp_path))
    content = "# Test snapshot\n\n**User**: Hello\n**Assistant**: Hi there!"
    path = await log.save_snapshot("test-conversation", content)

    assert path.exists()
    assert "test-conversation" in path.name
    assert path.read_text() == content
    assert path.parent.name == "snapshots"


async def test_save_snapshot_creates_directory(tmp_path):
    log = DailyLog(memory_dir=str(tmp_path / "nested" / "dir"))
    path = await log.save_snapshot("test", "content")
    assert path.exists()


async def test_append_creates_directory(tmp_path):
    log = DailyLog(memory_dir=str(tmp_path / "new" / "dir"))
    await log.append("Entry in new dir")

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    file_path = tmp_path / "new" / "dir" / f"{today}.md"
    assert file_path.exists()
