from unittest.mock import AsyncMock, patch

import pytest

from app.llm.client import ChatResponse, OllamaClient
from app.models import ChatMessage
from app.skills.executor import MAX_TOOL_ITERATIONS, execute_tool_loop
from app.skills.registry import SkillRegistry


def _bypass_router():
    """Return patch decorators that bypass the tool router for unit tests."""
    return (
        patch("app.skills.executor.classify_intent", new_callable=AsyncMock, return_value=["time"]),
        patch(
            "app.skills.executor.select_tools",
            side_effect=lambda cats, all_tools, max_tools=8: list(all_tools.values()),
        ),
    )


@pytest.fixture
def skill_registry(tmp_path):
    reg = SkillRegistry(skills_dir=str(tmp_path))
    return reg


@pytest.fixture
def ollama_client():
    mock_http = AsyncMock()
    return OllamaClient(
        http_client=mock_http,
        base_url="http://localhost:11434",
        model="test-model",
    )


async def test_no_tool_calls_returns_text(ollama_client, skill_registry):
    """When LLM returns plain text, return it directly."""
    p1, p2 = _bypass_router()

    async def fake_handler() -> str:
        return "result"

    skill_registry.register_tool(
        name="test_tool",
        description="A test",
        parameters={"type": "object", "properties": {}},
        handler=fake_handler,
    )

    ollama_client.chat_with_tools = AsyncMock(
        return_value=ChatResponse(content="Just text, no tools")
    )

    messages = [ChatMessage(role="user", content="Hello")]
    with p1, p2:
        result = await execute_tool_loop(messages, ollama_client, skill_registry)
    assert result == "Just text, no tools"


async def test_single_tool_call(ollama_client, skill_registry):
    """LLM calls a tool, gets result, returns final text."""
    p1, p2 = _bypass_router()

    async def get_time() -> str:
        return "2024-01-01 12:00:00"

    skill_registry.register_tool(
        name="get_time",
        description="Get current time",
        parameters={"type": "object", "properties": {}},
        handler=get_time,
    )

    # First call: LLM returns a tool call
    # Second call: LLM returns final text
    ollama_client.chat_with_tools = AsyncMock(
        side_effect=[
            ChatResponse(
                content="",
                tool_calls=[{"function": {"name": "get_time", "arguments": {}}}],
            ),
            ChatResponse(content="The time is 12:00"),
        ]
    )

    messages = [ChatMessage(role="user", content="What time is it?")]
    with p1, p2:
        result = await execute_tool_loop(messages, ollama_client, skill_registry)
    assert result == "The time is 12:00"
    assert ollama_client.chat_with_tools.call_count == 2


async def test_max_iterations_forces_text(ollama_client, skill_registry):
    """After MAX_TOOL_ITERATIONS, force a response without tools."""
    p1, p2 = _bypass_router()

    async def dummy() -> str:
        return "ok"

    skill_registry.register_tool(
        name="loop_tool",
        description="Loops forever",
        parameters={"type": "object", "properties": {}},
        handler=dummy,
    )

    # All calls return tool_calls, except the final forced one
    tool_response = ChatResponse(
        content="",
        tool_calls=[{"function": {"name": "loop_tool", "arguments": {}}}],
    )
    final_response = ChatResponse(content="Forced final answer")

    responses = [tool_response] * MAX_TOOL_ITERATIONS + [final_response]
    ollama_client.chat_with_tools = AsyncMock(side_effect=responses)

    messages = [ChatMessage(role="user", content="Loop me")]
    with p1, p2:
        result = await execute_tool_loop(messages, ollama_client, skill_registry)
    assert result == "Forced final answer"
    # MAX_TOOL_ITERATIONS calls with tools + 1 final call without tools
    assert ollama_client.chat_with_tools.call_count == MAX_TOOL_ITERATIONS + 1


