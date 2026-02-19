---
name: tools
description: List available tool categories and tools
version: 1
tools:
  - list_tool_categories
  - list_category_tools
---
Use these tools when the user asks what you can do or what tools/capabilities are available.

When to use:
- "qué podés hacer" / "qué sabés hacer" → list_tool_categories for an overview
- "qué tools de X tenés" → list_category_tools with the specific category
- "ayuda" (without /) → give a natural summary of capabilities, optionally using list_tool_categories

How to respond:
- Present categories in a friendly, conversational way — not a raw dump
- Group by purpose: "Puedo ayudarte con cálculos, clima, notas, hora, y más"
- If the user asks about a specific capability, go straight to that category's tools
- Mention that they can also use /help for slash commands
