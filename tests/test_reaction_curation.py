"""Tests for the reaction → dataset curation and correction prompt pipeline."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import WhatsAppReaction
from app.webhook.router import _handle_reaction

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_reaction(emoji: str = "👍", from_number: str = "+1234567890") -> WhatsAppReaction:
    return WhatsAppReaction(
        message_id="reaction-msg-id",
        from_number=from_number,
        reacted_message_id="bot-msg-id",
        emoji=emoji,
    )


def _make_repository(
    *, trace_id: str | None = "trace-123", io: tuple | None = ("q", "a"), scores: list | None = None
) -> AsyncMock:
    repo = AsyncMock()
    repo.get_trace_id_by_wa_message_id.return_value = trace_id
    repo.get_trace_io_by_id.return_value = io
    repo.get_trace_scores.return_value = scores or []
    repo.save_trace_score.return_value = None
    return repo


def _make_settings(*, eval_auto_curate: bool = True) -> MagicMock:
    s = MagicMock()
    s.eval_auto_curate = eval_auto_curate
    return s


def _make_wa_client() -> AsyncMock:
    client = AsyncMock()
    client.send_message.return_value = "msg-id"
    return client


# ---------------------------------------------------------------------------
# Repository: get_trace_io_by_id
# ---------------------------------------------------------------------------


async def test_get_trace_io_by_id_returns_tuple(tmp_path):
    """Integration-style: verify the method is wired correctly in the real repo."""
    import aiosqlite

    from app.database.repository import Repository

    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "CREATE TABLE traces (id TEXT PRIMARY KEY, input_text TEXT, output_text TEXT)"
        )
        await conn.execute("INSERT INTO traces VALUES (?, ?, ?)", ("t1", "hello", "world"))
        await conn.commit()
        repo = Repository(conn)
        result = await repo.get_trace_io_by_id("t1")
        assert result == ("hello", "world")


async def test_get_trace_io_by_id_returns_none_for_unknown(tmp_path):
    import aiosqlite

    from app.database.repository import Repository

    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "CREATE TABLE traces (id TEXT PRIMARY KEY, input_text TEXT, output_text TEXT)"
        )
        await conn.commit()
        repo = Repository(conn)
        result = await repo.get_trace_io_by_id("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# _handle_reaction: score saving
# ---------------------------------------------------------------------------


async def test_positive_reaction_saves_score():
    repo = _make_repository()
    await _handle_reaction(_make_reaction("👍"), repo)
    repo.save_trace_score.assert_awaited_once()
    call_kwargs = repo.save_trace_score.call_args
    assert call_kwargs.kwargs["name"] == "user_reaction"
    assert call_kwargs.kwargs["value"] == 1.0
    assert call_kwargs.kwargs["source"] == "user"


async def test_negative_reaction_saves_score_zero():
    repo = _make_repository()
    await _handle_reaction(_make_reaction("👎"), repo)
    repo.save_trace_score.assert_awaited()
    first_call = repo.save_trace_score.call_args_list[0]
    assert first_call.kwargs["value"] == 0.0


async def test_unknown_emoji_defaults_to_neutral():
    repo = _make_repository()
    await _handle_reaction(_make_reaction("🤔"), repo)
    first_call = repo.save_trace_score.call_args_list[0]
    assert first_call.kwargs["value"] == 0.5


async def test_reaction_to_unknown_message_is_ignored():
    repo = _make_repository(trace_id=None)
    await _handle_reaction(_make_reaction("👍"), repo)
    repo.save_trace_score.assert_not_awaited()


async def test_non_reaction_object_is_ignored():
    repo = _make_repository()
    await _handle_reaction("not a reaction", repo)
    repo.save_trace_score.assert_not_awaited()


# ---------------------------------------------------------------------------
# _handle_reaction: curation pipeline
# ---------------------------------------------------------------------------


async def test_positive_reaction_triggers_curation():
    repo = _make_repository()
    settings = _make_settings(eval_auto_curate=True)

    with patch("app.webhook.router.maybe_curate_to_dataset", new_callable=AsyncMock) as mock_curate:
        await _handle_reaction(_make_reaction("👍"), repo, settings=settings)
        # Let the created task run
        await asyncio.sleep(0)
        mock_curate.assert_awaited_once()
        call_kwargs = mock_curate.call_args.kwargs
        assert call_kwargs["trace_id"] == "trace-123"
        assert call_kwargs["input_text"] == "q"
        assert call_kwargs["output_text"] == "a"


async def test_negative_reaction_triggers_curation():
    repo = _make_repository()
    settings = _make_settings(eval_auto_curate=True)

    with patch("app.webhook.router.maybe_curate_to_dataset", new_callable=AsyncMock) as mock_curate:
        await _handle_reaction(_make_reaction("👎"), repo, settings=settings)
        await asyncio.sleep(0)
        mock_curate.assert_awaited_once()


async def test_curation_skipped_when_eval_auto_curate_disabled():
    repo = _make_repository()
    settings = _make_settings(eval_auto_curate=False)

    with patch("app.webhook.router.maybe_curate_to_dataset", new_callable=AsyncMock) as mock_curate:
        await _handle_reaction(_make_reaction("👍"), repo, settings=settings)
        await asyncio.sleep(0)
        mock_curate.assert_not_awaited()


async def test_curation_skipped_when_no_trace_found():
    repo = _make_repository(trace_id=None)
    settings = _make_settings(eval_auto_curate=True)

    with patch("app.webhook.router.maybe_curate_to_dataset", new_callable=AsyncMock) as mock_curate:
        await _handle_reaction(_make_reaction("👍"), repo, settings=settings)
        await asyncio.sleep(0)
        mock_curate.assert_not_awaited()


async def test_curation_skipped_when_trace_has_no_io():
    repo = _make_repository(io=None)
    settings = _make_settings(eval_auto_curate=True)

    with patch("app.webhook.router.maybe_curate_to_dataset", new_callable=AsyncMock) as mock_curate:
        await _handle_reaction(_make_reaction("👍"), repo, settings=settings)
        await asyncio.sleep(0)
        mock_curate.assert_not_awaited()


# ---------------------------------------------------------------------------
# _handle_reaction: correction prompt
# ---------------------------------------------------------------------------


async def test_very_negative_reaction_sends_correction_prompt():
    repo = _make_repository(scores=[])
    wa_client = _make_wa_client()
    settings = _make_settings()

    with patch("app.webhook.router.maybe_curate_to_dataset", new_callable=AsyncMock):
        await _handle_reaction(_make_reaction("👎"), repo, wa_client=wa_client, settings=settings)
        await asyncio.sleep(0)

    wa_client.send_message.assert_awaited_once()
    call_args = wa_client.send_message.call_args
    assert call_args.args[0] == "+1234567890"
    assert "debería" in call_args.args[1]


async def test_correction_prompt_not_sent_twice():
    """If correction_prompted score already exists, don't send again."""
    existing = [{"name": "correction_prompted", "value": 1.0, "source": "system"}]
    repo = _make_repository(scores=existing)
    wa_client = _make_wa_client()
    settings = _make_settings()

    with patch("app.webhook.router.maybe_curate_to_dataset", new_callable=AsyncMock):
        await _handle_reaction(_make_reaction("👎"), repo, wa_client=wa_client, settings=settings)
        await asyncio.sleep(0)

    wa_client.send_message.assert_not_awaited()


