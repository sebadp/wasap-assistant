"""Integration tests for the guardrail pipeline."""
import pytest

from app.config import Settings
from app.guardrails.pipeline import run_guardrails


@pytest.fixture
def mock_settings(mocker):
    """Settings with guardrails fully enabled."""
    s = mocker.MagicMock(spec=Settings)
    s.guardrails_enabled = True
    s.guardrails_language_check = True
    s.guardrails_pii_check = True
    s.guardrails_llm_checks = False
    return s


@pytest.mark.asyncio
async def test_pipeline_passes_for_clean_interaction(mock_settings):
    user = "¿Qué hora es ahora mismo?"
    reply = "Son las 3:00 PM hora local."
    report = await run_guardrails(user_text=user, reply=reply, settings=mock_settings)
    assert report.passed is True
    assert report.total_latency_ms >= 0


@pytest.mark.asyncio
async def test_pipeline_fails_for_empty_reply(mock_settings):
    report = await run_guardrails(user_text="Hello", reply="", settings=mock_settings)
    assert report.passed is False
    failed = [r.check_name for r in report.results if not r.passed]
    assert "not_empty" in failed


@pytest.mark.asyncio
async def test_pipeline_fails_for_excessive_length(mock_settings):
    report = await run_guardrails(
        user_text="Explain something",
        reply="A" * 8001,
        settings=mock_settings,
    )
    assert report.passed is False
    failed = [r.check_name for r in report.results if not r.passed]
    assert "excessive_length" in failed


@pytest.mark.asyncio
async def test_pipeline_includes_all_check_names(mock_settings):
    report = await run_guardrails(
        user_text="Hello there", reply="Hi!", settings=mock_settings,
    )
    check_names = {r.check_name for r in report.results}
    # Always-on checks
    assert "not_empty" in check_names
    assert "excessive_length" in check_names
    assert "no_raw_tool_json" in check_names
    # Configurable checks
    assert "language_match" in check_names
    assert "no_pii" in check_names


@pytest.mark.asyncio
async def test_pipeline_language_check_disabled(mocker):
    s = mocker.MagicMock(spec=Settings)
    s.guardrails_language_check = False
    s.guardrails_pii_check = True
    report = await run_guardrails(
        user_text="Hello there my friend today", reply="Hi!", settings=s,
    )
    check_names = {r.check_name for r in report.results}
    assert "language_match" not in check_names


@pytest.mark.asyncio
async def test_pipeline_pii_check_disabled(mocker):
    s = mocker.MagicMock(spec=Settings)
    s.guardrails_language_check = True
    s.guardrails_pii_check = False
    report = await run_guardrails(
        user_text="Hello", reply="Contact me@example.com", settings=s,
    )
    check_names = {r.check_name for r in report.results}
    assert "no_pii" not in check_names


@pytest.mark.asyncio
async def test_pipeline_no_settings_uses_defaults():
    """Without settings, all checks run with defaults."""
    report = await run_guardrails(
        user_text="Hello", reply="Hi there!", settings=None,
    )
    # Should not raise; returns a report
    assert isinstance(report.passed, bool)


@pytest.mark.asyncio
async def test_pipeline_llm_checks_enabled_pass(mocker):
    """LLM checks run when guardrails_llm_checks=True and ollama_client is provided."""
    s = mocker.MagicMock(spec=Settings)
    s.guardrails_language_check = False
    s.guardrails_pii_check = False
    s.guardrails_llm_checks = True

    mock_client = mocker.AsyncMock()
    mock_client.chat.return_value = "no"  # no hallucination

    report = await run_guardrails(
        user_text="¿Cuál es la capital de Francia?",
        reply="Es París.",
        tool_calls_used=False,
        settings=s,
        ollama_client=mock_client,
    )
    check_names = {r.check_name for r in report.results}
    assert "hallucination_check" in check_names


@pytest.mark.asyncio
async def test_pipeline_llm_checks_tool_coherence_included_when_tools_used(mocker):
    """tool_coherence check runs when tool_calls_used=True and llm_checks=True."""
    s = mocker.MagicMock(spec=Settings)
    s.guardrails_language_check = False
    s.guardrails_pii_check = False
    s.guardrails_llm_checks = True

    mock_client = mocker.AsyncMock()
    mock_client.chat.return_value = "yes"  # coherent

    report = await run_guardrails(
        user_text="What time is it?",
        reply="It is 3pm.",
        tool_calls_used=True,
        settings=s,
        ollama_client=mock_client,
    )
    check_names = {r.check_name for r in report.results}
    assert "tool_coherence" in check_names
    assert "hallucination_check" in check_names


@pytest.mark.asyncio
async def test_pipeline_llm_checks_skipped_without_client(mocker):
    """LLM checks do not run when ollama_client is None, even if enabled."""
    s = mocker.MagicMock(spec=Settings)
    s.guardrails_language_check = False
    s.guardrails_pii_check = False
    s.guardrails_llm_checks = True

    report = await run_guardrails(
        user_text="hello", reply="hi", settings=s, ollama_client=None,
    )
    check_names = {r.check_name for r in report.results}
    assert "hallucination_check" not in check_names
    assert "tool_coherence" not in check_names


@pytest.mark.asyncio
async def test_pipeline_llm_check_timeout_fails_open(mocker):
    """LLM check timeout → fail open (result.passed=True)."""
    import asyncio

    s = mocker.MagicMock(spec=Settings)
    s.guardrails_language_check = False
    s.guardrails_pii_check = False
    s.guardrails_llm_checks = True

    mock_client = mocker.AsyncMock()

    async def _slow(*_a, **_kw):
        await asyncio.sleep(10)
        return "no"

    mock_client.chat.side_effect = _slow

    report = await run_guardrails(
        user_text="hello", reply="hi", settings=s, ollama_client=mock_client,
    )
    # Timed out → fail open
    hallucination = next(r for r in report.results if r.check_name == "hallucination_check")
    assert hallucination.passed is True
    assert "timed out" in hallucination.details
