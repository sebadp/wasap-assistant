"""Shallow clone management for deep code search (Plan 63-C).

Pattern: git clone --depth 1, fetch+reset for updates, cleanup stale clones.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_CLONES_DIR = "data/repo_clones"


async def _run_git(args: list[str], cwd: Path | None = None, timeout: int = 60) -> str:
    """Run a git command asynchronously."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {err}")
    return stdout.decode().strip()


def _clone_dir(repo_key: str, clones_dir: Path) -> Path:
    """Get the clone directory for a repo key like 'github:owner/repo'."""
    safe = repo_key.replace(":", "_").replace("/", "_")
    return clones_dir / safe


async def ensure_clone(
    repo_key: str,
    clone_url: str,
    clones_dir: str = _DEFAULT_CLONES_DIR,
) -> Path:
    """Ensure a shallow clone exists and is up to date.

    If clone exists: git fetch + reset to origin/HEAD.
    If not: git clone --depth 1 --single-branch.
    """
    base = Path(clones_dir)
    base.mkdir(parents=True, exist_ok=True)
    clone_path = _clone_dir(repo_key, base)

    if clone_path.exists() and (clone_path / ".git").is_dir():
        # Update existing clone
        await _run_git(["fetch", "origin"], cwd=clone_path)
        await _run_git(["reset", "--hard", "origin/HEAD"], cwd=clone_path)
        logger.info("Updated clone for %s", repo_key)
    else:
        # Fresh clone
        if clone_path.exists():
            shutil.rmtree(clone_path)
        await _run_git(["clone", "--depth", "1", "--single-branch", clone_url, str(clone_path)])
        logger.info("Cloned %s to %s", repo_key, clone_path)

    return clone_path


def get_clone_path(repo_key: str, clones_dir: str = _DEFAULT_CLONES_DIR) -> Path | None:
    """Return the clone path if it exists and is valid."""
    clone_path = _clone_dir(repo_key, Path(clones_dir))
    if clone_path.exists() and (clone_path / ".git").is_dir():
        return clone_path
    return None


def remove_clone(repo_key: str, clones_dir: str = _DEFAULT_CLONES_DIR) -> bool:
    """Remove a clone directory. Returns True if it existed."""
    clone_path = _clone_dir(repo_key, Path(clones_dir))
    if clone_path.exists():
        shutil.rmtree(clone_path)
        logger.info("Removed clone for %s", repo_key)
        return True
    return False


def cleanup_stale_clones(clones_dir: str = _DEFAULT_CLONES_DIR, max_age_days: int = 30) -> int:
    """Remove clones not modified in max_age_days. Returns count removed."""
    base = Path(clones_dir)
    if not base.exists():
        return 0
    cutoff = time.time() - (max_age_days * 86400)
    removed = 0
    for entry in base.iterdir():
        if entry.is_dir() and (entry / ".git").is_dir():
            mtime = entry.stat().st_mtime
            if mtime < cutoff:
                shutil.rmtree(entry)
                removed += 1
                logger.info("Cleaned stale clone: %s", entry.name)
    return removed
