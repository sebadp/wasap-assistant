---
name: debug
description: Debug and analyze user interactions with planner-orchestrator support
version: 1
tools:
  - review_interactions
  - get_tool_output_full
  - get_interaction_context
  - write_debug_report
  - get_conversation_transcript
---
Use these tools to investigate user interactions and diagnose issues.
- Start with get_conversation_transcript(phone) to read what the user said and what the bot replied.
- Use review_interactions(phone) to get an overview of recent traces with anomaly flags.
- For traces with low scores (< 0.5), use get_interaction_context(trace_id) for full details.
- Use get_tool_output_full(trace_id) to see exactly what tools were called and their outputs.
- After analysis, use write_debug_report(title, content) to save your findings.
- Never guess trace IDs — always get them from review_interactions() first.
- Focus on actionable findings: what went wrong, why, and how to fix it.
