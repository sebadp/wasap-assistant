"""Export the eval dataset to JSONL for offline evaluation."""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def export_to_jsonl(
    repository: object,
    output_path: Path,
    entry_type: str | None = None,
    limit: int = 1000,
) -> int:
    """Export dataset entries to a JSONL file.

    Each line is a JSON object with keys:
        id, trace_id, entry_type, input, output, expected_output, metadata, created_at

    Returns the number of entries exported.
    """
    entries = await repository.get_dataset_entries(  # type: ignore[attr-defined]
        entry_type=entry_type,
        limit=limit,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            record = {
                "id": entry["id"],
                "trace_id": entry["trace_id"],
                "entry_type": entry["entry_type"],
                "input": entry["input_text"],
                "output": entry["output_text"],
                "expected_output": entry["expected_output"],
                "metadata": entry["metadata"],
                "created_at": entry["created_at"],
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info("Exported %d dataset entries to %s", len(entries), output_path)
    return len(entries)
