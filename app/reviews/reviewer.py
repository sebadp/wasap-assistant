"""LLM Review Pipeline — summary + line-by-line review per file (Plan 63-A).

Pattern: Single LLM call per file (Qodo), token budgeting, confidence filtering.
"""

from __future__ import annotations

import json
import logging
import re
import time

from app.llm.client import OllamaClient
from app.models import ChatMessage
from app.reviews.models import (
    Category,
    DiffFile,
    PullRequestInfo,
    ReviewFinding,
    ReviewSummary,
    RiskLevel,
    Severity,
)
from app.reviews.prompts import REVIEW_SYSTEM, SUMMARY_SYSTEM

logger = logging.getLogger(__name__)

# Rough chars-per-token estimate
_CHARS_PER_TOKEN = 3.5


def _estimate_tokens(text: str) -> int:
    return int(len(text) / _CHARS_PER_TOKEN)


def _file_diff_text(f: DiffFile) -> str:
    """Render a DiffFile back to unified diff text."""
    lines: list[str] = []
    for hunk in f.hunks:
        lines.append(
            f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@ {hunk.header}"
        )
        for dl in hunk.lines:
            if dl.type.value == "add":
                lines.append(f"+{dl.content}")
            elif dl.type.value == "remove":
                lines.append(f"-{dl.content}")
            else:
                lines.append(f" {dl.content}")
    return "\n".join(lines)


def _budget_files(files: list[DiffFile], max_tokens: int) -> tuple[list[DiffFile], list[str]]:
    """Select files to review within token budget (80%).

    Returns (files_to_review, overflow_file_names).
    """
    budget = int(max_tokens * 0.8)
    sorted_files = sorted(files, key=lambda f: f.additions + f.deletions, reverse=True)
    selected: list[DiffFile] = []
    overflow: list[str] = []
    used = 0
    for f in sorted_files:
        cost = _estimate_tokens(_file_diff_text(f))
        if used + cost <= budget:
            selected.append(f)
            used += cost
        else:
            overflow.append(f.path)
    return selected, overflow


# Prompts now centralized in app/reviews/prompts.py


async def _generate_summary(
    pr: PullRequestInfo,
    files: list[DiffFile],
    overflow: list[str],
    client: OllamaClient,
    model: str | None = None,
) -> tuple[str, str, RiskLevel, list[str]]:
    file_list = "\n".join(
        f"- {f.path} (+{f.additions}/-{f.deletions}) [{f.language}]" for f in files
    )
    if overflow:
        file_list += "\n\nAlso changed (not reviewed): " + ", ".join(overflow)

    user_msg = f"""PR #{pr.number}: {pr.title}
Author: {pr.author}
Branch: {pr.head_branch} → {pr.base_branch}
Description: {pr.description or "(none)"}

Files changed:
{file_list}"""

    messages = [
        ChatMessage(role="system", content=SUMMARY_SYSTEM),
        ChatMessage(role="user", content=user_msg),
    ]
    raw = await client.chat(messages, model=model, think=False)
    try:
        data = json.loads(_extract_json(raw))
    except (json.JSONDecodeError, ValueError):
        return pr.title, raw[:500], RiskLevel.medium, []

    risk_map = {
        "low": RiskLevel.low,
        "medium": RiskLevel.medium,
        "high": RiskLevel.high,
        "critical": RiskLevel.critical,
    }
    return (
        data.get("title", pr.title),
        data.get("overview", ""),
        risk_map.get(data.get("risk_level", "medium"), RiskLevel.medium),
        data.get("key_changes", []),
    )




