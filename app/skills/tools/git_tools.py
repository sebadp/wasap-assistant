"""Git tools for agentic sessions.

Provides a set of tools for interacting with the local Git repository:
- git_status: Show the current working tree status
- git_diff: Show file-level diff stats
- git_create_branch: Create and switch to a new branch
- git_commit: Stage all changes and commit
- git_push: Push the current branch to origin
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_GIT_TIMEOUT = 30  # seconds


def _run_git(*args: str) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Git command timed out."
    except FileNotFoundError:
        return -1, "", "git executable not found."
    except Exception as e:
        return -1, "", str(e)


def register(registry: SkillRegistry) -> None:
    """Register all git tools in the skill registry."""

    async def git_status() -> str:
        """Show the current Git status of the project (short format)."""
        code, out, err = await asyncio.to_thread(_run_git, "status", "--short", "--branch")
        if code != 0:
            return f"Error: {err}"
        return out or "(working tree clean)"

    async def git_diff() -> str:
        """Show a summary of staged and unstaged changes (--stat format)."""
        code, out, err = await asyncio.to_thread(_run_git, "diff", "--stat")
        staged_code, staged_out, staged_err = await asyncio.to_thread(
            _run_git, "diff", "--cached", "--stat"
        )
        parts = []
        if code != 0:
            parts.append(f"Error reading unstaged diff: {err}")
        elif out:
            parts.append(f"Unstaged:\n{out}")
        if staged_code != 0:
            parts.append(f"Error reading staged diff: {staged_err}")
        elif staged_out:
            parts.append(f"Staged:\n{staged_out}")
        if not parts:
            return "(no changes)"
        return "\n".join(parts)

    async def git_create_branch(branch_name: str) -> str:
        """Create and switch to a new Git branch."""
        clean = branch_name.strip()
        if not clean or " " in clean:
            return "Error: branch name cannot be empty or contain spaces."
        # Use `--` to prevent branch names starting with `-` being interpreted as flags
        code, out, err = await asyncio.to_thread(_run_git, "checkout", "-b", "--", clean)
        if code != 0:
            return f"Error creating branch '{clean}': {err}"
        return f"✅ Created and switched to branch: {clean}"

    async def git_commit(message: str) -> str:
        """Stage ALL changes (git add -A) and create a commit with the given message."""
        if not message.strip():
            return "Error: commit message cannot be empty."
        # Stage — check for errors before committing
        add_code, _, add_err = await asyncio.to_thread(_run_git, "add", "-A")
        if add_code != 0:
            return f"Error staging changes (git add -A): {add_err}"
        # Commit
        code, out, err = await asyncio.to_thread(_run_git, "commit", "-m", message.strip())
        if code != 0:
            if "nothing to commit" in err or "nothing added" in err:
                return "Nothing to commit — working tree is clean."
            return f"Error committing: {err}"
        return f"✅ Committed: {message.strip()}\n{out}"

    async def git_push(branch_name: str = "") -> str:
        """Push the current branch (or the specified branch) to origin."""
        cmd: list[str]
        if branch_name:
            clean = branch_name.strip()
            # Block flag injection: names starting with `-` would be interpreted as git flags
            if clean.startswith("-"):
                return f"Error: invalid branch name '{clean}' (cannot start with '-')."
            cmd = ["push", "--set-upstream", "origin", "--", clean]
        else:
            cmd = ["push"]
        code, out, err = await asyncio.to_thread(_run_git, *cmd)
        if code != 0:
            return f"Error pushing: {err}"
        return f"✅ Pushed successfully.\n{out or err}"

    registry.register_tool(
        name="git_status",
        description="Show the current Git status of the project (short format with branch info)",
        parameters={"type": "object", "properties": {}},
        handler=git_status,
        skill_name="git",
    )

    registry.register_tool(
        name="git_diff",
        description="Show a summary of staged and unstaged file changes (--stat format)",
        parameters={"type": "object", "properties": {}},
        handler=git_diff,
        skill_name="git",
    )

    registry.register_tool(
        name="git_create_branch",
        description="Create and switch to a new Git branch",
        parameters={
            "type": "object",
            "properties": {
                "branch_name": {
                    "type": "string",
                    "description": "Name for the new branch, e.g. 'fix/header-color'",
                },
            },
            "required": ["branch_name"],
        },
        handler=git_create_branch,
        skill_name="git",
    )

    registry.register_tool(
        name="git_commit",
        description=(
            "Stage ALL current changes (git add -A) and create a commit. "
            "Use a conventional commit message, e.g. 'fix: correct header color'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message (conventional commit format recommended)",
                },
            },
            "required": ["message"],
        },
        handler=git_commit,
        skill_name="git",
    )

    registry.register_tool(
        name="git_push",
        description="Push the current or specified branch to the 'origin' remote",
        parameters={
            "type": "object",
            "properties": {
                "branch_name": {
                    "type": "string",
                    "description": "Branch to push. If empty, pushes the current branch.",
                },
            },
        },
        handler=git_push,
        skill_name="git",
    )
