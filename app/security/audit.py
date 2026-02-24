import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AuditEntry(BaseModel):
    timestamp: str
    tool_name: str
    arguments: dict[str, Any]
    decision: str
    decision_reason: str | None
    execution_result: str | None = None
    previous_hash: str
    entry_hash: str


class AuditTrail:
    """Append-only cryptographic audit log for all sensitive tool executions."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self._last_hash = self._initialize_log()

    def _initialize_log(self) -> str:
        """Ensures the file exists and returns the hash of the last entry."""
        if not self.log_path.exists():
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.touch()
            return "0000000000000000000000000000000000000000000000000000000000000000"

        last_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        try:
            with open(self.log_path) as f:
                lines = f.readlines()
                if lines:
                    last_line = lines[-1].strip()
                    if last_line:
                        data = json.loads(last_line)
                        last_hash = data.get("entry_hash", last_hash)
        except Exception as e:
            logger.error(f"Error reading audit log: {e}")

        return last_hash

    def _calculate_hash(self, payload: dict) -> str:
        """Calculates SHA-256 hash of the payload."""
        payload_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    def record(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        decision: str,
        decision_reason: str | None,
        execution_result: str | None = None,
    ) -> AuditEntry:
        """Appends a new record to the audit trail with a rolling hash."""
        timestamp = datetime.utcnow().isoformat() + "Z"

        payload_to_hash = {
            "timestamp": timestamp,
            "tool_name": tool_name,
            "arguments": arguments,
            "decision": decision,
            "decision_reason": decision_reason,
            "execution_result": execution_result,
            "previous_hash": self._last_hash,
        }

        entry_hash = self._calculate_hash(payload_to_hash)

        # Complete entry
        entry = AuditEntry(
            timestamp=timestamp,
            tool_name=tool_name,
            arguments=arguments,
            decision=decision,
            decision_reason=decision_reason,
            execution_result=execution_result,
            previous_hash=self._last_hash,
            entry_hash=entry_hash,
        )

        try:
            with open(self.log_path, "a") as f:
                f.write(entry.model_dump_json() + "\n")
            self._last_hash = entry_hash
        except Exception as e:
            logger.error(f"Failed to write to audit log: {e}")

        return entry
