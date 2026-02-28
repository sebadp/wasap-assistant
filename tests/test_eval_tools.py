"""Tests for eval tools — specifically the LLM-as-judge in run_quick_eval."""

from __future__ import annotations

from unittest.mock import AsyncMock


def _make_registry_and_register(repository_mock, ollama_mock):
    """Helper: build a minimal registry and call register() from eval_tools."""
    from app.skills.registry import SkillRegistry

    registry = SkillRegistry()

    from app.skills.tools.eval_tools import register

    register(
        registry=registry,
        repository=repository_mock,
        ollama_client=ollama_mock,
    )
    return registry


# ---------------------------------------------------------------------------
# run_quick_eval — LLM-as-judge
# ---------------------------------------------------------------------------


async def test_run_quick_eval_uses_llm_judge_yes():
    """run_quick_eval must use LLM-as-judge (binary yes/no) — 'yes' → passed=True → ✅."""
    repository_mock = AsyncMock()
    repository_mock.get_dataset_entries = AsyncMock(
        return_value=[
            {
                "id": 1,
                "input_text": "¿Cuánto es 2+2?",
                "output_text": "La respuesta es cuatro.",
                "expected_output": "4",
            }
        ]
    )

    # chat is called twice: first for the actual response, then for the judge
    ollama_mock = AsyncMock()
    ollama_mock.chat = AsyncMock(side_effect=["La respuesta es cuatro.", "yes"])

    registry = _make_registry_and_register(repository_mock, ollama_mock)
    handler = registry._tools["run_quick_eval"].handler
    result = await handler(category="all")

    # Judge prompt must contain "yes or no"
    judge_call = ollama_mock.chat.call_args_list[1]
    judge_messages = judge_call[0][0]
    assert "yes" in judge_messages[0].content.lower()
    assert "no" in judge_messages[0].content.lower()

    # Result must show ✅ and 1/1
    assert "✅" in result
    assert "1/1" in result


async def test_run_quick_eval_uses_llm_judge_no():
    """'no' from judge → passed=False → ❌ in output."""
    repository_mock = AsyncMock()
    repository_mock.get_dataset_entries = AsyncMock(
        return_value=[
            {
                "id": 2,
                "input_text": "Dime la capital de Francia",
                "output_text": "No sé.",
                "expected_output": "París",
            }
        ]
    )

    ollama_mock = AsyncMock()
    ollama_mock.chat = AsyncMock(side_effect=["No sé.", "no"])

    registry = _make_registry_and_register(repository_mock, ollama_mock)
    handler = registry._tools["run_quick_eval"].handler
    result = await handler(category="all")

    assert "❌" in result
    assert "0/1" in result


async def test_run_quick_eval_judge_uses_think_false():
    """Judge call must pass think=False to avoid chain-of-thought in binary prompt."""
    repository_mock = AsyncMock()
    repository_mock.get_dataset_entries = AsyncMock(
        return_value=[
            {
                "id": 3,
                "input_text": "¿Hola?",
                "output_text": "Hola",
                "expected_output": "Hola",
            }
        ]
    )

    ollama_mock = AsyncMock()
    ollama_mock.chat = AsyncMock(side_effect=["Hola", "yes"])

    registry = _make_registry_and_register(repository_mock, ollama_mock)
    handler = registry._tools["run_quick_eval"].handler
    await handler()

    # Second call (judge) must have think=False kwarg
    judge_call = ollama_mock.chat.call_args_list[1]
    assert judge_call.kwargs.get("think") is False


async def test_run_quick_eval_skips_entries_without_expected_output():
    """Entries without expected_output must be skipped gracefully."""
    repository_mock = AsyncMock()
    repository_mock.get_dataset_entries = AsyncMock(
        return_value=[
            {"id": 10, "input_text": "test", "output_text": "output", "expected_output": None},
        ]
    )

    ollama_mock = AsyncMock()
    ollama_mock.chat = AsyncMock()

    registry = _make_registry_and_register(repository_mock, ollama_mock)
    handler = registry._tools["run_quick_eval"].handler
    result = await handler()

    # No entries had expected_output — should get the "no entries" message
    assert "No correction entries" in result
    # chat must NOT have been called (no entries to process)
    ollama_mock.chat.assert_not_called()


async def test_run_quick_eval_no_entries_returns_helpful_message():
    """Empty dataset returns actionable message."""
    repository_mock = AsyncMock()
    repository_mock.get_dataset_entries = AsyncMock(return_value=[])

    ollama_mock = AsyncMock()

    registry = _make_registry_and_register(repository_mock, ollama_mock)
    handler = registry._tools["run_quick_eval"].handler
    result = await handler()

    assert "No dataset entries" in result
    assert "add_to_dataset" in result
