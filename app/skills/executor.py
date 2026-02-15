from __future__ import annotations

import logging

from app.llm.client import OllamaClient
from app.models import ChatMessage
from app.skills.models import ToolCall
from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5


async def execute_tool_loop(
    messages: list[ChatMessage],
    ollama_client: OllamaClient,
    skill_registry: SkillRegistry,
) -> str:
    """Run the tool calling loop: send messages to LLM, execute tools, repeat."""
    tools = skill_registry.get_ollama_tools()
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

        # Execute each tool call and append results
        for tc in response.tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            arguments = func.get("arguments", {})

            # Inject skill instructions on first use of a skill
            instructions = skill_registry.get_skill_instructions(tool_name)
            if instructions:
                working_messages.append(ChatMessage(
                    role="system",
                    content=instructions,
                ))

            tool_call = ToolCall(name=tool_name, arguments=arguments)
            result = await skill_registry.execute_tool(tool_call)
            logger.info("Tool %s -> %s", tool_name, result.content[:100])

            working_messages.append(ChatMessage(
                role="tool",
                content=result.content,
            ))

    # Safety: exceeded max iterations, force a text response without tools
    logger.warning("Max tool iterations (%d) reached, forcing text response", MAX_TOOL_ITERATIONS)
    response = await ollama_client.chat_with_tools(working_messages, tools=None)
    return response.content
