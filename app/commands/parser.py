from __future__ import annotations


def parse_command(text: str) -> tuple[str, str] | None:
    text = text.strip()
    if not text.startswith("/"):
        return None
    parts = text[1:].split(None, 1)
    if not parts:
        return None
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    return (command, args)
