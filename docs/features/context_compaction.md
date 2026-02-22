# Context Compaction System

This document outlines the **Context Compaction** architecture, introduced in 2026 to address the inherent limitations of LLM context windows when dealing with massive data sources (like those returned by external MCP tools such as `search_repositories`).

## The Problem: "Context Rot" & Hardware Limits

When an LLM agent uses external tools to retrieve information (for example, fetching a user's repositories from GitHub), the tools often return huge JSON payloads containing dozens of fields and metadata points. 

1. **Context Overflow**: If the payload exceeds the physical context window limit (e.g. `4000` tokens), the prompt is strictly truncated. A truncation occurring in the middle of a JSON string inevitably corrupts its syntax.
2. **Context Rot (The "Lost in the Middle" problem)**: Even if the LLM possesses a massive context window (e.g. 1 Million tokens), stuffing unoptimized raw JSON payloads degrades its attention mechanism. The LLM loses track of the original user request and often hallucinates responses by blindly autocompleting the JSON structure instead of answering.

## The Solution: Intelligent Summarization

Instead of blindly taking a massive JSON payload and truncating it structurally, we pipe overflowing tool outputs through an auxiliary fast LLM pass *before* feeding it to the main agent loop.

The `compact_tool_output` utility (located in `app/formatting/compaction.py`) executes as follows:

1. **Threshold Detection**: It checks if the tool output length exceeds a critical limit (default: 4000 characters). 
   - If `len(output) <= 4000`, it bypasses the compactor.
2. **Prompt Construction**: It dynamically builds an auxiliary prompt combining three elements:
   - The tool name (`search_repositories`).
   - The user's original objective/request (e.g., *"Look at my latest repositories"*).
   - The raw, massive JSON payload.
3. **Execution**: A fast LLM call (ideally with reasoning `<think>` tags disabled explicitly for efficiency) processes this prompt. The model's explicit instruction is to **summarize the payload extracting ONLY the fields that matter for the original user request** and ignoring boilerplate metadata.
4. **Context Injection**: The resulting summary (e.g., *"I found 49 repos. The most relevant ones are X, Y, and Z. There is more specific data if needed."*) replaces the original massive payload in the conversation history.

### Advantages
- **Preserves Attention**: The main agent loop only reads highly relevant, dense information, keeping its attention span intact.
- **Prevents Hallucinations**: Because the JSON isn't suddenly truncated leaving trailing brackets, the LLM no longer attempts to "guess" or "autocomplete" missing structures.
- **Improved UX**: The LLM organically informs the user that there's more information available beneath the summary, encouraging a progressive disclosure chat flow.

## Managing Reasoning Models (`<think>` tags)

Modern reasoning models (such as `DeepSeek-R1` and `Qwen-R1` variants) output "thinking" traces inside `<think>...</think>` tags to structure their logic before emitting a user-facing response. 

When the Auto-Debug mode focuses the assistant on complex trace-logic, the `<think>` blocks grow exceedingly large. If this response spills over the context window, the trailing `</think>` tag might be lost, or the raw tags might leak to the WhatsApp interface.

### Client-Side Cleanup 
To prevent these leaks and ensure clean context history, `app/llm/client.py` implements a hard Regex strip **before** the message is added to the log or sent to the user:
```python
content = re.sub(r"<think>.*?</think>\n*", "", content, flags=re.DOTALL)
content = content.split("</think>")[-1]
content = content.split("<think>")[0].strip()
```
This guarantees reasoning models act exactly like standard chat models from the perspective of the broader routing application.
