from app.formatting.splitter import split_message


def test_short_message_no_split():
    text = "Hello world"
    assert split_message(text) == [text]


def test_exact_max_length():
    text = "a" * 4096
    assert split_message(text) == [text]


def test_split_on_paragraph():
    text = "A" * 100 + "\n\n" + "B" * 100
    result = split_message(text, max_length=120)
    assert len(result) == 2
    assert result[0] == "A" * 100
    assert result[1] == "B" * 100


def test_split_on_sentence():
    text = "First sentence. Second sentence. Third sentence."
    result = split_message(text, max_length=35)
    assert len(result) >= 2
    assert result[0].endswith(".")


def test_split_on_space():
    text = "word " * 50
    result = split_message(text.strip(), max_length=30)
    assert all(len(chunk) <= 30 for chunk in result)


def test_hard_cut_no_spaces():
    text = "a" * 200
    result = split_message(text, max_length=50)
    assert len(result) == 4
    assert all(len(chunk) == 50 for chunk in result)


def test_multiple_paragraphs():
    paragraphs = ["Para " + str(i) + " content." for i in range(5)]
    text = "\n\n".join(paragraphs)
    result = split_message(text, max_length=40)
    assert len(result) > 1


def test_empty_string():
    assert split_message("") == [""]


def test_split_preserves_all_content():
    text = "Hello world, this is a test message with some content."
    chunks = split_message(text, max_length=20)
    reconstructed = " ".join(chunks)
    # All words should be present
    for word in text.split():
        assert word in reconstructed
