from unittest.mock import MagicMock, patch

import pytest

from app.audio.transcriber import Transcriber


@pytest.fixture
def mock_transcriber():
    with patch("app.audio.transcriber.WhisperModel") as mock_cls:
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.text = " Hello world "
        mock_model.transcribe.return_value = ([mock_segment], MagicMock())
        mock_cls.return_value = mock_model

        t = Transcriber(model_size="base", device="cpu", compute_type="int8")
        yield t


def test_transcribe_sync(mock_transcriber):
    result = mock_transcriber.transcribe(b"fake-audio-data")
    assert result == "Hello world"


async def test_transcribe_async(mock_transcriber):
    result = await mock_transcriber.transcribe_async(b"fake-audio-data")
    assert result == "Hello world"


def test_transcribe_multiple_segments():
    with patch("app.audio.transcriber.WhisperModel") as mock_cls:
        mock_model = MagicMock()
        seg1 = MagicMock()
        seg1.text = " Hello "
        seg2 = MagicMock()
        seg2.text = " world "
        mock_model.transcribe.return_value = ([seg1, seg2], MagicMock())
        mock_cls.return_value = mock_model

        t = Transcriber(model_size="base")
        result = t.transcribe(b"fake-audio")
        assert result == "Hello world"
