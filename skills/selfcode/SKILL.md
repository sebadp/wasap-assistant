---
name: selfcode
description: Inspect own source code, version, config and system health
version: 1
tools:
  - get_version_info
  - read_source_file
  - list_source_files
  - get_runtime_config
  - get_system_health
  - search_source_code
  - get_skill_details
---
Use these tools when asked about your own code, version, configuration or system status.
- Use get_version_info() first for general "what version are you?" queries.
- Use read_source_file(path) with paths relative to the project root (e.g. "app/main.py").
- Use list_source_files(directory) to explore structure before reading specific files.
- Use search_source_code(pattern) to find where something is implemented.
- Use get_skill_details(skill_name) to review how a specific skill/tool is defined.
- Never try to guess file paths; explore first with list_source_files.
- get_runtime_config() shows live settings (sensitive fields are hidden).
- get_system_health() checks connectivity to Ollama, DB and embeddings.
