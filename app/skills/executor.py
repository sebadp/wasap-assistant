from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.llm.client import OllamaClient
from app.models import ChatMessage
from app.skills.models import ToolCall
from app.skills.registry import SkillRegistry
from app.skills.router import classify_intent, select_tools
from app.tracing.context import get_current_trace

if TYPE_CHECKING:
    from app.mcp.manager import McpManager

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5

# Module-level cache: tools don't change at runtime after initialization
_cached_tools_map: dict[str, dict] | None = None


def _build_tools_map(
    skill_registry: SkillRegistry,
    mcp_manager: McpManager | None,
) -> dict[str, dict]:
    """Build a name -> ollama schema dict from all available tools."""
    tools_map: dict[str, dict] = {}
    for tool_schema in skill_registry.get_ollama_tools():
        name = tool_schema["function"]["name"]
        tools_map[name] = tool_schema
    if mcp_manager:
        for tool_schema in mcp_manager.get_ollama_tools():
            name = tool_schema["function"]["name"]
            tools_map[name] = tool_schema
    return tools_map


def _get_cached_tools_map(
    skill_registry: SkillRegistry,
    mcp_manager: McpManager | None,
) -> dict[str, dict]:
    """Return cached tools map, building it on first call."""
    global _cached_tools_map
    if _cached_tools_map is None:
        _cached_tools_map = _build_tools_map(skill_registry, mcp_manager)
    return _cached_tools_map


def reset_tools_cache() -> None:
    """Invalidate the cached tools map so it rebuilds on the next request.

    Call this after hot-adding or hot-removing MCP servers, or after
    reloading skills, to ensure the executor picks up the new tools.
    """
    global _cached_tools_map
    _cached_tools_map = None
    logger.info("Tools cache invalidated")


async def _run_tool_call(
    tc: dict,
    skill_registry: SkillRegistry,
    mcp_manager: McpManager | None,
) -> ChatMessage:
    """Execute a single tool call and return the result as a tool message."""
    func = tc.get("function", {})
    tool_name = func.get("name", "")
    arguments = func.get("arguments", {})

    # Lazy-load skill instructions on first use (only for local skills)
    instructions = skill_registry.get_skill_instructions(tool_name)

    tool_call = ToolCall(name=tool_name, arguments=arguments)

    trace = get_current_trace()
    if trace:
        async with trace.span(f"tool:{tool_name}", kind="tool") as span:
            span.set_input({"tool": tool_name, "arguments": arguments})
            if mcp_manager and mcp_manager.has_tool(tool_name):
                result = await mcp_manager.execute_tool(tool_call)
            else:
                result = await skill_registry.execute_tool(tool_call)
            span.set_output({"content": result.content[:200]})
    else:
        if mcp_manager and mcp_manager.has_tool(tool_name):
            result = await mcp_manager.execute_tool(tool_call)
        else:
            result = await skill_registry.execute_tool(tool_call)

    logger.info("Tool %s -> %s", tool_name, result.content[:100])

    final_content = result.content
    if instructions:
        final_content = f"{instructions}\n\nResult:\n{result.content}"

    return ChatMessage(role="tool", content=final_content)


async def execute_tool_loop(
    messages: list[ChatMessage],
    ollama_client: OllamaClient,
    skill_registry: SkillRegistry,
    mcp_manager: McpManager | None = None,
    max_tools: int = 8,
    pre_classified_categories: list[str] | None = None,
) -> str:
    """Run the tool calling loop: classify intent, select tools, execute."""
    # Extract last user message for classification (only if not pre-classified)
    user_message = ""
    if pre_classified_categories is None:
        for msg in reversed(messages):
            if msg.role == "user":
                user_message = msg.content
                break

    # Stage 1: classify intent (use pre-computed result if available)
    all_tools_map = _get_cached_tools_map(skill_registry, mcp_manager)
    categories = pre_classified_categories or await classify_intent(user_message, ollama_client)

    if categories == ["none"]:
        logger.info("Tool router: categories=none, plain chat")
        return await ollama_client.chat(messages)

    # Stage 2: select relevant tools
    tools = select_tools(categories, all_tools_map, max_tools=max_tools)
    logger.info(
        "Tool router: categories=%s, selected %d tools",
        categories,
        len(tools),
    )

    if not tools:
        logger.info("Tool router: no matching tools found, plain chat")
        return await ollama_client.chat(messages)

    working_messages = list(messages)

    for iteration in range(MAX_TOOL_ITERATIONS):
        response = await ollama_client.chat_with_tools(working_messages, tools=tools)

        if not response.tool_calls:
            return response.content

        logger.info(
            "Tool iteration %d: %d tool call(s)",
            iteration + 1,
            len(response.tool_calls),
        )

        # Append assistant message with tool_calls
        working_messages.append(ChatMessage(
            role="assistant",
            content=response.content or "",
            tool_calls=response.tool_calls,
        ))

        # Execute all tool calls in parallel, append results in order
        tool_messages = await asyncio.gather(*[
            _run_tool_call(tc, skill_registry, mcp_manager)
            for tc in response.tool_calls
        ])
        working_messages.extend(tool_messages)

    # Safety: exceeded max iterations, force a text response without tools
    logger.warning("Max tool iterations (%d) reached, forcing text response", MAX_TOOL_ITERATIONS)
    response = await ollama_client.chat_with_tools(working_messages, tools=None)
    return response.content
