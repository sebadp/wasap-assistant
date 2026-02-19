---
name: calculator
description: Evaluate mathematical expressions safely
version: 1
tools:
  - calculate
---
Use the `calculate` tool for any math the user asks about.

Supported operations:
- Arithmetic: +, -, *, /, ** (power), % (modulo), // (integer division)
- Functions: sqrt, sin, cos, tan, log, log10, abs, round, ceil, floor
- Constants: pi, e

Examples:
- "cuánto es 15% de 340" → calculate("340 * 0.15")
- "raíz de 144" → calculate("sqrt(144)")
- "2 elevado a la 10" → calculate("2 ** 10")

How to respond:
- Show the expression and the result clearly: "15% de 340 = *51*"
- For multi-step problems, break them down and calculate each step
- If the expression is invalid, explain what went wrong and suggest a correction
- Use the user's language (Spanish if they write in Spanish)
