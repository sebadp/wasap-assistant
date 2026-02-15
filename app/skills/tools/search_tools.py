from __future__ import annotations

import asyncio
import logging

import primp
from lxml.html import document_fromstring

from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

# Max results to return to the LLM to avoid context overflow
MAX_RESULTS = 5

# DuckDuckGo Lite endpoint — simpler HTML, more reliable parsing
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"


def _perform_search(query: str, time_range: str | None = None) -> list[dict]:
    """Search DuckDuckGo Lite and parse results from the HTML table."""
    # Common browser versions supported by primp 1.0.0
    browsers = ["chrome_119", "chrome_118", "chrome_117"]
    
    params = {"q": query}
    if time_range:
        # DDG Lite often uses 'df' or 't' parameter. Using 'df' as standard.
        # Values: d (day), w (week), m (month), y (year)
        params["df"] = time_range

    for attempt, browser in enumerate(browsers):
        try:
            client = primp.Client(
                impersonate=browser,
                cookie_store=True,
                referer=True,
                follow_redirects=True,
                verify=True,
                timeout=15,
            )
            resp = client.get(DDG_LITE_URL, params=params)
            
            if resp.status_code == 200:
                resp_text = resp.text
                if resp_text and len(resp_text) > 100:
                    break  # Success
            
            logger.warning(f"Search attempt {attempt+1} ({browser}) failed: Status {resp.status_code}, Length {len(resp.text) if resp.text else 0}")
            if attempt < len(browsers) - 1:
                import time
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Search attempt {attempt+1} failed with error: {e}")
    else:
        # All attempts failed
        return []

    tree = document_fromstring(resp_text)

    links = tree.xpath('//a[@class="result-link"]')
    snippets = tree.xpath('//td[@class="result-snippet"]')

    results = []
    for i, link in enumerate(links):
        href = link.get("href", "")
        title = (link.text or "").strip()
        body = ""
        if i < len(snippets):
            body = (snippets[i].text_content() or "").strip()

        if href and title:
            results.append({"title": title, "href": href, "body": body})

        if len(results) >= MAX_RESULTS:
            break

    return results


def register(registry: SkillRegistry) -> None:
    async def web_search(query: str) -> str:
        logger.info("Searching web for: %s", query)
        try:
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(None, _perform_search, query)

            if not results:
                logger.info("No results found for: %s", query)
                return f"No results found for '{query}'."

            formatted_results = []
            for i, res in enumerate(results, 1):
                title = res.get("title", "No title")
                link = res.get("href", "#")
                body = res.get("body", "")
                formatted_results.append(f"{i}. [{title}]({link}): {body}")

            output = "\n\n".join(formatted_results)
            logger.info("Found %d results for: %s", len(results), query)
            return output

        except Exception as e:
            logger.exception("Search failed for query '%s'", query)
            return f"Error performing search: {e}"

    registry.register_tool(
        name="web_search",
        description="Search the internet for information",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g. 'latest news about AI', 'recipe for lasagna')",
                },
            },
            "required": ["query"],
        },
        handler=web_search,
        skill_name="search",
    )
