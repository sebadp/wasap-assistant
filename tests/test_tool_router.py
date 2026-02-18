from unittest.mock import AsyncMock, MagicMock

from app.llm.client import ChatResponse
from app.skills.router import (
    DEFAULT_CATEGORIES,
    TOOL_CATEGORIES,
    classify_intent,
    select_tools,
)


def _make_tool_schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Tool {name}",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def _make_tools_map(names: list[str]) -> dict[str, dict]:
    return {name: _make_tool_schema(name) for name in names}


def _mock_ollama(response_text: str) -> AsyncMock:
    client = AsyncMock()
    client.chat_with_tools = AsyncMock(
        return_value=ChatResponse(content=response_text)
    )
    client.chat = AsyncMock(return_value="plain reply")
    return client


# --- classify_intent tests ---


async def test_classify_single_category():
    client = _mock_ollama("weather")
    result = await classify_intent("What's the weather?", client)
    assert result == ["weather"]
    # Should call with think=False
    client.chat_with_tools.assert_called_once()
    call_kwargs = client.chat_with_tools.call_args
    assert call_kwargs.kwargs.get("think") is False or call_kwargs[1].get("think") is False


async def test_classify_multiple_categories():
    client = _mock_ollama("time, weather")
    result = await classify_intent("What time is it and how's the weather?", client)
    assert result == ["time", "weather"]


async def test_classify_none():
    client = _mock_ollama("none")
    result = await classify_intent("Hello, how are you?", client)
    assert result == ["none"]


async def test_classify_invalid_response_returns_defaults():
    client = _mock_ollama("I don't understand the question")
    result = await classify_intent("Tell me a joke", client)
    assert result == DEFAULT_CATEGORIES


async def test_classify_mixed_valid_invalid():
    client = _mock_ollama("weather, foobar, math")
    result = await classify_intent("Calculate and check weather", client)
    assert result == ["weather", "math"]


async def test_classify_exception_returns_defaults():
    client = AsyncMock()
    client.chat_with_tools = AsyncMock(side_effect=Exception("LLM error"))
    result = await classify_intent("anything", client)
    assert result == DEFAULT_CATEGORIES


async def test_classify_empty_response_returns_defaults():
    client = _mock_ollama("")
    result = await classify_intent("test", client)
    assert result == DEFAULT_CATEGORIES


async def test_classify_strips_whitespace():
    client = _mock_ollama("  search , news  ")
    result = await classify_intent("Find latest news", client)
    assert result == ["search", "news"]


# --- select_tools tests ---


def test_select_single_category():
    tools_map = _make_tools_map(["get_weather", "calculate", "web_search"])
    result = select_tools(["weather"], tools_map)
    assert len(result) == 1
    assert result[0]["function"]["name"] == "get_weather"


def test_select_multiple_categories():
    all_names = ["get_current_datetime", "convert_timezone", "calculate", "get_weather"]
    tools_map = _make_tools_map(all_names)
    result = select_tools(["time", "math"], tools_map)
    names = [t["function"]["name"] for t in result]
    assert "get_current_datetime" in names
    assert "convert_timezone" in names
    assert "calculate" in names


def test_select_respects_max_tools():
    # Create tools for many categories
    all_names = (
        TOOL_CATEGORIES["time"]
        + TOOL_CATEGORIES["notes"]
        + TOOL_CATEGORIES["weather"]
    )
    tools_map = _make_tools_map(all_names)
    result = select_tools(["time", "notes", "weather"], tools_map, max_tools=3)
    assert len(result) == 3


def test_select_ignores_missing_tools():
    # Only some tools exist in the map
    tools_map = _make_tools_map(["get_weather"])
    result = select_tools(["weather", "math"], tools_map)
    assert len(result) == 1
    assert result[0]["function"]["name"] == "get_weather"


def test_select_unknown_category():
    tools_map = _make_tools_map(["get_weather"])
    result = select_tools(["nonexistent"], tools_map)
    assert result == []


def test_select_no_duplicates():
    tools_map = _make_tools_map(["get_weather"])
    # Same category twice shouldn't duplicate
    result = select_tools(["weather", "weather"], tools_map)
    assert len(result) == 1


def test_select_empty_categories():
    tools_map = _make_tools_map(["get_weather"])
    result = select_tools([], tools_map)
    assert result == []
