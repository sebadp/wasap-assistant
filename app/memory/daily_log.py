from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class DailyLog:
    def __init__(self, memory_dir: str = "data/memory"):
        self._dir = Path(memory_dir)

    async def append(self, entry: str) -> None:
        """Append an entry to today's daily log with timestamp."""
        now = datetime.now(UTC)
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")
        file_path = self._dir / f"{date_str}.md"
        parent_dir = self._dir

        def _do_append() -> None:
            parent_dir.mkdir(parents=True, exist_ok=True)
            if not file_path.exists():
                file_path.write_text(f"# {date_str}\n\n", encoding="utf-8")
            with file_path.open("a", encoding="utf-8") as f:
                f.write(f"- {time_str} — {entry}\n")

        await asyncio.to_thread(_do_append)

    async def load_recent(self, days: int = 2) -> str | None:
        """Load daily logs for the last N days. Returns None if no logs exist."""
        log_dir = self._dir

        def _do_load() -> str | None:
            if not log_dir.exists():
                return None
            now = datetime.now(UTC)
            parts: list[str] = []
            for i in range(days):
                date = now - timedelta(days=i)
                date_str = date.strftime("%Y-%m-%d")
                file_path = log_dir / f"{date_str}.md"
                if file_path.exists():
                    content = file_path.read_text(encoding="utf-8").strip()
                    if content:
                        parts.append(content)
            return "\n\n".join(parts) if parts else None

        return await asyncio.to_thread(_do_load)

    async def save_snapshot(self, slug: str, content: str) -> Path:
        """Save a session snapshot to data/memory/snapshots/."""
        now = datetime.now(UTC)
        date_str = now.strftime("%Y-%m-%d")
        snapshots_dir = self._dir / "snapshots"
        file_path = snapshots_dir / f"{date_str}-{slug}.md"

        def _do_save() -> None:
            snapshots_dir.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        await asyncio.to_thread(_do_save)
        logger.info("Saved session snapshot: %s", file_path.name)
        return file_path
