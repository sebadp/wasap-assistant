# Testing: Web Fetch Fix — Puppeteer-first con fallback a mcp-server-fetch

## Tests automatizados

```bash
# Router: URL fast-path y categoría "fetch"
pytest tests/test_tool_router.py -v -k "fetch or url"

# MCP Manager: fetch mode tracking
pytest tests/test_mcp_manager.py -v
```

---

## Tests manuales

### Test 1: URL fetching básico con Puppeteer (camino feliz)

**Setup**: Puppeteer conectado (`enabled: true` en `mcp_servers.json`)

```
Qué dice la homepage de https://example.com
```

**Esperado**:
- Logs: `Fetch mode: puppeteer`
- El LLM llama `puppeteer_navigate(url="https://example.com")`
- Responde con el contenido real de la página (no "no puedo acceder")

**Verificar en logs**:
```bash
grep "fetch mode\|puppeteer_navigate\|Fetch mode" data/wasap.log
```

---

### Test 2: URL en mensaje con texto adicional

```
Mirá este artículo y dime el punto principal: https://news.ycombinator.com
```

**Esperado**:
- `classify_intent` retorna categorías que incluyen "fetch"
- LLM tiene `puppeteer_navigate` disponible
- Responde con resumen del contenido

---

### Test 3: Fallback a mcp-fetch cuando Puppeteer está desactivado

**Setup**: En `mcp_servers.json`, cambiar `"enabled": false` para puppeteer y `"enabled": true` para mcp-fetch. Reiniciar el servidor.

```
¿Qué dice https://example.com?
```

**Esperado**:
- Logs: `Fetch mode: mcp-fetch (Puppeteer unavailable...)`
- El sistema inyecta nota de sistema sobre Puppeteer no disponible
- El LLM usa `fetch_markdown` o `fetch` de mcp-fetch
- En la respuesta al usuario: mención breve de que el fetch es básico (sin JS)

---

### Test 4: Runtime fallback (Puppeteer conectado pero browser falla)

**Setup**: Puppeteer habilitado pero Node.js/Chrome no disponible en el container → el tool se registra pero falla en ejecución.

```
¿Qué hay en https://example.com?
```

**Esperado**:
- `puppeteer_navigate` se ejecuta pero retorna error (`success=False`)
- Logs: `Puppeteer tool puppeteer_navigate failed, retrying with mcp-fetch fallback`
- Resultado al LLM prefixado con `"[⚠️ Fallback a mcp-fetch — Puppeteer no respondió]"`

---

### Test 5: Sin ningún servidor fetch disponible

**Setup**: Ambos servidores desactivados en `mcp_servers.json`. Reiniciar.

```
¿Qué dice https://example.com?
```

**Esperado**:
- Logs: `Fetch mode: unavailable — no web browsing tools connected` (ERROR level)
- El LLM no tiene tools de fetch → responde explicando que no puede acceder a URLs
- No crash, no error 500

---

### Test 6: URL en mensaje clasificada correctamente (sin pasar a "none")

```
https://github.com/fastapi/fastapi
```

**Esperado** (mensaje con solo una URL):
- `classify_intent` fast-path detecta URL
- Retorna `["fetch"]` aunque el classifier diga "none"
- Logs: `URL detected but classifier returned 'none', overriding to ['fetch']`

---

## Verificación en logs

```bash
# Estado de fetch mode al inicializar
grep "Fetch mode\|fetch_mode" data/wasap.log | head -5

# Fallback runtime
grep "mcp-fetch fallback\|Puppeteer tool.*failed" data/wasap.log

# URL fast-path
grep "URL detected\|overriding.*fetch" data/wasap.log

# Categorías seleccionadas para un mensaje con URL
grep "Tool router: categories" data/wasap.log | grep fetch
```

---

## Verificación del registro de categoría "fetch"

Usar el tool `list_tool_categories` vía WhatsApp:
```
/agent list_tool_categories
```

**Esperado**: La categoría `"fetch"` aparece con las tools de Puppeteer (o mcp-fetch si es el fallback).

---

## Queries de DB (N/A)

Esta feature no usa SQLite — toda la configuración está en `mcp_servers.json` y en memoria.
