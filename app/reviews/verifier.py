"""Multi-pass verification — Pass 2 of the review pipeline (Plan 64).

Each finding from Pass 1 is challenged by a second LLM call that tries to
argue it's a false positive.  Only findings that survive verification are kept.
"""

from __future__ import annotations

import json
import logging
import re

from app.llm.client import OllamaClient
from app.models import ChatMessage
from app.reviews.models import (
    DiffFile,
    ReviewFinding,
    Severity,
    VerificationResult,
)
from app.reviews.prompts import VERIFY_SYSTEM
from app.reviews.reviewer import _file_diff_text

logger = logging.getLogger(__name__)


def _extract_json(raw: str) -> str:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", raw)
    if m:
        return m.group(1).strip()
    return raw


async def verify_finding(
    finding: ReviewFinding,
    file: DiffFile,
    client: OllamaClient,
    model: str | None = None,
    repo_context: str = "",
) -> VerificationResult:
    """Run Pass 2 verification on a single finding."""
    diff_text = _file_diff_text(file)
    ctx = f"Repository context:\n{repo_context}" if repo_context else ""

    prompt = VERIFY_SYSTEM.format(
        path=finding.path,
        line=finding.line,
        severity=finding.severity.value,
        category=finding.category.value,
        body=finding.body,
        suggestion=finding.suggestion or "(none)",
        diff=diff_text,
        repo_context=ctx,
    )

    messages = [ChatMessage(role="user", content=prompt)]
    raw = await client.chat(messages, model=model, think=False)

    try:
        data = json.loads(_extract_json(raw))
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse verify JSON for %s:%d", finding.path, finding.line)
        # Default: keep the finding as-is
        return VerificationResult(is_valid=True, confidence=finding.confidence, reasoning="")

    revised = None
    if data.get("revised_severity"):
        try:
            revised = Severity(data["revised_severity"])
        except ValueError:
            pass

    return VerificationResult(
        is_valid=bool(data.get("is_valid", True)),
        confidence=float(data.get("confidence", finding.confidence)),
        reasoning=data.get("reasoning", ""),
        revised_severity=revised,
    )


async def verify_findings(
    findings: list[ReviewFinding],
    files: list[DiffFile],
    client: OllamaClient,
    model: str | None = None,
    repo_context: str = "",
    min_confidence: float = 7.0,
) -> list[ReviewFinding]:
    """Verify all findings, filtering out false positives and adjusting severity."""
    if not findings:
        return []

    # Build path → file lookup
    file_map = {f.path: f for f in files}

    verified: list[ReviewFinding] = []
    for finding in findings:
        file = file_map.get(finding.path)
        if not file:
            continue

        result = await verify_finding(
            finding, file, client, model=model, repo_context=repo_context
        )

        if not result.is_valid:
            logger.info(
                "Filtered false positive: %s:%d — %s", finding.path, finding.line, result.reasoning
            )
            continue

        if result.confidence < min_confidence:
            logger.info(
                "Filtered low-confidence: %s:%d (%.1f)", finding.path, finding.line, result.confidence
            )
            continue

        # Apply revised severity if downgraded
        if result.revised_severity:
            finding.severity = result.revised_severity

        # Update confidence from verification pass
        finding.confidence = result.confidence
        verified.append(finding)

    return verified
