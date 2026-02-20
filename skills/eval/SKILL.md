---
name: eval
description: Self-evaluation and continuous improvement tools
version: 1
tools:
  - get_eval_summary
  - list_recent_failures
  - diagnose_trace
  - propose_correction
  - add_to_dataset
  - get_dataset_stats
  - run_quick_eval
  - propose_prompt_change
  - get_dashboard_stats
---
Use these tools to analyze your own performance and improve over time.
- Use get_eval_summary() for an overview of recent performance metrics (scores, failure rates).
- Use get_dashboard_stats() for a comprehensive view: daily failure trend + score distribution per guardrail check.
- Use list_recent_failures() to see traces where guardrails or users flagged issues.
- Use diagnose_trace(trace_id) to deep-dive into a specific interaction: spans, scores, input/output.
- Use propose_correction(trace_id, correction) to record what you should have said instead.
- Use add_to_dataset(trace_id, entry_type) to manually curate traces (golden/failure/correction).
- Use get_dataset_stats() to see dataset composition and coverage.
- Use run_quick_eval(category) to run a quick evaluation against the dataset for a category.
- Use propose_prompt_change(prompt_name, diagnosis, proposed_change) to generate a prompt modification draft.
- Never fabricate trace_ids — always get them from list_recent_failures() or diagnose_trace().
- After propose_prompt_change(), tell the user to review with /approve-prompt <name> <version>.
