import pytest

from app.skills.models import ToolCall
from app.skills.registry import SkillRegistry


@pytest.fixture
def registry(tmp_path):
    # Create a skill directory with a SKILL.md
    skill_dir = tmp_path / "test_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: test_skill
description: A test skill
tools:
  - greet
---
Always greet politely.""")

    reg = SkillRegistry(skills_dir=str(tmp_path))
    reg.load_skills()
    return reg


async def dummy_handler(name: str = "world") -> str:
    return f"Hello, {name}!"


def test_register_tool(registry):
    registry.register_tool(
        name="greet",
        description="Greet someone",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": []},
        handler=dummy_handler,
        skill_name="test_skill",
    )
    assert registry.has_tools()


def test_get_ollama_tools(registry):
    registry.register_tool(
        name="greet",
        description="Greet someone",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": []},
        handler=dummy_handler,
        skill_name="test_skill",
    )
    tools = registry.get_ollama_tools()
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "greet"


def test_get_tools_summary(registry):
    registry.register_tool(
        name="greet",
        description="Greet someone",
        parameters={"type": "object", "properties": {}},
        handler=dummy_handler,
    )
    summary = registry.get_tools_summary()
    assert "greet" in summary
    assert "Greet someone" in summary


def test_get_tools_summary_empty():
    reg = SkillRegistry(skills_dir="/nonexistent")
    assert reg.get_tools_summary() == ""


def test_has_tools_empty():
    reg = SkillRegistry(skills_dir="/nonexistent")
    assert reg.has_tools() is False


async def test_execute_tool(registry):
    registry.register_tool(
        name="greet",
        description="Greet someone",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": []},
        handler=dummy_handler,
        skill_name="test_skill",
    )
    result = await registry.execute_tool(ToolCall(name="greet", arguments={"name": "Alice"}))
    assert result.success is True
    assert result.content == "Hello, Alice!"


async def test_execute_unknown_tool(registry):
    result = await registry.execute_tool(ToolCall(name="unknown", arguments={}))
    assert result.success is False
    assert "Unknown tool" in result.content


async def test_execute_tool_error(registry):
    async def failing_handler() -> str:
        raise ValueError("boom")

    registry.register_tool(
        name="fail",
        description="Always fails",
        parameters={"type": "object", "properties": {}},
        handler=failing_handler,
    )
    result = await registry.execute_tool(ToolCall(name="fail", arguments={}))
    assert result.success is False
    assert "Tool error" in result.content


def test_get_skill_instructions_lazy_load(registry):
    registry.register_tool(
        name="greet",
        description="Greet someone",
        parameters={"type": "object", "properties": {}},
        handler=dummy_handler,
        skill_name="test_skill",
    )
    # First call returns instructions
    instructions = registry.get_skill_instructions("greet")
    assert instructions == "Always greet politely."

    # Second call returns None (already loaded)
    assert registry.get_skill_instructions("greet") is None


def test_get_skill_instructions_no_skill(registry):
    registry.register_tool(
        name="standalone",
        description="No skill",
        parameters={"type": "object", "properties": {}},
        handler=dummy_handler,
    )
    assert registry.get_skill_instructions("standalone") is None
