from __future__ import annotations

from pathlib import Path

from app.models import Memory


class MemoryFile:
    def __init__(self, path: str):
        self._path = Path(path)

    async def sync(self, memories: list[Memory]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Memories\n"]
        for m in memories:
            if m.category:
                lines.append(f"- [{m.category}] {m.content}")
            else:
                lines.append(f"- {m.content}")
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")
