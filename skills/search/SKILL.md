---
name: search
description: Search the internet and read web pages
tools:
  - web_search
---

Use the `web_search` tool when the user asks for current events, news, facts that you don't know, or specific information that requires internet access (e.g. "who won the game yesterday?", "find a recipe for...").
Do NOT use this tool for weather (use `get_weather` instead) or simple calculations.

**Time Sensitivity**: You know the current date from the system prompt. Use it to contextualize relative time expressions like "last week" or "today" in your search queries.

**Web Browsing / Reading URLs**:
Si el usuario envía un hipervínculo (URL, link) directamente en el chat y te pide leerlo o revisarlo, **no asumas que sabes lo que tiene**. Debes usar las herramientas del servidor MCP `puppeteer` para visitarlo.
1. Utiliza `puppeteer_navigate` para ir a la URL enviada (asegúrate de incluir el `http://` o `https://`).
2. Luego utiliza `puppeteer_evaluate` o las herramientas pertinentes de extracción del DOM para leer el contenido principal de la vista. Extract text content specifically.
3. Si la página es muy compleja, evalúa su texto renderizado (`document.body.innerText`).
4. Resume el contenido o responde a la pregunta del usuario basándote en lo que leíste.

Summarize the search/browse results for the user.
