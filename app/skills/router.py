from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.llm.client import OllamaClient

from app.models import ChatMessage

logger = logging.getLogger(__name__)

# Maps category names to tool names that belong to that category.
# Builtin tools use their exact registered names.
# MCP tools use the names exposed by the MCP server.
TOOL_CATEGORIES: dict[str, list[str]] = {
    "time": ["get_current_datetime", "convert_timezone", "schedule_task", "list_schedules"],
    "math": ["calculate"],
    "weather": ["get_weather"],
    "search": ["web_search"],
    "news": ["search_news", "add_news_preference"],
    "notes": ["save_note", "list_notes", "search_notes", "delete_note"],
    "files": ["read_file", "write_file", "list_directory", "search_files",
              "read_text_file", "list_allowed_directories"],
    "memory": ["create_entities", "add_observations", "search_nodes",
               "read_graph", "open_nodes", "delete_entities",
               "delete_observations", "delete_relations", "create_relations"],
    "github": ["list_issues", "create_issue", "search_repositories",
               "get_file_contents", "list_pull_requests", "create_pull_request",
               "create_or_update_file"],
    "tools": ["list_tool_categories", "list_category_tools"],
    "selfcode": [
        "get_version_info", "read_source_file", "list_source_files",
        "get_runtime_config", "get_system_health",
        "search_source_code", "get_skill_details",
    ],
    "expand": [
        "search_mcp_registry", "get_mcp_server_info", "install_from_smithery",
        "install_mcp_server", "remove_mcp_server", "list_mcp_servers",
        "preview_skill_from_url", "install_skill_from_url", "reload_capabilities",
    ],
    "projects": [
        "create_project", "list_projects", "get_project",
        "add_task", "update_task", "delete_task",
        "project_progress", "update_project_status",
        "add_project_note", "search_project_notes",
    ],
}

DEFAULT_CATEGORIES = ["time", "math", "weather", "search"]

CLASSIFIER_PROMPT = (
    "Classify this message into tool categories. "
    "Reply with ONLY category names separated by commas, or \"none\".\n"
    "Categories: time, math, weather, search, news, notes, files, memory, github, tools, selfcode, expand, projects, none\n\n"
    "Message: {user_message}"
)


def register_dynamic_category(category: str, tool_names: list[str]) -> None:
    """Add or update a category in TOOL_CATEGORIES at runtime.

    Used by McpManager when hot-adding servers so the classifier can
    route messages to the new tools.
    """
    existing = TOOL_CATEGORIES.get(category, [])
    # Merge without duplicates, preserving order
    merged = list(existing)
    for name in tool_names:
        if name not in merged:
            merged.append(name)
    TOOL_CATEGORIES[category] = merged
    logger.info("Dynamic category registered: %s (%d tools)", category, len(merged))


async def classify_intent(
    user_message: str,
    ollama_client: OllamaClient,
) -> list[str]:
    """Call the LLM without tools/think to classify the user message into categories."""
    prompt = CLASSIFIER_PROMPT.format(user_message=user_message)
    messages = [ChatMessage(role="user", content=prompt)]

    try:
        response = await ollama_client.chat_with_tools(messages, tools=None, think=False)
        raw = response.content.strip().lower()

        if raw == "none":
            return ["none"]

        # Parse comma-separated categories, keep only valid ones
        valid = set(TOOL_CATEGORIES.keys())
        categories = [c.strip() for c in raw.split(",") if c.strip() in valid]

        if not categories:
            logger.warning("Classifier returned no valid categories from: %r, using defaults", raw)
            return DEFAULT_CATEGORIES

        return categories

    except Exception:
        logger.exception("Intent classification failed, using defaults")
        return DEFAULT_CATEGORIES


def select_tools(
    categories: list[str],
    all_tools: dict[str, dict],
    max_tools: int = 8,
) -> list[dict]:
    """Given categories and a map of all available tools (name -> ollama schema), return filtered list.

    Args:
        categories: List of category names from classify_intent.
        all_tools: Dict mapping tool name to its Ollama tool schema dict.
        max_tools: Maximum number of tools to return.

    Returns:
        List of Ollama tool schema dicts, capped at max_tools.
    """
    selected: list[dict] = []
    seen: set[str] = set()

    for category in categories:
        tool_names = TOOL_CATEGORIES.get(category, [])
        for name in tool_names:
            if name in seen:
                continue
            if name in all_tools:
                selected.append(all_tools[name])
                seen.add(name)
            if len(selected) >= max_tools:
                return selected

    return selected
