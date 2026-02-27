"""Debug tools for planner-orchestrator agent sessions.

Provides tools for introspecting conversations, traces, and tool outputs
to enable the dev-review workflow and general debugging.

register() receives: registry, repository, ollama_client (optional).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.database.repository import Repository
    from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

_SKILL_NAME = "debug"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_REPORTS_DIR = _PROJECT_ROOT / "data" / "debug_reports"


def register(
    registry: SkillRegistry,
    repository: Repository,
) -> None:
    """Register all debug tools into the skill registry."""

    async def review_interactions(phone_number: str, limit: int = 10) -> str:
        """Review recent interactions for a user, showing traces with anomaly indicators.

        Returns an overview of recent traces with scores, timing, and error flags.
        """
        try:
            traces = await repository.get_traces_by_phone(phone_number, limit=limit)
        except Exception:
            logger.exception("review_interactions failed")
            return "Error retrieving traces."

        if not traces:
            return f"No traces found for {phone_number}."

        lines = [f"*Recent interactions for {phone_number} ({len(traces)}):*\n"]
        for t in traces:
            trace_id = t["id"][:12]
            input_preview = (t["input_text"] or "")[:80]
            status = t["status"] or "unknown"
            score_info = ""
            if t["score_count"] and t["score_count"] > 0:
                min_s = t["min_score"]
                avg_s = t["avg_score"]
                flag = " ⚠️" if min_s is not None and min_s < 0.5 else ""
                score_info = f" | scores: min={min_s:.2f} avg={avg_s:.2f}{flag}"
            timestamp = (t["started_at"] or "")[:16]
            lines.append(
                f"- `{trace_id}` [{timestamp}] {status}{score_info}\n"
                f"  Input: {input_preview}"
            )

        return "\n".join(lines)

    async def get_tool_output_full(trace_id: str) -> str:
        """Get the full tool call details (input + output) for a specific trace.

        Shows all tool calls made during that trace with their complete inputs and outputs.
        """
        try:
            tool_calls = await repository.get_trace_tool_calls(trace_id)
        except Exception:
            logger.exception("get_tool_output_full failed")
            return "Error retrieving tool calls."

        if not tool_calls:
            return f"No tool calls found for trace {trace_id}."

        lines = [f"*Tool calls for trace `{trace_id[:12]}`({len(tool_calls)}):*\n"]
        for tc in tool_calls:
            name = tc["name"] or "unknown"
            status = tc["status"] or "?"
            latency = tc["latency_ms"]
            latency_str = f" ({latency}ms)" if latency else ""

            lines.append(f"**{name}** [{status}]{latency_str}")

            if tc["input"]:
                input_str = json.dumps(tc["input"], ensure_ascii=False)
                if len(input_str) > 300:
                    input_str = input_str[:300] + "..."
                lines.append(f"  Input: {input_str}")

            if tc["output"]:
                output_str = json.dumps(tc["output"], ensure_ascii=False)
                if len(output_str) > 500:
                    output_str = output_str[:500] + "..."
                lines.append(f"  Output: {output_str}")
            lines.append("")

        return "\n".join(lines)

    async def get_interaction_context(trace_id: str) -> str:
        """Get the full context (input, output, metadata, scores) for a specific trace.

        Deep-dive into a single interaction to understand what happened.
        """
        try:
            trace = await repository.get_trace_with_spans(trace_id)
        except Exception:
            logger.exception("get_interaction_context failed")
            return "Error retrieving trace context."

        if not trace:
            return f"Trace {trace_id} not found."

        lines = [
            f"*Trace `{trace['id'][:12]}`*",
            f"Phone: {trace['phone_number']}",
            f"Status: {trace['status']}",
            f"Started: {trace['started_at']}",
            f"Completed: {trace['completed_at']}",
            f"Type: {trace['message_type']}",
            "",
            f"**Input:** {trace['input_text'] or '(empty)'}",
            "",
        ]

        output = trace["output_text"] or "(empty)"
        if len(output) > 500:
            output = output[:500] + "..."
        lines.append(f"**Output:** {output}")

        if trace.get("metadata"):
            meta = trace["metadata"]
            if meta:
                lines.append(f"\n**Metadata:** {json.dumps(meta, ensure_ascii=False)[:300]}")

        if trace.get("scores"):
            lines.append("\n**Scores:**")
            for s in trace["scores"]:
                lines.append(
                    f"  - {s['name']}: {s['value']:.2f} (source: {s['source']})"
                    + (f" — {s['comment']}" if s.get("comment") else "")
                )

        if trace.get("spans"):
            lines.append(f"\n**Spans ({len(trace['spans'])}):**")
            for s in trace["spans"][:10]:  # Cap at 10
                lines.append(
                    f"  - {s['name']} [{s['kind']}] {s['status']} "
                    f"({s.get('latency_ms', '?')}ms)"
                )

        return "\n".join(lines)

    async def write_debug_report(
        title: str,
        content: str,
        phone_number: str = "",
    ) -> str:
        """Save a markdown debug report to data/debug_reports/.

        Returns the path to the saved report.
        """
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        # Generate filename from title
        slug = "".join(c if c.isalnum() or c == "-" else "-" for c in title.lower()).strip("-")
        slug = slug[:50]
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{slug}.md"
        filepath = _REPORTS_DIR / filename

        report_content = f"# {title}\n\n"
        if phone_number:
            report_content += f"**Phone:** {phone_number}\n"
        report_content += f"**Date:** {datetime.now(UTC).isoformat()}\n\n"
        report_content += content

        try:
            filepath.write_text(report_content, encoding="utf-8")
            logger.info("Debug report saved: %s", filepath)
            return f"Report saved to: {filepath.relative_to(_PROJECT_ROOT)}"
        except Exception as e:
            logger.exception("Failed to save debug report")
            return f"Error saving report: {e}"

    async def get_conversation_transcript(
        phone_number: str,
        limit: int = 20,
    ) -> str:
        """Read the actual conversation messages (user + assistant) for a phone number.

        Returns the conversation in chronological order as a readable transcript.
        """
        try:
            messages = await repository.get_conversation_transcript(phone_number, limit=limit)
        except Exception:
            logger.exception("get_conversation_transcript failed")
            return "Error retrieving conversation."

        if not messages:
            return f"No conversation found for {phone_number}."

        lines = [f"*Conversation transcript for {phone_number} ({len(messages)} messages):*\n"]
        for m in messages:
            role_label = "👤 User" if m["role"] == "user" else "🤖 Assistant"
            timestamp = (m["timestamp"] or "")[:16]
            content = m["content"]
            if len(content) > 300:
                content = content[:300] + "..."
            lines.append(f"[{timestamp}] {role_label}:\n{content}\n")

        return "\n".join(lines)

    # --- Register tools ---

    registry.register_tool(
        name="review_interactions",
        description=(
            "Review recent interactions for a user showing traces with scores "
            "and anomaly flags. Use this to get an overview before deep-diving."
        ),
        parameters={
            "type": "object",
            "properties": {
                "phone_number": {
                    "type": "string",
                    "description": "The target user's phone number as provided in your objective. Do NOT invent or guess this value.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of recent traces to show (default 10)",
                    "default": 10,
                },
            },
            "required": ["phone_number"],
        },
        handler=review_interactions,
        skill_name=_SKILL_NAME,
    )

    registry.register_tool(
        name="get_tool_output_full",
        description=(
            "Get the full tool call details (inputs + outputs) for a specific trace. "
            "Use this to see exactly what tools were called and what they returned."
        ),
        parameters={
            "type": "object",
            "properties": {
                "trace_id": {
                    "type": "string",
                    "description": "The trace ID to inspect",
                },
            },
            "required": ["trace_id"],
        },
        handler=get_tool_output_full,
        skill_name=_SKILL_NAME,
    )

    registry.register_tool(
        name="get_interaction_context",
        description=(
            "Deep-dive into a single interaction: input, output, metadata, scores, "
            "and spans. Use after review_interactions to investigate a specific trace."
        ),
        parameters={
            "type": "object",
            "properties": {
                "trace_id": {
                    "type": "string",
                    "description": "The trace ID to inspect",
                },
            },
            "required": ["trace_id"],
        },
        handler=get_interaction_context,
        skill_name=_SKILL_NAME,
    )

    registry.register_tool(
        name="write_debug_report",
        description=(
            "Save a markdown debug report to data/debug_reports/. "
            "Use this to document findings from a debugging session."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Report title",
                },
                "content": {
                    "type": "string",
                    "description": "Report body in markdown",
                },
                "phone_number": {
                    "type": "string",
                    "description": "Phone number being debugged (optional)",
                    "default": "",
                },
            },
            "required": ["title", "content"],
        },
        handler=write_debug_report,
        skill_name=_SKILL_NAME,
    )

    registry.register_tool(
        name="get_conversation_transcript",
        description=(
            "Read the actual conversation messages (user + assistant) for a phone number. "
            "Use this to understand what the user said and what the bot replied."
        ),
        parameters={
            "type": "object",
            "properties": {
                "phone_number": {
                    "type": "string",
                    "description": "The target user's phone number as provided in your objective. Do NOT invent or guess this value.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of recent messages to show (default 20)",
                    "default": 20,
                },
            },
            "required": ["phone_number"],
        },
        handler=get_conversation_transcript,
        skill_name=_SKILL_NAME,
    )