async def test_neutral_reaction_no_correction_prompt():
    repo = _make_repository(scores=[])
    wa_client = _make_wa_client()
    settings = _make_settings()

    with patch("app.webhook.router.maybe_curate_to_dataset", new_callable=AsyncMock):
        await _handle_reaction(_make_reaction("😮"), repo, wa_client=wa_client, settings=settings)
        await asyncio.sleep(0)

    wa_client.send_message.assert_not_awaited()


async def test_positive_reaction_no_correction_prompt():
    repo = _make_repository(scores=[])
    wa_client = _make_wa_client()
    settings = _make_settings()

    with patch("app.webhook.router.maybe_curate_to_dataset", new_callable=AsyncMock):
        await _handle_reaction(_make_reaction("👍"), repo, wa_client=wa_client, settings=settings)
        await asyncio.sleep(0)

    wa_client.send_message.assert_not_awaited()


async def test_correction_prompt_saves_score():
    """After sending correction prompt, a score 'correction_prompted' is saved."""
    repo = _make_repository(scores=[])
    wa_client = _make_wa_client()
    settings = _make_settings()

    with patch("app.webhook.router.maybe_curate_to_dataset", new_callable=AsyncMock):
        await _handle_reaction(_make_reaction("👎"), repo, wa_client=wa_client, settings=settings)
        await asyncio.sleep(0)

    score_calls = [
        c
        for c in repo.save_trace_score.call_args_list
        if c.kwargs.get("name") == "correction_prompted"
    ]
    assert len(score_calls) == 1
    assert score_calls[0].kwargs["value"] == 1.0
    assert score_calls[0].kwargs["source"] == "system"