async def test_tool_error_returns_error_content(ollama_client, skill_registry):
    """Tool execution errors are returned as tool results."""
    p1, p2 = _bypass_router()

    async def failing_tool() -> str:
        raise RuntimeError("Network error")

    skill_registry.register_tool(
        name="bad_tool",
        description="Fails",
        parameters={"type": "object", "properties": {}},
        handler=failing_tool,
    )

    ollama_client.chat_with_tools = AsyncMock(
        side_effect=[
            ChatResponse(
                content="",
                tool_calls=[{"function": {"name": "bad_tool", "arguments": {}}}],
            ),
            ChatResponse(content="Sorry, there was an error"),
        ]
    )

    messages = [ChatMessage(role="user", content="Do the thing")]
    with p1, p2:
        result = await execute_tool_loop(messages, ollama_client, skill_registry)
    assert result == "Sorry, there was an error"


async def test_request_more_tools_expands_tool_set_in_loop(ollama_client, skill_registry):
    """request_more_tools meta-call must expand the active tool set for subsequent iterations."""

    async def save_note(content: str = "") -> str:
        return "Note saved"

    async def list_issues() -> str:
        return "GitHub issues: #1, #2"

    skill_registry.register_tool(
        name="save_note",
        description="Save a note",
        parameters={"type": "object", "properties": {"content": {"type": "string"}}},
        handler=save_note,
    )
    skill_registry.register_tool(
        name="list_issues",
        description="List GitHub issues",
        parameters={"type": "object", "properties": {}},
        handler=list_issues,
    )

    all_tools_map = {
        "save_note": {
            "type": "function",
            "function": {"name": "save_note", "description": "Save note", "parameters": {}},
        },
        "list_issues": {
            "type": "function",
            "function": {"name": "list_issues", "description": "List issues", "parameters": {}},
        },
    }

    ollama_client.chat_with_tools = AsyncMock(
        side_effect=[
            # Iteration 1: LLM calls request_more_tools to get github tools
            ChatResponse(
                content="",
                tool_calls=[
                    {
                        "function": {
                            "name": "request_more_tools",
                            "arguments": {"categories": ["github"], "reason": "need github tools"},
                        }
                    }
                ],
            ),
            # Iteration 2: LLM uses the newly added list_issues tool
            ChatResponse(
                content="",
                tool_calls=[{"function": {"name": "list_issues", "arguments": {}}}],
            ),
            # Iteration 3: final text response
            ChatResponse(content="Here are the GitHub issues"),
        ]
    )

    messages = [ChatMessage(role="user", content="List GitHub issues")]
    fake_categories = {"notes": ["save_note"], "github": ["list_issues"]}

    with (
        patch(
            "app.skills.executor.classify_intent", new_callable=AsyncMock, return_value=["notes"]
        ),
        patch("app.skills.executor._get_cached_tools_map", return_value=all_tools_map),
        patch("app.skills.router.TOOL_CATEGORIES", fake_categories),
        patch("app.skills.executor.TOOL_CATEGORIES", fake_categories),
    ):
        result = await execute_tool_loop(messages, ollama_client, skill_registry)

    assert result == "Here are the GitHub issues"
    assert ollama_client.chat_with_tools.call_count == 3


async def test_multiple_tool_calls_in_one_response(ollama_client, skill_registry):
    """LLM returns multiple tool calls in a single response."""
    p1, p2 = _bypass_router()

    async def tool_a() -> str:
        return "result_a"

    async def tool_b() -> str:
        return "result_b"

    skill_registry.register_tool(
        name="tool_a",
        description="A",
        parameters={"type": "object", "properties": {}},
        handler=tool_a,
    )
    skill_registry.register_tool(
        name="tool_b",
        description="B",
        parameters={"type": "object", "properties": {}},
        handler=tool_b,
    )

    ollama_client.chat_with_tools = AsyncMock(
        side_effect=[
            ChatResponse(
                content="",
                tool_calls=[
                    {"function": {"name": "tool_a", "arguments": {}}},
                    {"function": {"name": "tool_b", "arguments": {}}},
                ],
            ),
            ChatResponse(content="Both tools returned results"),
        ]
    )

    messages = [ChatMessage(role="user", content="Do both")]
    with p1, p2:
        result = await execute_tool_loop(messages, ollama_client, skill_registry)
    assert result == "Both tools returned results"
