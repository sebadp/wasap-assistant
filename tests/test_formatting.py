from app.formatting.whatsapp import markdown_to_whatsapp


def test_bold():
    assert markdown_to_whatsapp("**hello**") == "*hello*"


def test_italic_asterisk():
    assert markdown_to_whatsapp("*hello*") == "_hello_"


def test_strikethrough():
    assert markdown_to_whatsapp("~~hello~~") == "~hello~"


def test_header():
    assert markdown_to_whatsapp("# Title") == "*Title*"
    assert markdown_to_whatsapp("## Subtitle") == "*Subtitle*"
    assert markdown_to_whatsapp("### Deep") == "*Deep*"


def test_link():
    assert markdown_to_whatsapp("[click](https://example.com)") == "click (https://example.com)"


def test_bold_and_italic():
    result = markdown_to_whatsapp("**bold** and *italic*")
    assert result == "*bold* and _italic_"


def test_code_block_preserved():
    text = "Before\n```python\n**not bold**\n```\nAfter **bold**"
    result = markdown_to_whatsapp(text)
    assert "```python\n**not bold**\n```" in result
    assert "After *bold*" in result


def test_inline_code_preserved():
    text = "Use `**not bold**` for code"
    result = markdown_to_whatsapp(text)
    assert "`**not bold**`" in result


def test_mixed_formatting():
    text = "# Title\n\n**bold** and *italic* with ~~strike~~\n[link](url)"
    result = markdown_to_whatsapp(text)
    assert "*Title*" in result
    assert "*bold*" in result
    assert "_italic_" in result
    assert "~strike~" in result
    assert "link (url)" in result


def test_plain_text_unchanged():
    text = "Just plain text with no formatting."
    assert markdown_to_whatsapp(text) == text


def test_multiline_headers():
    text = "# First\n\nSome text\n\n## Second"
    result = markdown_to_whatsapp(text)
    assert "*First*" in result
    assert "*Second*" in result
    assert "Some text" in result
