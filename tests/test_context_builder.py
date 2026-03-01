"""Tests for app/context/context_builder.py"""

from app.context.context_builder import ContextBuilder
from app.models import ChatMessage


def test_empty_sections_skipped():
    builder = ContextBuilder("Base prompt")
    builder.add_section("user_memories", "")
    builder.add_section("daily_logs", None)
    result = builder.build_system_message()
    assert result == "Base prompt"
    assert "<user_memories>" not in result
    assert "<daily_logs>" not in result


def test_xml_tags_present():
    builder = ContextBuilder("Base prompt")
    builder.add_section("user_memories", "I like coffee")
    builder.add_section("recent_activity", "Did some stuff")
    result = builder.build_system_message()
    assert "<user_memories>" in result
    assert "</user_memories>" in result
    assert "I like coffee" in result
    assert "<recent_activity>" in result
    assert "</recent_activity>" in result
    assert "Did some stuff" in result


def test_base_prompt_preserved():
    base = "You are a helpful assistant."
    builder = ContextBuilder(base)
    builder.add_section("capabilities", "some tools here")
    result = builder.build_system_message()
    assert result.startswith(base)


def test_sections_in_order():
    builder = ContextBuilder("System")
    builder.add_section("first", "content A")
    builder.add_section("second", "content B")
    result = builder.build_system_message()
    assert result.index("<first>") < result.index("<second>")


def test_method_chaining():
    result = (
        ContextBuilder("Prompt")
        .add_section("a", "alpha")
        .add_section("b", "beta")
        .build_system_message()
    )
    assert "<a>" in result
    assert "<b>" in result


def test_no_sections_returns_base_prompt():
    builder = ContextBuilder("Just the base")
    assert builder.build_system_message() == "Just the base"


def test_history_appended_after_system():
    """Verify history messages come after the single system message."""
    from app.webhook.router import _build_context

    history = [
        ChatMessage(role="user", content="hello"),
        ChatMessage(role="assistant", content="hi!"),
    ]
    context = _build_context(
        system_prompt="sys",
        memories=[],
        relevant_notes=[],
        daily_logs=None,
        skills_summary=None,
        summary=None,
        history=history,
    )
    # First message is system
    assert context[0].role == "system"
    # History messages follow
    assert context[1].role == "user"
    assert context[2].role == "assistant"
