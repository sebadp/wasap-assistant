from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.database.repository import Repository
    from app.skills.registry import SkillRegistry


def register_builtin_tools(registry: SkillRegistry, repository: Repository) -> None:
    from app.skills.tools.calculator_tools import register as register_calculator
    from app.skills.tools.datetime_tools import register as register_datetime
    from app.skills.tools.notes_tools import register as register_notes
    from app.skills.tools.weather_tools import register as register_weather
    from app.skills.tools.search_tools import register as register_search
    from app.skills.tools.news_tools import register as register_news
    from app.skills.tools.scheduler_tools import register as register_scheduler
    from app.skills.tools.tool_manager_tools import register as register_tool_manager

    register_datetime(registry)
    register_calculator(registry)
    register_weather(registry)
    register_search(registry)
    register_notes(registry, repository)
    register_news(registry, repository)
    register_scheduler(registry)
    register_tool_manager(registry)

