from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.skills.models import ToolCall, ToolDefinition, ToolResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Timeout for individual MCP tool calls (seconds)
MCP_TOOL_TIMEOUT = 30.0
# Timeout for connecting to an MCP server (seconds)
MCP_CONNECT_TIMEOUT = 30.0


def _make_handler(session: ClientSession, tool_name: str):
    """Create a handler bound to a specific session and tool name.

    This avoids the classic closure-over-loop-variable bug:
    without this factory, all handlers would reference the last
    tool/session from the loop.
    """

    async def handler(**kwargs: object) -> str:
        try:
            res = await asyncio.wait_for(
                session.call_tool(tool_name, arguments=kwargs),
                timeout=MCP_TOOL_TIMEOUT,
            )
            text_parts: list[str] = []
            for content in res.content:
                if content.type == "text":
                    text_parts.append(content.text)
                elif content.type == "image":
                    text_parts.append(f"[Image: {content.mimeType}]")
                elif content.type == "resource":
                    text_parts.append(f"[Resource: {content.uri}]")
            return "\n".join(text_parts)
        except asyncio.TimeoutError:
            logger.error("MCP tool %s timed out after %.0fs", tool_name, MCP_TOOL_TIMEOUT)
            return f"Error: tool {tool_name} timed out"
        except Exception as e:
            logger.error("Error calling MCP tool %s: %s", tool_name, e)
            return f"Error: {e}"

    return handler


class McpManager:
    """Manages connections to multiple MCP servers."""

    def __init__(self, config_path: str = "data/mcp_servers.json"):
        self.config_path = config_path
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, ToolDefinition] = {}
        self._server_descriptions: dict[str, str] = {}  # server_name -> description

    async def initialize(self) -> None:
        """Load config and connect to all enabled servers."""
        if not os.path.exists(self.config_path):
            logger.warning("MCP config not found at %s", self.config_path)
            return

        try:
            with open(self.config_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Failed to load MCP config: %s", e)
            return

        servers_config = data.get("servers", {})

        for name, cfg in servers_config.items():
            if not cfg.get("enabled", True):
                logger.info("MCP server %s is disabled, skipping", name)
                continue

            if "description" in cfg:
                self._server_descriptions[name] = cfg["description"]

            await self._connect_server(name, cfg)

        if self._tools:
            logger.info(
                "MCP initialized: %d server(s), %d tool(s)",
                len(self._sessions),
                len(self._tools),
            )
        else:
            logger.info("MCP initialized: no tools loaded")

    async def _connect_server(self, name: str, cfg: dict) -> None:
        """Connect to a single MCP server with timeout."""
        server_params = StdioServerParameters(
            command=cfg["command"],
            args=cfg.get("args", []),
            env={**os.environ, **(cfg.get("env") or {})},
        )

        try:
            transport = await asyncio.wait_for(
                self._exit_stack.enter_async_context(stdio_client(server_params)),
                timeout=MCP_CONNECT_TIMEOUT,
            )
            read, write = transport

            session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )

            await asyncio.wait_for(session.initialize(), timeout=MCP_CONNECT_TIMEOUT)

            self._sessions[name] = session
            logger.info("Connected to MCP server: %s", name)

            await self._load_tools(name, session)

        except asyncio.TimeoutError:
            logger.error(
                "MCP server %s timed out during connection (%.0fs)",
                name,
                MCP_CONNECT_TIMEOUT,
            )
        except Exception as e:
            logger.error("Failed to connect to MCP server %s: %s", name, e)

    async def _load_tools(self, server_name: str, session: ClientSession) -> None:
        """Fetch tools from the server and register them as ToolDefinitions."""
        try:
            result = await asyncio.wait_for(
                session.list_tools(), timeout=MCP_CONNECT_TIMEOUT
            )
        except Exception as e:
            logger.error("Failed to list tools for server %s: %s", server_name, e)
            return

        for tool in result.tools:
            # Detect name collisions
            if tool.name in self._tools:
                existing = self._tools[tool.name].skill_name
                logger.warning(
                    "MCP tool name collision: '%s' from mcp::%s overwrites %s",
                    tool.name,
                    server_name,
                    existing,
                )

            tool_def = ToolDefinition(
                name=tool.name,
                description=tool.description or "",
                parameters=tool.inputSchema,
                handler=_make_handler(session, tool.name),
                skill_name=f"mcp::{server_name}",
            )
            self._tools[tool.name] = tool_def
            logger.info("Registered MCP tool: %s (server: %s)", tool.name, server_name)

    def get_ollama_tools(self) -> list[dict]:
        """Return tool schemas in Ollama's expected format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    async def cleanup(self) -> None:
        """Close all connections."""
        try:
            await self._exit_stack.aclose()
        except Exception as e:
            logger.error("Error during MCP cleanup: %s", e)
        self._sessions.clear()
        self._tools.clear()
        logger.info("MCP Manager cleanup complete")

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tools

    async def execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call and return the result."""
        tool = self._tools.get(tool_call.name)
        if not tool:
            return ToolResult(
                tool_name=tool_call.name,
                content=f"Unknown MCP tool: {tool_call.name}",
                success=False,
            )
        try:
            result = await tool.handler(**tool_call.arguments)
            return ToolResult(tool_name=tool_call.name, content=result)
        except Exception as e:
            logger.exception("MCP tool %s execution failed", tool_call.name)
            return ToolResult(
                tool_name=tool_call.name,
                content=f"MCP tool error: {e}",
                success=False,
            )

    def get_tools_summary(self) -> str | None:
        """Return a summary of MCP tools grouped by server, for the system prompt."""
        if not self._tools:
            return None

        # Group tools by server
        by_server: dict[str, list[ToolDefinition]] = {}
        for tool in self._tools.values():
            # skill_name is "mcp::server_name"
            server = tool.skill_name.removeprefix("mcp::")
            by_server.setdefault(server, []).append(tool)

        lines = ["Available MCP capabilities:"]
        for server, tools in by_server.items():
            desc = self._server_descriptions.get(server, server)
            lines.append(f"\n{server} ({desc}):")
            for tool in tools:
                lines.append(f"- {tool.name}: {tool.description}")

        return "\n".join(lines)

    def get_tools(self) -> dict[str, ToolDefinition]:
        return dict(self._tools)
