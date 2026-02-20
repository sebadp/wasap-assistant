from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings
    from app.mcp.manager import McpManager
    from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

_SMITHERY_SEARCH_URL = "https://registry.smithery.ai/servers"
_SMITHERY_SERVER_URL = "https://registry.smithery.ai/servers/{name}"

# Project root for writing skills
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def register(
    registry: SkillRegistry,
    mcp_manager: McpManager,
    settings: Settings,
) -> None:

    # ------------------------------------------------------------------
    # MCP Registry tools (Smithery)
    # ------------------------------------------------------------------

    async def search_mcp_registry(query: str, count: int = 5) -> str:
        """Search Smithery registry for MCP servers matching a query."""
        import httpx
        count = max(1, min(count, 10))
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    _SMITHERY_SEARCH_URL,
                    params={"q": query, "pageSize": count},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return f"Error searching MCP registry: {e}"

        servers = data.get("servers", [])
        if not servers:
            return f"No MCP servers found for '{query}'."

        pagination = data.get("pagination", {})
        total = pagination.get("totalCount", len(servers))

        lines = [f"Found {total} MCP servers for '{query}' (showing {len(servers)}):"]
        for s in servers:
            remote_label = "remote/HTTP" if s.get("remote") else "local"
            verified = " ✓" if s.get("verified") else ""
            lines.append(
                f"\n• {s['qualifiedName']}{verified} — {s.get('displayName', s['qualifiedName'])}"
                f"\n  {s.get('description', '')[:120]}"
                f"\n  Type: {remote_label} | Uses: {s.get('useCount', 0)}"
            )
        lines.append(
            "\nUse get_mcp_server_info(name) for details, "
            "or install_from_smithery(name) to install."
        )
        return "\n".join(lines)

    async def get_mcp_server_info(qualified_name: str) -> str:
        """Get full details of a Smithery MCP server including connection config."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    _SMITHERY_SERVER_URL.format(name=qualified_name),
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return f"Error fetching server info: {e}"

        lines = [
            f"Server: {data.get('displayName', qualified_name)}",
            f"Description: {data.get('description', '')}",
        ]

        connections = data.get("connections", [])
        if connections:
            lines.append("\nConnections:")
            for c in connections:
                if c["type"] == "http":
                    lines.append(f"  type: http  url: {c.get('deploymentUrl', '')}")
                elif c["type"] == "stdio":
                    lines.append(f"  type: stdio  command: {c.get('command', '')} {' '.join(c.get('args', []))}")

        tools = data.get("tools", [])
        if tools:
            lines.append(f"\nTools ({len(tools)}):")
            for t in tools[:10]:
                lines.append(f"  - {t.get('name', '?')}: {t.get('description', '')[:80]}")
            if len(tools) > 10:
                lines.append(f"  ... and {len(tools) - 10} more")

        return "\n".join(lines)

    async def install_from_smithery(qualified_name: str, alias: str = "") -> str:
        """Install an MCP server from the Smithery registry by its qualified name.

        Auto-detects the connection type (HTTP or stdio) from the registry.
        alias: optional local name (defaults to qualified_name).
        """
        import httpx
        name = alias.strip() or qualified_name.split("/")[-1]

        if name in {s["name"] for s in mcp_manager.list_servers() if s["status"] == "connected"}:
            return f"Server '{name}' is already installed."

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    _SMITHERY_SERVER_URL.format(name=qualified_name),
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return f"Error fetching server info from Smithery: {e}"

        connections = data.get("connections", [])
        if not connections:
            return f"No connection info available for '{qualified_name}'."

        # Prefer HTTP, fall back to stdio
        cfg: dict = {}
        for c in connections:
            if c["type"] == "http" and c.get("deploymentUrl"):
                cfg = {
                    "type": "http",
                    "url": c["deploymentUrl"],
                    "description": data.get("description", ""),
                    "enabled": True,
                }
                break
            elif c["type"] == "stdio" and c.get("command"):
                cfg = {
                    "type": "stdio",
                    "command": c["command"],
                    "args": c.get("args", []),
                    "description": data.get("description", ""),
                    "enabled": True,
                }
                break

        if not cfg:
            return f"Could not determine a usable connection for '{qualified_name}'."

        result = await mcp_manager.hot_add_server(name, cfg)
        return f"Installed '{qualified_name}' as '{name}'.\n{result}"

    # ------------------------------------------------------------------
    # Manual MCP server management
    # ------------------------------------------------------------------

    async def install_mcp_server(
        name: str,
        command: str,
        args: str = "",
        description: str = "",
        env_keys: str = "",
    ) -> str:
        """Manually install a local (stdio) MCP server.

        Args:
            name: Local identifier for this server.
            command: Executable (e.g. "npx", "uvx", "node", "python").
            args: Space-separated arguments (e.g. "-y @modelcontextprotocol/server-github").
            description: Human-readable description.
            env_keys: Comma-separated env var names needed (values set separately in .env).
        """
        if not name or not command:
            return "name and command are required."

        parsed_args = args.split() if args.strip() else []
        env: dict[str, str] = {}
        for key in (k.strip() for k in env_keys.split(",") if k.strip()):
            import os
            env[key] = os.environ.get(key, "")

        cfg: dict = {
            "type": "stdio",
            "command": command,
            "args": parsed_args,
            "description": description,
            "enabled": True,
        }
        if env:
            cfg["env"] = env

        return await mcp_manager.hot_add_server(name, cfg)

    async def remove_mcp_server(name: str) -> str:
        """Disconnect and remove an MCP server by name."""
        return await mcp_manager.hot_remove_server(name)

    async def list_mcp_servers() -> str:
        """List all configured MCP servers with their connection status."""
        servers = mcp_manager.list_servers()
        if not servers:
            return "No MCP servers configured."

        lines = ["MCP Servers:"]
        for s in servers:
            icon = "🟢" if s["status"] == "connected" else "🔴"
            tools_str = f" ({s['tools']} tools)" if s["status"] == "connected" else ""
            desc = f" — {s['description']}" if s.get("description") else ""
            lines.append(f"  {icon} {s['name']}{tools_str}{desc}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Skill installation from URL
    # ------------------------------------------------------------------

    async def preview_skill_from_url(url: str) -> str:
        """Fetch and display a SKILL.md from any public URL (GitHub raw, direct link, etc.)
        before deciding whether to install it.
        """
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.text
        except Exception as e:
            return f"Error fetching URL: {e}"

        if len(content) > 4000:
            content = content[:4000] + "\n... (truncated)"

        return f"Content from {url}:\n\n{content}"

    async def install_skill_from_url(name: str, url: str) -> str:
        """Download a SKILL.md from a URL and install it as a new skill.

        The skill's SKILL.md will be written to skills/<name>/SKILL.md and
        capabilities will be reloaded. Use preview_skill_from_url first to
        review the content before installing.

        Note: this installs the skill metadata/instructions only. Tools with
        Python handlers require manual implementation.
        """
        import httpx
        if not name or not name.isidentifier():
            return "Invalid skill name. Use lowercase letters, digits, and underscores only."

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.text
        except Exception as e:
            return f"Error fetching skill: {e}"

        # Basic validation: must have frontmatter
        if not content.strip().startswith("---"):
            return "Content doesn't look like a valid SKILL.md (missing frontmatter). Use preview_skill_from_url to review first."

        skill_dir = _PROJECT_ROOT / settings.skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(content, encoding="utf-8")

        # Reload skill metadata
        count = registry.reload()
        return (
            f"Installed skill '{name}' from {url}.\n"
            f"Skills directory now has {count} skills.\n"
            f"Note: if this skill defines tools that require Python handlers, "
            f"those must be implemented separately."
        )

    # ------------------------------------------------------------------
    # General reload
    # ------------------------------------------------------------------

    async def reload_capabilities() -> str:
        """Reload all skills and reset the tools cache.

        Use this after manually editing SKILL.md files or after installing
        new skill files on disk.
        """
        from app.skills.executor import reset_tools_cache
        count = registry.reload()
        reset_tools_cache()
        mcp_servers = len([s for s in mcp_manager.list_servers() if s["status"] == "connected"])
        return (
            f"Capabilities reloaded.\n"
            f"  Skills: {count}\n"
            f"  MCP servers connected: {mcp_servers}"
        )

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    registry.register_tool(
        name="search_mcp_registry",
        description="Search the Smithery MCP registry for servers matching a capability (e.g. 'email', 'calendar', 'github')",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Capability to search for"},
                "count": {"type": "integer", "description": "Number of results (1-10, default 5)"},
            },
            "required": ["query"],
        },
        handler=search_mcp_registry,
        skill_name="expand",
    )

    registry.register_tool(
        name="get_mcp_server_info",
        description="Get full details and connection config for a Smithery MCP server by its qualified name",
        parameters={
            "type": "object",
            "properties": {
                "qualified_name": {"type": "string", "description": "Server qualified name (e.g. 'gmail', 'github')"},
            },
            "required": ["qualified_name"],
        },
        handler=get_mcp_server_info,
        skill_name="expand",
    )

    registry.register_tool(
        name="install_from_smithery",
        description="Install an MCP server from Smithery registry by qualified name (auto-detects HTTP or stdio)",
        parameters={
            "type": "object",
            "properties": {
                "qualified_name": {"type": "string", "description": "Smithery qualified name (e.g. 'gmail')"},
                "alias": {"type": "string", "description": "Optional local name override"},
            },
            "required": ["qualified_name"],
        },
        handler=install_from_smithery,
        skill_name="expand",
    )

    registry.register_tool(
        name="install_mcp_server",
        description="Manually install a local stdio MCP server by specifying command and args",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Local identifier"},
                "command": {"type": "string", "description": "Executable (e.g. 'npx', 'uvx')"},
                "args": {"type": "string", "description": "Space-separated args (e.g. '-y @modelcontextprotocol/server-github')"},
                "description": {"type": "string", "description": "Human-readable description"},
                "env_keys": {"type": "string", "description": "Comma-separated env var names needed"},
            },
            "required": ["name", "command"],
        },
        handler=install_mcp_server,
        skill_name="expand",
    )

    registry.register_tool(
        name="remove_mcp_server",
        description="Disconnect and remove an MCP server by name",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Server name to remove"},
            },
            "required": ["name"],
        },
        handler=remove_mcp_server,
        skill_name="expand",
    )

    registry.register_tool(
        name="list_mcp_servers",
        description="List all configured MCP servers with their status and tool count",
        parameters={"type": "object", "properties": {}},
        handler=list_mcp_servers,
        skill_name="expand",
    )

    registry.register_tool(
        name="preview_skill_from_url",
        description="Fetch and display a SKILL.md from any public URL before installing it",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch (GitHub raw, direct link, etc.)"},
            },
            "required": ["url"],
        },
        handler=preview_skill_from_url,
        skill_name="expand",
    )

    registry.register_tool(
        name="install_skill_from_url",
        description="Download a SKILL.md from a URL and install it as a new skill (metadata + instructions only)",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name (lowercase, no spaces)"},
                "url": {"type": "string", "description": "URL of the SKILL.md file"},
            },
            "required": ["name", "url"],
        },
        handler=install_skill_from_url,
        skill_name="expand",
    )

    registry.register_tool(
        name="reload_capabilities",
        description="Reload skill metadata from disk and reset the tools cache after manual changes",
        parameters={"type": "object", "properties": {}},
        handler=reload_capabilities,
        skill_name="expand",
    )
