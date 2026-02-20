def split_message(text: str, max_length: int = 4096) -> list[str]:
    """Split a message into chunks that fit within max_length.

    Split priority: paragraph break (\\n\\n) > sentence end (. ) > space > hard cut.
    """
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Try to find the best split point within max_length
        segment = text[:max_length]

        # Priority 1: paragraph break
        pos = segment.rfind("\n\n")
        if pos > 0:
            chunks.append(text[:pos])
            text = text[pos + 2 :]
            continue

        # Priority 2: sentence end (". ")
        pos = segment.rfind(". ")
        if pos > 0:
            chunks.append(text[: pos + 1])
            text = text[pos + 2 :]
            continue

        # Priority 3: space
        pos = segment.rfind(" ")
        if pos > 0:
            chunks.append(text[:pos])
            text = text[pos + 1 :]
            continue

        # Priority 4: hard cut
        chunks.append(text[:max_length])
        text = text[max_length:]

    return chunks
