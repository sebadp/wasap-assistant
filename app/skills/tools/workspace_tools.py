"""workspace_tools.py — Multi-project workspace management.

Allows the agent to switch between different project directories at runtime,
without requiring a container restart or config change.

Requires PROJECTS_ROOT to be set in .env to enable multi-project features.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# Mutable project root — shared with selfcode_tools and shell_tools via set_project_root()
_current_project_root: Path | None = None
_original_project_root: Path = Path(__file__).resolve().parents[3]
_projects_root: Path | None = None


def init_workspace(projects_root: str) -> None:
    """Initialize workspace tool with the configured projects_root directory."""
    global _projects_root, _current_project_root
    if projects_root:
        _projects_root = Path(projects_root).expanduser().resolve()
    _current_project_root = _original_project_root


def get_current_root() -> Path:
    """Return the active project root (used by shell and selfcode tools)."""
    return _current_project_root or _original_project_root


def _safe_project_name(name: str) -> bool:
    """Validate that a project name is safe (no path traversal)."""
    if not name:
        return False
    if "/" in name or "\\" in name or ".." in name:
        return False
    # Must resolve to a direct child of _projects_root
    return True


def _git_branch(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "N/A"
    except Exception:
        return "N/A"


def _count_py_files(path: Path) -> int:
    try:
        return sum(1 for _ in path.rglob("*.py") if ".git" not in str(_))
    except Exception:
        return 0


async def list_workspaces() -> str:
    """List all available project workspaces in the configured projects_root directory."""
    if not _projects_root:
        return (
            "Error: PROJECTS_ROOT is not configured. "
            "Set PROJECTS_ROOT=/path/to/projects in your .env to enable multi-project workspace."
        )

    if not _projects_root.exists():
        return f"Error: projects_root '{_projects_root}' does not exist."

    projects = [
        d for d in sorted(_projects_root.iterdir()) if d.is_dir() and not d.name.startswith(".")
    ]

    if not projects:
        return f"No projects found in {_projects_root}"

    current = _current_project_root or _original_project_root
    lines = [f"**Workspaces** (root: `{_projects_root}`):\n"]
    for proj in projects:
        active = " ← active" if proj.resolve() == current.resolve() else ""
        branch = _git_branch(proj)
        py_count = _count_py_files(proj)
        lines.append(f"• `{proj.name}/`  [git: {branch} | {py_count} .py files]{active}")

    return "\n".join(lines)


async def switch_workspace(name: str) -> str:
    """Switch the active project to a named workspace under projects_root.

    The name must be a direct subdirectory of projects_root. No path traversal allowed.
    """
    global _current_project_root

    if not _projects_root:
        return "Error: PROJECTS_ROOT is not configured."

    if not _safe_project_name(name):
        return f"Error: Invalid project name '{name}'. Use a simple directory name without path separators."

    target = (_projects_root / name).resolve()

    # Security: must be a direct child of projects_root
    try:
        target.relative_to(_projects_root)
    except ValueError:
        return f"Error: '{name}' is outside the projects root — path traversal not allowed."

    if not target.exists() or not target.is_dir():
        return f"Error: Project '{name}' not found in {_projects_root}."

    _current_project_root = target

    # Propagate to selfcode_tools and shell_tools if they expose set_project_root / set_cwd
    try:
        import app.skills.tools.selfcode_tools as sc

        if hasattr(sc, "_PROJECT_ROOT"):
            sc._PROJECT_ROOT = target  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        import app.skills.tools.shell_tools as sh

        if hasattr(sh, "_PROJECT_ROOT"):
            sh._PROJECT_ROOT = target  # type: ignore[attr-defined]
    except Exception:
        pass

    branch = _git_branch(target)
    py_count = _count_py_files(target)
    logger.info("Switched workspace to '%s' (%s)", name, target)

    return (
        f"\u2705 Workspace cambiado a `{name}`\n"
        f"Path: `{target}`\n"
        f"Branch: {branch} | {py_count} archivos .py"
    )


async def get_workspace_info() -> str:
    """Return information about the currently active workspace."""
    current = _current_project_root or _original_project_root
    name = current.name

    branch = _git_branch(current)
    py_count = _count_py_files(current)

    # Recent commits
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            cwd=current,
            capture_output=True,
            text=True,
            timeout=5,
        )
        recent = result.stdout.strip() if result.returncode == 0 else "N/A"
    except Exception:
        recent = "N/A"

    lines = [
        f"**Workspace activo**: `{name}`",
        f"**Path**: `{current}`",
        f"**Branch**: {branch}",
        f"**Archivos .py**: {py_count}",
        f"\n**Últimos commits:**\n```\n{recent}\n```",
    ]
    return "\n".join(lines)


if TYPE_CHECKING:
    from app.skills.registry import SkillRegistry


def register(registry: SkillRegistry, projects_root: str = "") -> None:
    """Register workspace tools. projects_root from settings."""
    init_workspace(projects_root)

    registry.register_tool(
        name="list_workspaces",
        description=(
            "List all available project workspaces. "
            "Requires PROJECTS_ROOT to be configured in settings."
        ),
        parameters={"type": "object", "properties": {}},
        handler=list_workspaces,
        skill_name="workspace",
    )
    registry.register_tool(
        name="switch_workspace",
        description=(
            "Switch the active project workspace by name. "
            "Use list_workspaces first to see available projects."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Project directory name (must be a direct child of projects_root).",
                },
            },
            "required": ["name"],
        },
        handler=switch_workspace,
        skill_name="workspace",
    )
    registry.register_tool(
        name="get_workspace_info",
        description="Get information about the currently active workspace: path, git branch, file count, recent commits.",
        parameters={"type": "object", "properties": {}},
        handler=get_workspace_info,
        skill_name="workspace",
    )
