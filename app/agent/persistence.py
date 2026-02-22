import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SESSIONS_DIR = _PROJECT_ROOT / "data" / "agent_sessions"


def _get_session_path(phone_number: str, session_id: str) -> Path:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    # Sanitize phone number to be safe for filenames
    safe_phone = "".join(c for c in phone_number if c.isdigit() or c == "+")
    return _SESSIONS_DIR / f"{safe_phone}_{session_id}.jsonl"


def append_to_session(phone_number: str, session_id: str, data: dict[str, Any]) -> None:
    """Append a round's data as a JSON line to the session's history file."""
    path = _get_session_path(phone_number, session_id)
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")
    except Exception as e:
        logger.error("Failed to append to session %s: %s", session_id, e)


def load_session_history(phone_number: str, session_id: str) -> list[dict[str, Any]]:
    """Load the full history of a session from its JSONL file."""
    path = _get_session_path(phone_number, session_id)
    history = []
    if not path.exists():
        return history

    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    history.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Corrupted line in session %s: %s", session_id, line[:50])
    except Exception as e:
        logger.error("Failed to load session %s: %s", session_id, e)

    return history


def get_latest_session_id(phone_number: str) -> str | None:
    """Find the most recent session ID for a given phone number."""
    if not _SESSIONS_DIR.exists():
        return None

    safe_phone = "".join(c for c in phone_number if c.isdigit() or c == "+")
    prefix = f"{safe_phone}_"

    files = []
    for p in _SESSIONS_DIR.glob(f"{prefix}*.jsonl"):
        files.append((p.stat().st_mtime, p))

    if not files:
        return None

    # Sort by modification time, newest first
    files.sort(reverse=True)
    latest_file = files[0][1]

    # Extract session_id from filename (format: {phone}_{session_id}.jsonl)
    filename = latest_file.name
    session_id = filename[len(prefix) : -len(".jsonl")]
    return session_id
