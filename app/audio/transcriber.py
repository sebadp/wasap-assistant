import asyncio
import logging
import os
import tempfile

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
        logger.info(
            "Loading Whisper model: %s (device=%s, compute=%s)", model_size, device, compute_type
        )
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes to text (synchronous)."""
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=True) as f:
            f.write(audio_bytes)
            f.flush()
            segments, _info = self._model.transcribe(f.name)
            result = " ".join(seg.text.strip() for seg in segments)
            logger.debug("Audio (Whisper) RAW INTERPRETATION: %r", result)
            return result

    async def transcribe_async(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes to text without blocking the event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.transcribe, audio_bytes)
