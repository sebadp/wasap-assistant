---
name: expand
description: Install new MCP servers and skills at runtime without restarting
version: 1
tools:
  - search_mcp_registry
  - get_mcp_server_info
  - install_from_smithery
  - install_mcp_server
  - remove_mcp_server
  - list_mcp_servers
  - preview_skill_from_url
  - install_skill_from_url
  - reload_capabilities
---
Use these tools when asked to add new capabilities, install integrations, or manage MCP servers.

## MCP Servers (via Smithery registry)
- Use search_mcp_registry(query) to find available MCP servers by capability.
- Use get_mcp_server_info(name) to see connection details and available tools before installing.
- Use install_from_smithery(qualified_name) to auto-install (handles HTTP and stdio automatically).
- Use install_mcp_server(name, command, args) for local servers not on Smithery (e.g. npx-based).
- Use remove_mcp_server(name) to disconnect a server.
- Use list_mcp_servers() to see what's currently installed.

## Skills from URL (ClawHub / GitHub)
- Skills from ClawHub can be found via web_search("clawhub <capability> SKILL.md").
- Use preview_skill_from_url(url) to review a SKILL.md before installing.
- Use install_skill_from_url(name, url) to install (metadata + instructions only, no Python handlers).

## Important rules
- Always preview before installing: show the user what will be installed and get confirmation.
- After installing, explain what new tools are now available.
- Prefer install_from_smithery for any cloud service (email, calendar, drive, github, etc.).
- For ClawHub skills, use the GitHub raw URL of the SKILL.md file.
- reload_capabilities() is only needed after manual disk edits, not after install_from_smithery.
