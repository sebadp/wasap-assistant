from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.skills.models import ToolDefinition, ToolCall, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class McpServerConfig:
    command: str
    args: list[str]
    env: dict[str, str] = None
    enabled: bool = True


class McpManager:
    """
    Manages connections to multiple MCP servers.
    """

    def __init__(self, config_path: str = "data/mcp_servers.json"):
        self.config_path = config_path
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, ToolDefinition] = {}

    async def initialize(self) -> None:
        """Load config and connect to all enabled servers."""
        if not os.path.exists(self.config_path):
            logger.warning(f"MCP config not found at {self.config_path}")
            return

        try:
            with open(self.config_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return

        servers_config = data.get("servers", {})
        
        for name, cfg in servers_config.items():
            if not cfg.get("enabled", True):
                continue
                
            server_params = StdioServerParameters(
                command=cfg["command"],
                args=cfg["args"],
                env={**os.environ, **(cfg.get("env") or {})},
            )
            
            try:
                # Enter the stdio_client context
                transport = await self._exit_stack.enter_async_context(stdio_client(server_params))
                read, write = transport
                
                # Enter the ClientSession context
                session = await self._exit_stack.enter_async_context(
                    ClientSession(read, write)
                )
                
                # Initialize the session
                await session.initialize()
                
                self._sessions[name] = session
                logger.info(f"Connected to MCP server: {name}")
                
                # Load tools immediately
                await self._load_tools(name, session)
                
            except Exception as e:
                logger.error(f"Failed to connect to MCP server {name}: {e}")

    async def _load_tools(self, server_name: str, session: ClientSession) -> None:
        """Fetch tools from the server and adapt them to ToolDefinition."""
        try:
            result = await session.list_tools()
            for tool in result.tools:
                # Create a wrapper handler that calls the tool on the session
                async def handler(**kwargs) -> str:
                    try:
                        res = await session.call_tool(tool.name, arguments=kwargs)
                        # MCP returns a list of content (TextContent, ImageContent, etc.)
                        # We flatten it to a string for Ollama
                        text_parts = []
                        for content in res.content:
                            if content.type == "text":
                                text_parts.append(content.text)
                            elif content.type == "image":
                                text_parts.append(f"[Image: {content.mime_type}]")
                            elif content.type == "resource":
                                text_parts.append(f"[Resource: {content.uri}]")
                        return "\n".join(text_parts)
                    except Exception as e:
                        logger.error(f"Error calling MCP tool {tool.name}: {e}")
                        return f"Error: {e}"

                # Generate a unique name to avoid conflicts? 
                # Or trust servers to have unique tool names?
                # Using original name for now to keep it simple for LLM.
                tool_def = ToolDefinition(
                    name=tool.name,
                    description=tool.description or "",
                    parameters=tool.inputSchema,  # MCP uses JSON Schema, compatible with Ollama
                    handler=handler,
                    skill_name=f"mcp::{server_name}",
                )
                self._tools[tool.name] = tool_def
                logger.info(f"Registered MCP tool: {tool.name} (server: {server_name})")
                
        except Exception as e:
            logger.error(f"Failed to list tools for server {server_name}: {e}")

    def get_ollama_tools(self) -> list[dict]:
        """Return tool schemas in Ollama's expected format."""
        tools = []
        for tool in self._tools.values():
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return tools
        """Close all connections."""
        await self._exit_stack.aclose()
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
            # The handler is already wrapped to call the session
            result = await tool.handler(**tool_call.arguments)
            return ToolResult(tool_name=tool_call.name, content=result)
        except Exception as e:
            logger.exception("MCP Tool %s execution failed", tool_call.name)
            return ToolResult(
                tool_name=tool_call.name,
                content=f"MCP Tool error: {e}",
                success=False,
            )

    def get_tools(self) -> dict[str, ToolDefinition]:
        return self._tools
