import pytest
from unittest.mock import MagicMock, patch
from app.skills.models import ToolCall
from app.skills.registry import SkillRegistry
from app.skills.tools.search_tools import register

def _make_registry():
    reg = SkillRegistry(skills_dir="/nonexistent")
    register(reg)
    return reg

@pytest.mark.asyncio
async def test_web_search_success():
    reg = _make_registry()
    
    query = "test query"
    mock_results = [
        {"title": "Result 1", "href": "http://example.com/1", "body": "Snippet 1"},
        {"title": "Result 2", "href": "http://example.com/2", "body": "Snippet 2"},
    ]

    # Mock DDGS context manager and text method
    with patch("app.skills.tools.search_tools.DDGS") as MockDDGS:
        mock_ddgs_instance = MockDDGS.return_value
        mock_ddgs_instance.__enter__.return_value = mock_ddgs_instance
        # interact returns an iterable, so we check how it's used.
        # the implementation calls list(ddgs.text(...))
        # so we mock text() to return the list directly (which is iterable)
        mock_ddgs_instance.text.return_value = mock_results

        result = await reg.execute_tool(ToolCall(name="web_search", arguments={"query": query}))

    assert result.success
    assert "Result 1" in result.content
    assert "Snippet 1" in result.content
    assert "http://example.com/1" in result.content
    assert "Result 2" in result.content

@pytest.mark.asyncio
async def test_web_search_no_results():
    reg = _make_registry()
    
    with patch("app.skills.tools.search_tools.DDGS") as MockDDGS:
        mock_ddgs_instance = MockDDGS.return_value
        mock_ddgs_instance.__enter__.return_value = mock_ddgs_instance
        mock_ddgs_instance.text.return_value = []

        result = await reg.execute_tool(ToolCall(name="web_search", arguments={"query": "nonexistent"}))

    assert result.success
    assert "No results found" in result.content

@pytest.mark.asyncio
async def test_web_search_error():
    reg = _make_registry()
    
    with patch("app.skills.tools.search_tools.DDGS") as MockDDGS:
        mock_ddgs_instance = MockDDGS.return_value
        mock_ddgs_instance.__enter__.return_value = mock_ddgs_instance
        mock_ddgs_instance.text.side_effect = Exception("Search failed")

        result = await reg.execute_tool(ToolCall(name="web_search", arguments={"query": "error"}))

    assert result.success
    assert "Error performing search" in result.content
