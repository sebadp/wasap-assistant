# Feature: Web Fetch Fix — Puppeteer-first con fallback a mcp-server-fetch

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-25
> **Fase**: Agent Mode
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Corrige el bug crítico de URL fetching: antes, el asistente recibía 0 tools cuando detectaba una URL porque la categoría "fetch" no estaba mapeada a ninguna herramienta real. Ahora, Puppeteer se registra automáticamente bajo la categoría "fetch" al inicializar, y mcp-server-fetch actúa como fallback cuando Puppeteer no está disponible. El sistema también notifica al usuario cuando está usando el fallback (sin renderizado JavaScript).

---

## Arquitectura

```
[Usuario: "¿Qué dice esta página? https://ejemplo.com"]
        │
        ▼
[classify_intent] ─── URL detectada via regex fast-path
        │              → categoría "fetch" forzada
        ▼
[select_tools("fetch")] ─── TOOL_CATEGORIES["fetch"]
        │                    → puppeteer_navigate, puppeteer_screenshot, puppeteer_evaluate
        ▼
[LLM: llama puppeteer_navigate(url=...)]
        │
        ├── Éxito: retorna contenido de la página
        │
        └── Falla (Puppeteer no conectado):
                │
                ▼
            [Runtime fallback en _run_tool_call()]
                │── result.success=False + tool es puppeteer_*
                ▼
            [mcp-fetch: fetch_markdown(url=...)]
                │── prefixea resultado con "[⚠️ Fallback a mcp-fetch...]"
                ▼
            [Notificación al usuario: "usando fetch básico"]
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/mcp/manager.py` | `_fetch_mode`, `get_fetch_mode()`, `_register_fetch_category()` |
| `app/skills/router.py` | URL fast-path en `classify_intent()`, `register_dynamic_category()` |
| `app/skills/executor.py` | Runtime fallback Puppeteer → mcp-fetch en `_run_tool_call()` |
| `app/webhook/router.py` | Notificación de fallback en `_run_normal_flow()` |
| `app/config.py` | `system_prompt` — instrucción genérica (sin mencionar tools específicas) |
| `data/mcp_servers.json` | Configuración de Puppeteer (primario) + mcp-server-fetch (fallback) |

---

## Walkthrough técnico: cómo funciona

### Bug original (pre-fix)

1. Usuario envía URL → `classify_intent()` fuerza categoría `["fetch"]`
2. `select_tools(["fetch"], all_tools_map)` → `TOOL_CATEGORIES.get("fetch", [])` → `[]`
3. No hay tools disponibles → LLM responde sin acceso a la página → **fail silencioso**

### Fix: registro de categoría "fetch"

1. `McpManager.initialize()` conecta todos los servidores (Puppeteer + mcp-fetch)
2. Al final de `initialize()`, llama `_register_fetch_category()`
3. `_register_fetch_category()` detecta herramientas disponibles:
   - Si hay tools de Puppeteer → `register_dynamic_category("fetch", puppeteer_tools)` → `_fetch_mode = "puppeteer"`
   - Si hay tools de mcp-fetch → `register_dynamic_category("fetch", mcp_fetch_tools)` → `_fetch_mode = "mcp-fetch"`
   - Sin ninguna → `_fetch_mode = "unavailable"`
4. Ahora `TOOL_CATEGORIES["fetch"]` tiene tools reales → `select_tools()` las encuentra

### Runtime fallback (Puppeteer falla en ejecución)

1. `_run_tool_call()` ejecuta `puppeteer_navigate(url=...)`
2. Resultado: `result.success=False` (error de conexión al browser)
3. Condición: `tool_name.startswith("puppeteer_")` AND `not result.success` AND mcp-fetch tools available
4. Se busca tool equivalente: `fetch_markdown` > `fetch` > `fetch_txt`
5. Se ejecuta `fetch_markdown(url=url)` via mcp-fetch
6. Resultado prefixado con `"[⚠️ Fallback a mcp-fetch — Puppeteer no respondió]\n"`

### Notificación al usuario (modo mcp-fetch activo)

1. `_run_normal_flow()` detecta: `has_url_in_msg AND get_fetch_mode() == "mcp-fetch"`
2. Inyecta `ChatMessage(role="system", content="NOTA DEL SISTEMA: Puppeteer no está disponible. ...")` al contexto
3. El LLM incluye brevemente en su respuesta que está usando fetch básico sin JS

---

## Cómo extenderla

- **Para agregar otro servidor fetch**: agregar en `_register_fetch_category()` la detección de sus tools y actualizar la prioridad
- **Para cambiar Puppeteer a habilitado/deshabilitado**: editar `data/mcp_servers.json` → campo `"enabled"`
- **Para forzar un fetch mode específico**: desactivar el servidor no deseado en `mcp_servers.json`

---

## Guía de testing

→ Ver [`docs/testing/25-web_fetch_fix_testing.md`](../testing/25-web_fetch_fix_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Registrar "fetch" dinámicamente (no hardcodeado en TOOL_CATEGORIES) | Hardcodear herramientas en el dict estático | Los nombres de tools de Puppeteer solo se conocen en runtime (son registradas por el servidor MCP) |
| Puppeteer como primario, mcp-fetch como fallback | mcp-fetch como primario | Puppeteer renderiza JavaScript → páginas SPA, Twitter, etc. funcionan; mcp-fetch solo ve HTML estático |
| Runtime fallback en `_run_tool_call` (no en el LLM) | Dejar que el LLM decida cuándo reintentar | El LLM no sabe si hay una alternativa disponible; el fallback transparente es UX más limpia |
| System_prompt genérico (sin mencionar tool names específicos) | System_prompt con `fetch_markdown` hardcodeado | El nombre de la tool cambia según el servidor activo; el prompt genérico es más robusto |

---

## Gotchas y edge cases

- **Ambos servidores no conectados**: `_fetch_mode = "unavailable"` + log ERROR + el LLM responde sin herramientas de fetch (igual que antes del fix, pero ahora logueado)
- **URL con path compleja**: el regex detecta la URL pero la extracción del `url` arg para el fallback usa `arguments.get("url")` — funciona si el LLM pasa el arg como "url"
- **mcp-server-fetch no instalado (npx falla)**: el servidor no conecta → no se registra en mcp-fetch tools → fallback no disponible → modo Puppeteer-only o unavailable
- **Puppeteer conectado pero browser no iniciado**: el tool puede fallar en ejecución (success=False) → activa el runtime fallback

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `mcp_config_path` | `"data/mcp_servers.json"` | Path al JSON de configuración de servidores MCP |
| `system_prompt` | ver `config.py` | Instrucción genérica para usar URL tools (sin mencionar tool names) |
