from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.skills.registry import SkillRegistry
from app.skills.tools.search_tools import _perform_search

if TYPE_CHECKING:
    from app.database.repository import Repository

logger = logging.getLogger(__name__)


def register(registry: SkillRegistry, repository: Repository) -> None:
    async def add_news_preference(source: str, preference: str) -> str:
        """
        Save a user's preference for a news source.
        """
        # Validate preference
        pref = preference.lower()
        if pref not in ("like", "dislike"):
            return "Error: preference must be 'like' or 'dislike'."
        
        content = f"News Preference: User {pref}s {source}."
        logger.info(f"Saving news preference: {content}")
        
        # Save to memory (category 'news_pref')
        await repository.add_memory(content, category="news_pref")
        
        return f"Memorized: You {pref} {source}."

    async def search_news(query: str, time_range: str | None = None) -> str:
        """
        Search for news with optional time filtering.
        """
        logger.info(f"Searching news: {query} (time_range={time_range})")
        
        # Reuse the existing search implementation (sync function)
        import asyncio
        loop = asyncio.get_running_loop()
        
        # Use functools.partial to pass arguments to the sync function
        from functools import partial
        search_func = partial(_perform_search, query, time_range=time_range)
        results = await loop.run_in_executor(None, search_func)
        
        if not results:
            return "No news found."
            
        formatted_results = []
        for i, r in enumerate(results, 1):
            formatted_results.append(f"{i}. [{r['title']}]({r['href']}): {r['body']}")
            
        return "\n\n".join(formatted_results)

    registry.register_tool(
        name="add_news_preference",
        description="MEMORIZE a news preference. Call this IMMEDIATELY when the user explicitly mentions liking, disliking, or wanting to avoid a specific news source/site.",
        parameters={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Name of the news source (e.g. 'Pagina 12', 'Clarin')",
                },
                "preference": {
                    "type": "string",
                    "enum": ["like", "dislike"],
                    "description": "Must be 'like' or 'dislike'",
                },
            },
            "required": ["source", "preference"],
        },
        handler=add_news_preference,
        skill_name="news",
    )

    registry.register_tool(
        name="search_news",
        description="Search specifically for NEWS, CURRENT EVENTS, or RECENT UPDATES. Use this instead of generic web_search to leverage user preferences.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query including any site filters based on preferences",
                },
                "time_range": {
                    "type": "string",
                    "enum": ["d", "w", "m", "y"],
                    "description": "Time filter: 'd' (day), 'w' (week), 'm' (month), 'y' (year). USE THIS for relative dates like 'last week'.",
                },
            },
            "required": ["query"],
        },
        handler=search_news,
        skill_name="news",
    )
