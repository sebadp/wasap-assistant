import json
import logging

from app.logging_config import configure_logging


def test_json_logging(capsys):
    configure_logging(level="INFO", json_format=True)
    logger = logging.getLogger("test.json")
    logger.info("hello json")

    captured = capsys.readouterr()
    record = json.loads(captured.err.strip())
    assert record["message"] == "hello json"
    assert record["level"] == "INFO"
    assert record["logger"] == "test.json"
    assert "timestamp" in record


def test_plain_logging(capsys):
    configure_logging(level="INFO", json_format=False)
    logger = logging.getLogger("test.plain")
    logger.info("hello plain")

    captured = capsys.readouterr()
    line = captured.err.strip()
    assert "hello plain" in line
    assert "test.plain" in line
    # Should NOT be JSON
    try:
        json.loads(line)
        assert False, "Expected plain text, got JSON"
    except json.JSONDecodeError:
        pass


def test_log_level_filtering(capsys):
    configure_logging(level="WARNING", json_format=True)
    logger = logging.getLogger("test.level")
    logger.info("should not appear")
    logger.warning("should appear")

    captured = capsys.readouterr()
    lines = [l for l in captured.err.strip().splitlines() if l]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["message"] == "should appear"
