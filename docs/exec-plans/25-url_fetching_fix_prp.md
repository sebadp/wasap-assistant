# PRP: URL Fetching and Intent Classification Fix

This plan outlines the execution steps for resolving the issue where the agent fails to fetch URLs and instead falls back to guessing context. Reference the investigation and problem diagnosis for the underlying cause.

## Objective & Architecture Decisions
- **Why it failed**: 
  1. The semantic intent classifier (`app.skills.router`) struggles to categorize single URLs into the `fetch` category reliably (sometimes categorizing as `files`, `news`, or `none`).
  2. Even when correctly categorized and tools (`fetch_html`, etc.) are injected into the context, the LLM heavily hallucinates security restrictions on URLs from common domains like LinkedIn, Google Drive, or Instagram due to strict internal safeguard conditioning, preemptively refusing to use the tool.
  
- **Design Decisions**:
  1. **Regex Pattern Fast-Path**: We will implement a specialized fast-path in `classify_intent` that bypasses or augments the LLM classification if the message is a pure URL. This guarantees the `fetch` category (which maps to external MCP web scrapers or local fetch skills) is selected with zero LLM inference latency and 100% reliability.
  2. **System Prompt Override Directive**: To defeat the LLM's preemptive refusal, we will update the global system prompt to explicitly command the LLM to use the provided tools without assuming pages are private or inaccessible. Prompt engineering is the only way to bypass these overly-cautious RLHF restrictions.

## Phase 1: Classification Regex Fast-Path
- [x] Modify `app/skills/router.py` to add a regex matching logic for HTTP/HTTPS URLs at the beginning of `classify_intent()`.
- [x] If a valid URL is detected as the primary intent, ensure `["fetch"]` is included in the categories list (or returned outright to save LLM tokens).
- [ ] Add unit tests in `tests/` to verify that `classify_intent` effectively catches URLs and forces the `fetch` category routing.

## Phase 2: Execution Prompting & Instructions
- [x] Update `app/config.py` `system_prompt` defaults to include explicit tool directives: *"When the user provides a URL and you have fetch tools available, you MUST ALWAYS attempt to use them to read the URL before responding. Do NOT assume a page is private, requires login, or is inaccessible without trying the tool first."*
- [x] As an alternative/complement, update the description for `fetch*` tools natively in the fetch server or via the tool schema map in `app/skills/executor.py` so the LLM knows it is strictly required.

## Phase 3: Validation & Documentation
- [x] Test manually passing a LinkedIn/Anthropic URL to verify `executor.py` logs show the `fetch_html` tool being invoked.
- [x] Run `make check` to ensure no linting/typing regressions.
- [x] Document the updated behavior in `docs/features/22-web_browsing.md` (or similar feature file).
- [x] Update `docs/features/README.md` and check off tasks in this document to complete the 5-step documentation protocol.
