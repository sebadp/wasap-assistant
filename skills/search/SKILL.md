---
name: search
description: Search the internet for real-time information
tools:
  - web_search
---

Use the `web_search` tool when the user asks for current events, news, facts that you don't know, or specific information that requires internet access (e.g. "who won the game yesterday?", "find a recipe for...").
Do NOT use this tool for weather (use `get_weather` instead) or simple calculations.

**Time Sensitivity**: You know the current date from the system prompt (e.g. "Current Date: 2024-05-20"). Use it to contextualize relative time expressions like "last week" or "today" in your search queries. For example, if today is 2024-05-20 and user asks for "news from last week", search for "news 2024-05-13..2024-05-20" or similar specific terms.

Summarize the search results for the user.
