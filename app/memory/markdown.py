from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.models import Memory

if TYPE_CHECKING:
    from app.memory.watcher import MemoryWatcher


class MemoryFile:
    def __init__(self, path: str):
        self._path = Path(path)
        self._watcher: MemoryWatcher | None = None

    def set_watcher(self, watcher: MemoryWatcher) -> None:
        """Register the watcher so sync() can set the guard."""
        self._watcher = watcher

    async def sync(self, memories: list[Memory]) -> None:
        import asyncio

        if self._watcher:
            self._watcher.set_sync_guard()
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            lines = ["# Memories\n"]
            for m in memories:
                if m.category:
                    lines.append(f"- [{m.category}] {m.content}")
                else:
                    lines.append(f"- {m.content}")
            content = "\n".join(lines) + "\n"
            path = self._path
            await asyncio.to_thread(path.write_text, content, "utf-8")
        finally:
            if self._watcher:
                # Delay clearing guard so watchdog event can pass
                await asyncio.sleep(0.5)
                self._watcher.clear_sync_guard()
