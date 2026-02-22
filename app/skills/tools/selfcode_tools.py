from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings
    from app.llm.client import OllamaClient
    from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

# Resolve project root once at import time (wasap-assistant/)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

_SENSITIVE = {
    "whatsapp_access_token",
    "whatsapp_app_secret",
    "whatsapp_verify_token",
    "ngrok_authtoken",
}

_BLOCKED_NAME_PATTERNS = {".env", "secret", "token", "password", ".key", ".pem"}
_BLOCKED_EXT = {".pyc", ".pyo", ".db", ".sqlite", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".tar"}


def _is_safe_path(path: Path) -> bool:
    """Return True if path is within PROJECT_ROOT and not a sensitive file."""
    try:
        resolved = path.resolve()
    except Exception:
        return False

    if not resolved.is_relative_to(_PROJECT_ROOT):
        return False

    name_lower = resolved.name.lower()
    for pattern in _BLOCKED_NAME_PATTERNS:
        if pattern in name_lower:
            return False

    # Also block if any parent component is .env
    for part in resolved.parts:
        if part == ".env":
            return False

    return True


def register(
    registry: SkillRegistry,
    settings: Settings,
    ollama_client: OllamaClient | None = None,
    vec_available: bool = False,
) -> None:

    async def get_version_info() -> str:
        def _collect() -> str:
            lines = []

            # Git commit
            try:
                result = subprocess.run(
                    ["git", "log", "-1", "--pretty=format:%H %s %ai"],
                    capture_output=True,
                    text=True,
                    cwd=str(_PROJECT_ROOT),
                )
                if result.returncode == 0 and result.stdout.strip():
                    lines.append(f"Last commit: {result.stdout.strip()}")
            except Exception as e:
                lines.append(f"Git log unavailable: {e}")

            # Git branch
            try:
                result = subprocess.run(
                    ["git", "branch", "--show-current"],
                    capture_output=True,
                    text=True,
                    cwd=str(_PROJECT_ROOT),
                )
                if result.returncode == 0:
                    lines.append(f"Branch: {result.stdout.strip()}")
            except Exception as e:
                lines.append(f"Git branch unavailable: {e}")

            # Python version
            lines.append(f"Python: {sys.version}")

            # Models from settings
            lines.append(f"Chat model: {settings.ollama_model}")
            lines.append(f"Embedding model: {settings.embedding_model}")
            lines.append(f"Project root: {_PROJECT_ROOT}")

            return "\n".join(lines)

        return await asyncio.to_thread(_collect)

    async def read_source_file(path: str) -> str:
        def _read() -> str:
            target = (_PROJECT_ROOT / path).resolve()

            if not _is_safe_path(target):
                return f"Access denied: '{path}' is outside project root or is a sensitive file."

            if not target.exists():
                return f"File not found: {path}"

            if not target.is_file():
                return f"Not a file: {path}"

            try:
                content = target.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                return f"Error reading file: {e}"

            # Add line numbers
            lines = content.splitlines()
            numbered = "\n".join(f"{i + 1:4d}  {line}" for i, line in enumerate(lines))

            # Truncate if too long
            if len(numbered) > 5000:
                numbered = numbered[:5000] + f"\n... (truncated, {len(lines)} total lines)"

            return f"=== {path} ===\n{numbered}"

        return await asyncio.to_thread(_read)

    async def list_source_files(directory: str = "") -> str:
        def _list() -> str:
            target = (_PROJECT_ROOT / directory).resolve() if directory else _PROJECT_ROOT

            if not target.is_relative_to(_PROJECT_ROOT):
                return f"Access denied: '{directory}' is outside project root."

            if not target.exists():
                return f"Directory not found: {directory or '.'}"

            if not target.is_dir():
                return f"Not a directory: {directory or '.'}"

            EXCLUDED = {"__pycache__", ".git", ".venv", "node_modules", ".pytest_cache"}
            EXCLUDED_EXTS = {".pyc", ".pyo"}

            lines = [f"Contents of {directory or '.'}:"]

            def _walk(d: Path, prefix: str) -> None:
                try:
                    entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name))
                except PermissionError:
                    return
                for entry in entries:
                    if entry.name in EXCLUDED or entry.name.startswith("."):
                        continue
                    if entry.is_file() and entry.suffix in EXCLUDED_EXTS:
                        continue
                    if entry.is_dir():
                        lines.append(f"{prefix}{entry.name}/")
                        _walk(entry, prefix + "  ")
                    else:
                        lines.append(f"{prefix}{entry.name}")

            _walk(target, "  ")

            result = "\n".join(lines)
            if len(result) > 5000:
                result = result[:5000] + "\n... (truncated)"
            return result

        return await asyncio.to_thread(_list)

    async def get_runtime_config() -> str:
        lines = ["Runtime configuration (sensitive fields hidden):"]
        try:
            for field_name, _ in settings.model_fields.items():
                if field_name in _SENSITIVE:
                    lines.append(f"  {field_name}: ***hidden***")
                else:
                    value = getattr(settings, field_name, None)
                    lines.append(f"  {field_name}: {value}")
        except Exception as e:
            lines.append(f"Error reading config: {e}")
        return "\n".join(lines)

    async def get_system_health() -> str:
        parts = []

        # Ollama ping
        if ollama_client:
            try:
                await ollama_client.embed(["health_check"], model=settings.embedding_model)
                parts.append("Ollama: OK")
            except Exception as e:
                parts.append(f"Ollama: ERROR ({e})")
        else:
            parts.append("Ollama: client not configured")

        # Vector search
        parts.append(
            f"Vector search (sqlite-vec): {'available' if vec_available else 'not available'}"
        )

        # Data directories
        data_dirs = ["data", "data/memory", "data/memory/snapshots"]
        for d in data_dirs:
            p = _PROJECT_ROOT / d
            parts.append(f"Dir '{d}': {'exists' if p.exists() else 'missing'}")

        # Skills directory
        skills_path = _PROJECT_ROOT / settings.skills_dir
        parts.append(
            f"Skills dir '{settings.skills_dir}': {'exists' if skills_path.exists() else 'missing'}"
        )

        return "System health:\n" + "\n".join(f"  {p}" for p in parts)

    async def search_source_code(pattern: str) -> str:
        def _search() -> str:
            if not pattern or len(pattern) > 200:
                return "Invalid pattern."

            try:
                result = subprocess.run(
                    [
                        "grep",
                        "-rn",
                        "--include=*.py",
                        "--include=*.md",
                        "--",
                        pattern,
                        str(_PROJECT_ROOT),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except subprocess.TimeoutExpired:
                return "Search timed out."
            except FileNotFoundError:
                return "grep not available on this system."
            except Exception as e:
                return f"Search error: {e}"

            output = result.stdout or result.stderr or "(no matches)"

            # Strip the project root prefix for readability
            root_str = str(_PROJECT_ROOT) + "/"
            output = output.replace(root_str, "")

            # Limit to 60 lines
            lines = output.splitlines()
            if len(lines) > 60:
                lines = lines[:60]
                lines.append(
                    f"... (showing 60 of {len(lines) + (len(output.splitlines()) - 60)} matches)"
                )

            return "\n".join(lines)

        return await asyncio.to_thread(_search)

    async def get_skill_details(skill_name: str) -> str:
        skill = registry.get_skill(skill_name)
        if not skill:
            available = [s.name for s in registry.list_skills()]
            return f"Skill '{skill_name}' not found. Available skills: {', '.join(available) or 'none'}"

        tools = registry.get_tools_for_skill(skill_name)

        lines = [
            f"Skill: {skill.name}",
            f"Version: {skill.version}",
            f"Description: {skill.description}",
            "",
            "Tools:",
        ]
        for t in tools:
            td = registry._tools.get(t.name)
            if td:
                lines.append(f"  - {td.name}: {td.description}")
            else:
                lines.append(f"  - {t.name}")

        if skill.instructions:
            lines.append("")
            lines.append("Instructions:")
            lines.append(skill.instructions)

        return "\n".join(lines)

    async def get_recent_logs(lines: int = 100) -> str:
        def _read_logs() -> str:
            if lines > 500:
                return "Request too large. Max lines is 500."

            log_path = _PROJECT_ROOT / "data" / "wasap.log"
            if not log_path.exists():
                return "Log file not found at data/wasap.log"

            try:
                result = subprocess.run(
                    ["tail", "-n", str(max(1, lines)), str(log_path)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    output = result.stdout.strip()
                    return output if output else "Log file is empty."
                return f"Error reading logs: {result.stderr}"
            except subprocess.TimeoutExpired:
                return "Reading logs timed out."
            except FileNotFoundError:
                return "tail command not available on this system."
            except Exception as e:
                return f"Error: {e}"

        return await asyncio.to_thread(_read_logs)

    async def write_source_file(path: str, content: str) -> str:
        """Write content to a file within the project. Creates the file if it doesn't exist.

        Requires AGENT_WRITE_ENABLED=true in config.
        Safety: Only allows writing within PROJECT_ROOT. Blocks sensitive files and binary extensions.
        """
        if not settings.agent_write_enabled:
            return "Error: Write operations are disabled. Set AGENT_WRITE_ENABLED=true in .env to enable."

        target = (_PROJECT_ROOT / path).resolve()

        if not _is_safe_path(target):
            return f"Blocked: '{path}' is outside the project root or is a sensitive file."

        if target.suffix.lower() in _BLOCKED_EXT:
            return f"Blocked: Cannot write binary or database file ({target.suffix})"

        def _write() -> str:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                return f"✅ Written {len(content)} chars to {path}"
            except Exception as e:
                return f"Error writing file: {e}"

        logger.info("Agent write_source_file: %s (%d chars)", path, len(content))
        return await asyncio.to_thread(_write)

    async def apply_patch(path: str, search: str, replace: str) -> str:
        """Apply a targeted text replacement in a source file.

        Finds the FIRST occurrence of `search` in the file and replaces it with `replace`.
        Safer than full file rewrites for small edits.
        Requires AGENT_WRITE_ENABLED=true in config.
        """
        if not settings.agent_write_enabled:
            return "Error: Write operations are disabled. Set AGENT_WRITE_ENABLED=true in .env to enable."

        target = (_PROJECT_ROOT / path).resolve()

        if not _is_safe_path(target):
            return f"Blocked: '{path}' is outside the project root or is a sensitive file."

        if target.suffix.lower() in _BLOCKED_EXT:
            return f"Blocked: Cannot patch binary or database file ({target.suffix})"

        def _patch() -> str:
            if not target.exists():
                return f"Error: File '{path}' does not exist. Use write_source_file to create it."

            try:
                text = target.read_text(encoding="utf-8")
            except Exception as e:
                return f"Error reading file: {e}"

            if search not in text:
                # Give the LLM a useful hint to diagnose what went wrong
                snippet = text[:300] + ("..." if len(text) > 300 else "")
                return (
                    f"Error: Search string not found in '{path}'.\n"
                    f"Use read_source_file to check the exact current content.\n"
                    f"File starts with:\n{snippet}"
                )

            new_text = text.replace(search, replace, 1)
            try:
                target.write_text(new_text, encoding="utf-8")
            except Exception as e:
                return f"Error writing file: {e}"

            return f"✅ Patched '{path}': replaced {len(search)} chars with {len(replace)} chars."

        logger.info("Agent apply_patch: %s (search=%d chars)", path, len(search))
        return await asyncio.to_thread(_patch)

    # Register all tools
    registry.register_tool(
        name="get_version_info",
        description="Get current version info: git commit, branch, Python version, and model settings",
        parameters={"type": "object", "properties": {}},
        handler=get_version_info,
        skill_name="selfcode",
    )

    registry.register_tool(
        name="read_source_file",
        description="Read the contents of a source file within the project (path relative to project root)",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to project root, e.g. 'app/main.py'",
                },
            },
            "required": ["path"],
        },
        handler=read_source_file,
        skill_name="selfcode",
    )

    registry.register_tool(
        name="list_source_files",
        description="List files and directories within the project (optionally filtered by directory)",
        parameters={
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory path relative to project root (empty string for root)",
                },
            },
        },
        handler=list_source_files,
        skill_name="selfcode",
    )

    registry.register_tool(
        name="get_runtime_config",
        description="Get the current runtime configuration settings (sensitive values are hidden)",
        parameters={"type": "object", "properties": {}},
        handler=get_runtime_config,
        skill_name="selfcode",
    )

    registry.register_tool(
        name="get_system_health",
        description="Check system health: Ollama connectivity, vector search, and data directory status",
        parameters={"type": "object", "properties": {}},
        handler=get_system_health,
        skill_name="selfcode",
    )

    registry.register_tool(
        name="search_source_code",
        description="Search for a pattern in the project source code files (.py and .md)",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Search pattern (plain text or regex)",
                },
            },
            "required": ["pattern"],
        },
        handler=search_source_code,
        skill_name="selfcode",
    )

    registry.register_tool(
        name="get_skill_details",
        description="Get detailed information about a specific skill: its tools, instructions, and version",
        parameters={
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the skill to inspect",
                },
            },
            "required": ["skill_name"],
        },
        handler=get_skill_details,
        skill_name="selfcode",
    )

    registry.register_tool(
        name="get_recent_logs",
        description="Get the most recent lines from the application log file (data/wasap.log)",
        parameters={
            "type": "object",
            "properties": {
                "lines": {
                    "type": "integer",
                    "description": "Number of lines to retrieve (default: 100, max: 500)",
                    "default": 100,
                },
            },
        },
        handler=get_recent_logs,
        skill_name="selfcode",
    )

    registry.register_tool(
        name="write_source_file",
        description=(
            "Write content to a source file within the project. "
            "Creates the file and any missing parent directories. "
            "Requires AGENT_WRITE_ENABLED=true. "
            "Use for NEW files. For edits to existing files, prefer apply_patch."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to project root, e.g. 'app/new_module.py'",
                },
                "content": {
                    "type": "string",
                    "description": "Full content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
        handler=write_source_file,
        skill_name="selfcode",
    )

    registry.register_tool(
        name="apply_patch",
        description=(
            "Apply a targeted text replacement in an existing source file. "
            "Finds the FIRST occurrence of `search` and replaces it with `replace`. "
            "Safer than write_source_file for small edits. "
            "Requires AGENT_WRITE_ENABLED=true."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to project root",
                },
                "search": {
                    "type": "string",
                    "description": "Exact text to find in the file (must match exactly, including whitespace)",
                },
                "replace": {
                    "type": "string",
                    "description": "Text to replace the found string with",
                },
            },
            "required": ["path", "search", "replace"],
        },
        handler=apply_patch,
        skill_name="selfcode",
    )
