import re

from app.skills.registry import SkillRegistry
from app.skills.tools.datetime_tools import register


def _make_registry():
    reg = SkillRegistry(skills_dir="/nonexistent")
    register(reg)
    return reg


async def test_get_current_datetime_utc():
    reg = _make_registry()
    from app.skills.models import ToolCall

    result = await reg.execute_tool(
        ToolCall(name="get_current_datetime", arguments={"timezone": "UTC"})
    )
    assert result.success
    assert "UTC" in result.content
    # Should match datetime format, optionally preceded by a weekday name
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", result.content)


async def test_get_current_datetime_default():
    reg = _make_registry()
    from app.skills.models import ToolCall

    result = await reg.execute_tool(ToolCall(name="get_current_datetime", arguments={}))
    assert result.success
    assert "UTC" in result.content


async def test_get_current_datetime_invalid_tz():
    reg = _make_registry()
    from app.skills.models import ToolCall

    result = await reg.execute_tool(
        ToolCall(name="get_current_datetime", arguments={"timezone": "Fake/Place"})
    )
    assert result.success
    assert "Unknown timezone" in result.content


async def test_convert_timezone():
    reg = _make_registry()
    from app.skills.models import ToolCall

    result = await reg.execute_tool(
        ToolCall(
            name="convert_timezone",
            arguments={"time": "14:30", "from_timezone": "UTC", "to_timezone": "America/New_York"},
        )
    )
    assert result.success
    # Should contain a valid time
    assert re.search(r"\d{2}:\d{2}:\d{2}", result.content)


async def test_convert_timezone_invalid_from():
    reg = _make_registry()
    from app.skills.models import ToolCall

    result = await reg.execute_tool(
        ToolCall(
            name="convert_timezone",
            arguments={"time": "14:30", "from_timezone": "Fake/Zone", "to_timezone": "UTC"},
        )
    )
    assert "Unknown timezone" in result.content


async def test_convert_timezone_bad_time_format():
    reg = _make_registry()
    from app.skills.models import ToolCall

    result = await reg.execute_tool(
        ToolCall(
            name="convert_timezone",
            arguments={"time": "not-a-time", "from_timezone": "UTC", "to_timezone": "UTC"},
        )
    )
    assert "Could not parse" in result.content
