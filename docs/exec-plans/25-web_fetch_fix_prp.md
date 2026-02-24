# PRP: Web Fetching, Intent Classification, and Compaction Fix

This plan outlines the execution steps for resolving the issue where the agent fails to fetch URLs and instead falls back to guessing context, and fixing the severe sluggishness caused by fetching HTML pages with hardcoded length limits and strict compaction.

## Objective & Architecture Decisions
- **Why it failed**: 
  1. The semantic intent classifier (`app.skills.router`) struggled to categorize single URLs into the `fetch` category reliably.
  2. The LLM preemptively refused to use tools for common domains.
  3. **New finding**: The `mcp-server-fetch` has a hardcoded default `max_length=5000`. When fetching full HTML, 5000 characters is mostly `<head>` boilerplate.
  4. **Latencies**: `wasap-assistant` summarization (`compaction.py`) kicks in at 4000 chars. Processing 5000 chars of garbage HTML took the local LLM ~2 minutes just to summarize nothing.
  
- **Design Decisions**:
  1. **Regex Pattern Fast-Path**: Specialized fast-path in `classify_intent` for URLs to enforce the `fetch` category.
  2. **System Prompt Override Directive**: Command the LLM to use `fetch_markdown` or `fetch_txt` rather than `fetch_html`, and to *always* specify a high `max_length` (e.g., 20000 or 40000).
  3. **Relax Compaction Tresholds**: Increase the `max_length` threshold in `compaction.py` from `4000` to a much larger value (e.g., `20000`) so the local LLM doesn't waste cycles on easily handleable payloads.

## Phase 1: Classification Regex Fast-Path
- [x] Modify `app/skills/router.py` to add a regex matching logic for HTTP/HTTPS URLs at the beginning of `classify_intent()`.
- [x] If a valid URL is detected as the primary intent, ensure `["fetch"]` is included in the categories list (or returned outright to save LLM tokens).
- [x] Add unit tests in `tests/` to verify that `classify_intent` effectively catches URLs and forces the `fetch` category routing.

## Phase 2: Execution Prompting & Instructions
- [x] Update `app/config.py` `system_prompt` defaults to include explicit tool directives: *"When the user provides a URL and you have fetch tools available, you MUST ALWAYS attempt to use them to read the URL before responding. Do NOT assume a page is private, requires login, or is inaccessible without trying the tool first."*
- [x] Also update `system_prompt` to strongly prefer `fetch_markdown` or `fetch_txt` over `fetch_html`, and instruct the LLM to ALWAYS pass a `max_length` parameter of at least 20000.

## Phase 3: Compaction Threshold Optimization
- [x] Update `app/config.py` to add `compaction_threshold` with a default of `20000`.
- [x] Modify `app/formatting/compaction.py` to use `Settings().compaction_threshold` instead of the hardcoded `4000`.

## Phase 4: Validation & Documentation
- [x] Test manually passing a LinkedIn/Anthropic URL to verify `executor.py` logs show the `fetch_html` tool being invoked.
- [x] Run `make check` to ensure no linting/typing regressions.
- [x] Document the updated behavior in `docs/features/22-web_browsing.md` (or similar feature file).
- [x] Update `docs/features/README.md` and check off tasks in this document to complete the 5-step documentation protocol.