async def _review_file(
    file: DiffFile,
    pr: PullRequestInfo,
    client: OllamaClient,
    language: str = "es",
    model: str | None = None,
    min_confidence: float = 0.6,
    max_findings: int = 10,
    repo_context: str = "",
) -> list[ReviewFinding]:
    diff_text = _file_diff_text(file)
    system = REVIEW_SYSTEM.format(language=language)
    if repo_context:
        system += f"\n\nREPOSITORY CONTEXT:\n{repo_context}"
    user_msg = f"""File: {file.path} ({file.language})
PR: #{pr.number} — {pr.title}
Description: {pr.description or "(none)"}

Diff:
```
{diff_text}
```"""

    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user_msg),
    ]
    raw = await client.chat(messages, model=model, think=False)
    return _parse_findings_json(raw, file, min_confidence, max_findings)


def _extract_json(raw: str) -> str:
    """Extract JSON from LLM output, stripping markdown fences if present."""
    raw = raw.strip()
    # Remove ```json ... ``` wrappers
    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", raw)
    if m:
        return m.group(1).strip()
    return raw


def _parse_findings_json(
    raw: str, file: DiffFile, min_confidence: float, max_findings: int
) -> list[ReviewFinding]:
    """Parse JSON array of findings from LLM output."""
    try:
        data = json.loads(_extract_json(raw))
    except (json.JSONDecodeError, ValueError):
        logger.warning("Failed to parse review JSON for %s", file.path)
        return []

    if not isinstance(data, list):
        return []

    # Collect valid line numbers from the diff
    valid_new_lines = set()
    valid_old_lines = set()
    for hunk in file.hunks:
        for dl in hunk.lines:
            if dl.new_line_no is not None:
                valid_new_lines.add(dl.new_line_no)
            if dl.old_line_no is not None:
                valid_old_lines.add(dl.old_line_no)

    findings: list[ReviewFinding] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        confidence = float(entry.get("confidence", 0))
        if confidence < min_confidence:
            continue

        line = int(entry.get("line", 0))
        side = entry.get("side", "RIGHT")
        # Validate line exists in diff
        if side == "RIGHT" and line not in valid_new_lines:
            continue
        if side == "LEFT" and line not in valid_old_lines:
            continue

        severity_str = entry.get("severity", "suggestion")
        category_str = entry.get("category", "maintainability")
        try:
            severity = Severity(severity_str)
        except ValueError:
            severity = Severity.suggestion
        try:
            category = Category(category_str)
        except ValueError:
            category = Category.maintainability

        findings.append(
            ReviewFinding(
                path=file.path,
                line=line,
                side=side,
                severity=severity,
                category=category,
                body=entry.get("body", ""),
                suggestion=entry.get("suggestion"),
                confidence=confidence,
                start_line=entry.get("start_line"),
                exploit_scenario=entry.get("exploit_scenario"),
            )
        )

    # Sort by severity priority, take top N
    severity_order = {
        Severity.critical: 0,
        Severity.warning: 1,
        Severity.suggestion: 2,
        Severity.nitpick: 3,
    }
    findings.sort(key=lambda f: severity_order.get(f.severity, 99))
    return findings[:max_findings]


