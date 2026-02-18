from app.skills.registry import SkillRegistry
from app.skills.tools.tool_manager_tools import register
from app.skills.router import TOOL_CATEGORIES


def _make_registry() -> SkillRegistry:
    reg = SkillRegistry(skills_dir="/nonexistent")
    register(reg)
    return reg


async def test_list_tool_categories():
    reg = _make_registry()
    tool = reg._tools["list_tool_categories"]
    result = await tool.handler()
    for category in TOOL_CATEGORIES:
        assert category in result


async def test_list_category_tools_valid():
    reg = _make_registry()
    tool = reg._tools["list_category_tools"]
    result = await tool.handler(category="weather")
    assert "get_weather" in result
    assert "weather" in result


async def test_list_category_tools_unknown():
    reg = _make_registry()
    tool = reg._tools["list_category_tools"]
    result = await tool.handler(category="nonexistent")
    assert "Unknown category" in result
    assert "weather" in result  # suggests available categories


async def test_list_category_tools_strips_whitespace():
    reg = _make_registry()
    tool = reg._tools["list_category_tools"]
    result = await tool.handler(category="  Math  ")
    assert "calculate" in result


async def test_tools_registered():
    reg = _make_registry()
    assert "list_tool_categories" in reg._tools
    assert "list_category_tools" in reg._tools
    assert reg._tools["list_tool_categories"].skill_name == "tools"
    assert reg._tools["list_category_tools"].skill_name == "tools"
