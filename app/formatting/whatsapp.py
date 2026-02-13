import re


def markdown_to_whatsapp(text: str) -> str:
    """Convert Markdown formatting to WhatsApp-compatible formatting.

    Conversions:
    - **bold** → *bold*
    - *italic* or _italic_ → _italic_
    - ~~strike~~ → ~strike~
    - # Header → *Header*
    - [text](url) → text (url)
    - Code blocks preserved as-is
    """
    # Extract code blocks and inline code to protect them
    placeholders: list[str] = []

    def _protect(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"\x00CODE{len(placeholders) - 1}\x00"

    # Protect fenced code blocks first, then inline code
    text = re.sub(r"```[\s\S]*?```", _protect, text)
    text = re.sub(r"`[^`]+`", _protect, text)

    # Headers: # Header → *Header* (up to h6) — use bold placeholder
    _BOLD_MARK = "\x01BOLD\x01"
    text = re.sub(
        r"^#{1,6}\s+(.+)$",
        lambda m: f"{_BOLD_MARK}{m.group(1)}{_BOLD_MARK}",
        text,
        flags=re.MULTILINE,
    )

    # Links: [text](url) → text (url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)

    # Bold: **text** → use temp placeholder to avoid collision with italic *
    text = re.sub(r"\*\*(.+?)\*\*", lambda m: f"{_BOLD_MARK}{m.group(1)}{_BOLD_MARK}", text)

    # Italic: *text* → _text_  (only single * left after bold conversion)
    text = re.sub(r"\*(.+?)\*", r"_\1_", text)

    # Restore bold placeholder → *text*
    text = text.replace(_BOLD_MARK, "*")

    # Strikethrough: ~~text~~ → ~text~
    text = re.sub(r"~~(.+?)~~", r"~\1~", text)

    # Restore code blocks
    def _restore(m: re.Match) -> str:
        idx = int(m.group(1))
        return placeholders[idx]

    text = re.sub(r"\x00CODE(\d+)\x00", _restore, text)

    return text