async def review_pull_request(
    pr: PullRequestInfo,
    files: list[DiffFile],
    client: OllamaClient,
    model: str | None = None,
    language: str = "es",
    min_confidence: float = 0.6,
    min_severity: str = "suggestion",
    max_findings_per_file: int = 10,
    skip_generated: bool = True,
    context_budget_tokens: int = 16000,
    repo_context: str = "",
    clone_path: str = "",
    deep_context_budget: int = 3000,
    thorough: bool = False,
) -> ReviewSummary:
    """Run the full review pipeline: summary + per-file line-by-line review."""
    from pathlib import Path

    start = time.monotonic()

    # Filter generated files
    reviewable = [f for f in files if not (skip_generated and f.is_generated)]
    skipped = len(files) - len(reviewable)

    # Budget files
    selected, overflow = _budget_files(reviewable, context_budget_tokens)

    # Get trace context for observability (if running inside a traced request)
    from app.tracing.context import get_current_trace

    trace = get_current_trace()

    # Extract symbols for deep context (Phase C)
    symbols: list = []
    cp: Path | None = None
    if clone_path:
        from app.reviews.symbol_extractor import extract_symbols_from_diff

        symbols = extract_symbols_from_diff(selected)
        cp = Path(clone_path)
        if trace:
            async with trace.span("pr_review.symbol_extraction") as span:
                span.set_output({"files_analyzed": len(selected), "symbols_found": len(symbols)})

    # Pass 1: Summary
    if trace:
        async with trace.span("pr_review.summary", kind="generation") as span:
            span.set_input({"pr": pr.number, "files": len(selected), "overflow": len(overflow)})
            title, overview, risk_level, key_changes = await _generate_summary(
                pr, selected, overflow, client, model=model,
            )
            span.set_output({"title": title, "risk_level": risk_level.value})
    else:
        title, overview, risk_level, key_changes = await _generate_summary(
            pr, selected, overflow, client, model=model,
        )

    # Pass 2: Per-file review
    all_findings: list[ReviewFinding] = []
    for file in selected:
        # Build cross-file context if clone available
        file_context = repo_context
        if cp and symbols:
            from app.reviews.code_search import get_cross_file_context

            cross_ctx = await get_cross_file_context(
                file, symbols, cp, token_budget=deep_context_budget
            )
            if cross_ctx:
                file_context = (
                    (file_context + "\n\n" + cross_ctx).strip() if file_context else cross_ctx
                )

        if trace:
            async with trace.span(f"pr_review.file.{file.path}", kind="generation") as span:
                span.set_input({"path": file.path, "additions": file.additions, "deletions": file.deletions})
                findings = await _review_file(
                    file, pr, client, language=language, repo_context=file_context,
                    model=model, min_confidence=min_confidence, max_findings=max_findings_per_file,
                )
                span.set_output({"findings": len(findings)})
        else:
            findings = await _review_file(
                file, pr, client, language=language, repo_context=file_context,
                model=model, min_confidence=min_confidence, max_findings=max_findings_per_file,
            )
        all_findings.extend(findings)

    # Pass 3 (optional): Verify findings to filter false positives
    if thorough and all_findings:
        from app.reviews.verifier import verify_findings

        if trace:
            async with trace.span("pr_review.verify", kind="generation") as span:
                span.set_input({"findings_before": len(all_findings)})
                all_findings = await verify_findings(
                    all_findings, selected, client, model=model,
                    repo_context=repo_context, min_confidence=min_confidence,
                )
                span.set_output({"findings_after": len(all_findings)})
        else:
            all_findings = await verify_findings(
                all_findings, selected, client, model=model,
                repo_context=repo_context, min_confidence=min_confidence,
            )

    # Filter by minimum severity
    severity_threshold = {
        "critical": {Severity.critical},
        "warning": {Severity.critical, Severity.warning},
        "suggestion": {Severity.critical, Severity.warning, Severity.suggestion},
        "nitpick": {Severity.critical, Severity.warning, Severity.suggestion, Severity.nitpick},
    }
    allowed = severity_threshold.get(min_severity, severity_threshold["suggestion"])
    all_findings = [f for f in all_findings if f.severity in allowed]

    duration_ms = (time.monotonic() - start) * 1000

    stats: dict[str, int | float] = {
        "files_changed": pr.files_changed,
        "additions": pr.additions,
        "deletions": pr.deletions,
        "findings_total": len(all_findings),
        "critical": sum(1 for f in all_findings if f.severity == Severity.critical),
        "warnings": sum(1 for f in all_findings if f.severity == Severity.warning),
        "suggestions": sum(1 for f in all_findings if f.severity == Severity.suggestion),
        "nitpicks": sum(1 for f in all_findings if f.severity == Severity.nitpick),
    }

    return ReviewSummary(
        title=title,
        overview=overview,
        risk_level=risk_level,
        key_changes=key_changes,
        stats=stats,
        findings=all_findings,
        files_reviewed=len(selected),
        files_skipped=skipped + len(overflow),
        duration_ms=duration_ms,
    )
