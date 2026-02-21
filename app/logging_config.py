import logging
import os
import sys
import warnings

from pythonjsonlogger.json import JsonFormatter


def configure_logging(
    level: str = "INFO", json_format: bool = True, log_file: str = "data/wasap.log"
) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    stream_handler = logging.StreamHandler(sys.stderr)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")

    formatter: logging.Formatter
    if json_format:
        formatter = JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        )
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    stream_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    root.handlers.clear()
    root.addHandler(stream_handler)
    root.addHandler(file_handler)

    # Silence noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", message=".*unauthenticated requests.*HF Hub.*")
