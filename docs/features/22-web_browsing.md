# Feature: Web Browsing & URL Fetching

> **Versión**: v1.1
> **Fecha de implementación**: 2026-02-24
> **Fase**: Fase 2+
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Permite que el agente resuelva consultas basadas en enlaces (URLs) enviados por el usuario de forma directa o dentro de un mensaje. Cuando el usuario comparte cualquier enlace web (LinkedIn, noticias, GitHub, GDrive público), el sistema detecta de forma determinista la intención de consulta a internet (`fetch`) y obliga al LLM a intentar leer el contenido mediante herramientas conectadas (como un navegador de Puppeteer vía MCP) en lugar de negarse por supuestas restricciones de privacidad.

---

## Arquitectura

El flujo prioriza la confiabilidad, combinando una validación determinista por Expresiones Regulares con la flexibilidad del intent classifier basado en LLM.

```
[Usuario envía URL]
        │
        ▼
[app/skills/router.py]
  ├──> Regex detecta URL en el mensaje
  ├──> LLM evalúa contexto (si es necesario otras tools)
  └──> Se fuerza "fetch" categoría
        │
        ▼
[app/skills/executor.py]
  ├──> Inyecta dependencias (Puppeteer MCP Tool / fetch skills)
  ├──> System Prompt global fuerza uso de la tool antes de responder
  └──> LLM ejecuta tool y resume/analiza
        │
        ▼
[Extracción & Respuesta]
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/skills/router.py` | Implementa el `Fast-Path` usando Regex (`re.compile(r"https?://...")`) para inyectar obligatoriamente la categoría `fetch` si hay URL. |
| `app/config.py` | Contiene el `system_prompt` modificado con directivas de selección de herramientas (`fetch_markdown`, `max_length=40000`) y el `compaction_threshold`. |
| `app/formatting/compaction.py` | Implementa los umbrales dinámicos (`Settings().compaction_threshold`) para evitar el cuello de botella previo con resúmenes innecesarios de HTML por el LLM local. |
| `data/mcp_servers.json` | Proveedor oficial de la capability de navegación, usando `@modelcontextprotocol/server-puppeteer`. |

---

## Walkthrough técnico: cómo funciona

1. **Recepción del Mensaje**: El webhook recibe el texto y se lo pasa al ciclo del agente (`app/agent/loop.py`).
2. **Clasificación de Intención (Fast-Path)**: `classify_intent` revisa si el mensaje contiene una URL de internet (`http/s`). Independientemente de lo que diga el modelo LLM, si existe una URL, se apendiza el string `"fetch"` a las categorías aprobadas (`router.py:192-195`).
3. **Selección de Herramientas**: La función `select_tools` mira la categoría "fetch" y añade el esquema de ejecución (por ej. `puppeteer_navigate`) de `_cached_tools_map` al payload de herramientas.
4. **Instrucciones Restrictivas**: Durante el armado del payload en `executor.py`, el LLM lee el Custom System Prompt: *"CRITICAL: When the user provides a URL... you MUST ALWAYS attempt to use them to read the URL before responding"*.
5. **Ejecución y Compactación**: La herramienta (Puppeteer) descarga el DOM optimizado, se comprime si es demasiado grande, y retorna al contexto para que el LLM formule su respuesta final.

---

## Guía de testing

→ Ver [`docs/testing/22-web_browsing_testing.md`](../testing/22-web_browsing_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Mapeo por Regex de URLs pre-LLM | Depender exclusivamente del LLM para clasificar URLs como `fetch` | Los LLMs livianos (Qwen3:8b) a veces agrupan URLs en `news` o `files` por el layout de la request ("share.google..."), lo que causa que la tool correcta nunca llegue a contexto. |
| Preferir `fetch_markdown` con `max_length` y aumentar `compaction_threshold` | Dejar que el LLM decida cómo usar `fetch_html` | El servidor MCP provee una trunca por default de 5000 chars que rompe las páginas complejas, y el HTML sucio forzaba a la app a usar el modelo local para compactarlo estresando el Event Loop. |

---

## Gotchas y edge cases

- **Manejo de Respuestas de Citas Evasivas**: Incluso con el system prompt modificado, el agente puede fallar si la herramienta (Browser Headless) es bloqueada (ej. un HTTP 403 explícito de Cloudflare). En este caso, **ahora es la herramienta quien falla, no el agente de forma prematura**. El LLM entonces reportará ese fallo real de la herramienta al usuario, lo cual es la "Graceful Degradation" esperada.
- **URLs sin http/s**: El Fast-Path requiere explícitamente que la URL tenga el prefijo `http://` o `https://`. Si el usuario envía `www.google.com`, el LLM clásico debe identificarlo por comprensión deductiva; caso contrario fallará la selección obligatoria de `fetch`.
