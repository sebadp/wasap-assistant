# Guía de Testing Manual — Skills & MCP

## Requisitos previos

- Container corriendo: `docker compose up --build -d`
- Ollama con `qwen3:8b` y `llava:7b` disponibles
- WhatsApp configurado (token, phone number ID, verify token, app secret en `.env`)
- Número de teléfono en `ALLOWED_PHONE_NUMBERS`
- Para MCP: `data/mcp_servers.json` con servers habilitados (`"enabled": true`)

### Verificar arranque

```bash
docker compose logs -f wasap | head -50
```

Buscar en los logs:
- `Skills loaded: N skill(s)` — skills de `skills/` cargados
- `Registered tool: <name>` — tools builtin registrados
- `MCP initialized: N server(s), M tool(s)` — MCP conectado
- `Scheduler started` — APScheduler activo

---

## 1. Calculator

**Objetivo**: Evaluar expresiones matemáticas de forma segura (AST, sin `eval()`).

| Mensaje | Respuesta esperada |
|---|---|
| `Cuánto es 15 * 7 + 3?` | 108 |
| `Raíz cuadrada de 144` | 12 |
| `sin(pi/2)` | 1.0 |
| `log(100)` | ~4.605 (ln natural) |
| `2 ** 10` | 1024 |

**Verificar error handling:**
- `Cuánto es import("os")` → debe rechazarlo sin ejecutar código

---

## 2. DateTime

**Objetivo**: Obtener fecha/hora actual y convertir entre zonas horarias.

| Mensaje | Respuesta esperada |
|---|---|
| `Qué hora es?` | Hora actual (UTC o local según system prompt) |
| `Qué hora es en Tokio?` | Hora en Asia/Tokyo |
| `Si acá son las 14:30, qué hora es en Londres?` | Conversión de timezone |

**Verificar:**
- Formato legible: `YYYY-MM-DD HH:MM:SS TZ`
- Timezone inválido → mensaje de error (no crash)

---

## 3. Weather

**Objetivo**: Clima actual y pronóstico via OpenMeteo (gratis, sin API key).

| Mensaje | Respuesta esperada |
|---|---|
| `Cómo está el clima en Buenos Aires?` | Temp, humedad, viento, descripción WMO, pronóstico |
| `Clima en El Soberbio, Misiones` | Idem, con localidad específica |
| `Weather in New York` | Funciona en inglés también |

**Verificar formato:**
```
Weather in Buenos Aires, Argentina:
  Partly cloudy, 25°C
  Humidity: 60%
  Wind: 15 km/h
  Today: 18°C - 28°C
  Precipitation chance: 20%
```

**Códigos WMO cubiertos:**
- 0: Clear sky
- 1-3: Partly cloudy
- 45, 48: Foggy
- 51, 53, 55: Drizzle
- 56, 57: Freezing drizzle
- 61, 63, 65: Rain
- 66, 67: Freezing rain
- 71, 73, 75: Snowfall
- 77: Snow grains
- 80-82: Rain showers
- 85, 86: Snow showers
- 95, 96, 99: Thunderstorm

---

## 4. Web Search

**Objetivo**: Búsqueda web via DuckDuckGo (`DDGS().text()`).

| Mensaje | Respuesta esperada |
|---|---|
| `Buscá recetas de empanadas` | Hasta 5 resultados con título, link, snippet |
| `Qué pasó hoy en el mundo?` | Resultados recientes (debería usar time_range) |
| `Search for Python 3.13 release notes` | Resultados en inglés |

**Verificar:**
- Formato: `1. [Título](URL): snippet`
- Máximo 5 resultados
- `time_range` opcional: `d` (día), `w` (semana), `m` (mes), `y` (año)
- Si falla DuckDuckGo → `"Error performing search: ..."`

---

## 5. News

**Objetivo**: Búsqueda de noticias via `DDGS().news()` con preferencias guardadas.

### 5a. Preferencias

| Mensaje | Respuesta esperada |
|---|---|
| `Me gusta leer Página 12` | Debe llamar `add_news_preference(source="Página 12", preference="like")` |
| `No me gusta Clarín` | Debe llamar `add_news_preference(source="Clarín", preference="dislike")` |

**Verificar:** `Memorized: You like Página 12.` (guardado en SQLite con category `news_pref`)

### 5b. Búsqueda de noticias

| Mensaje | Respuesta esperada |
|---|---|
| `Noticias sobre inteligencia artificial` | Resultados con fuente y fecha |
| `Qué pasó esta semana en Argentina?` | Debería usar `time_range="w"` |
| `Últimas noticias de tecnología` | Resultados recientes |

**Verificar formato:**
```
1. [Título](URL) — Fuente, 2026-02-15: Resumen del artículo

2. [Otro título](URL) — OtraFuente, 2026-02-14: Otro resumen
```

---

## 6. Notes

**Objetivo**: CRUD de notas personales en SQLite.

| Paso | Mensaje | Respuesta esperada |
|---|---|---|
| Crear | `Guardá una nota: Compras - Leche, pan, huevos` | `Note saved (ID: 1): "Compras"` |
| Listar | `Mostrá mis notas` | Lista con ID, título, preview (80 chars) |
| Buscar | `Buscá notas sobre compras` | Nota encontrada |
| Borrar | `Borrá la nota 1` | `Note 1 deleted.` |
| Borrar inexistente | `Borrá la nota 999` | `Note 999 not found.` |

---

## 7. Scheduler

**Objetivo**: Programar recordatorios via APScheduler, entrega por WhatsApp.

| Mensaje | Respuesta esperada |
|---|---|
| `Recordame revisar los logs en 2 minutos` | Confirmación con ID y hora programada |
| `Qué recordatorios tengo?` | Lista de jobs activos con ID y hora |

**Verificar entrega:**
1. Esperar el tiempo programado
2. Debe llegar mensaje WhatsApp: `⏰ *Reminder*: revisar los logs`

**Verificar error handling:**
- Fecha en el pasado → mensaje de error
- Formato inválido → el LLM debería manejar la conversión a ISO 8601

---

## 8. Tool Calling Loop

**Objetivo**: Verificar que el loop de herramientas funciona correctamente.

### 8a. Single tool call
> `Cuánto es 2 + 2?`
- Esperar: 1 iteración, respuesta directa

### 8b. Multi-step (encadenado)
> `Qué hora es en Buenos Aires y cómo está el clima ahí?`
- Esperar: LLM llama `get_current_datetime` + `get_weather` (puede ser en 1 o 2 iteraciones)

### 8c. Límite de iteraciones
- El loop tiene máximo **5 iteraciones** (`MAX_TOOL_ITERATIONS`)
- Si se excede, fuerza respuesta de texto sin tools

### 8d. Think mode
- **Con tools**: `think: True` deshabilitado (incompatibilidad qwen3)
- **Sin tools**: `think: True` habilitado (razonamiento visible en logs)

---

## 9. MCP — Fetch Server

**Objetivo**: Leer contenido web via `mcp-fetch-server`.

| Mensaje | Respuesta esperada |
|---|---|
| `Lee el contenido de https://example.com` | Resumen del contenido ("Example Domain...") |
| `Qué dice esta página? https://httpbin.org/get` | JSON de httpbin parseado |

**Verificar en logs:**
- `Executing MCP tool: fetch` o `get_markdown`
- Timeout: 30s por tool call

---

## 10. MCP — Filesystem Server

**Objetivo**: Leer/escribir archivos en `/app/data` (dentro del container).

| Mensaje | Respuesta esperada |
|---|---|
| `Lista los archivos en /home/appuser/data` | `mcp_servers.json`, `MEMORY.md`, etc. |
| `Leé el archivo mcp_servers.json` | Contenido del JSON de configuración |

**Verificar:**
- Solo accede a paths permitidos (el dir mapeado en Docker)
- Error si intenta acceder fuera del path configurado

---

## 11. MCP — Memory Server

**Objetivo**: Knowledge graph persistente via `@modelcontextprotocol/server-memory`.

| Paso | Mensaje | Respuesta esperada |
|---|---|---|
| Guardar | `Guardá en tu memoria que el proyecto WasAP usa Python 3.11` | Confirmación de entidad creada |
| Recuperar | `Qué sabés sobre WasAP según tu memoria?` | Info almacenada previamente |

> **Nota**: Los tools de Memory son de bajo nivel (`create_entity`, `add_relation`, etc.). El LLM puede necesitar guía explícita.

---

## 12. MCP — GitHub Server

**Requisito**: `GITHUB_PERSONAL_ACCESS_TOKEN` en `.env` con scope `repo`.

| Mensaje | Respuesta esperada |
|---|---|
| `Lista mis repositorios de GitHub` | Lista de repos |
| `Hay issues abiertos en el repo wasap?` | Issues listados (o "no hay") |

---

## 13. Colisiones de nombres (Skills vs MCP)

Si un tool MCP tiene el mismo nombre que un tool builtin:
- Se loguea un **warning**: `Tool name collision: <name>`
- El tool MCP **sobrescribe** al builtin
- Verificar en logs al arranque

---

## 14. Tipos de mensaje

| Tipo | Cómo probar | Comportamiento |
|---|---|---|
| **Texto** | Enviar mensaje normal | Flow completo (commands → tools → LLM) |
| **Audio** | Enviar nota de voz | Transcribe (faster-whisper) → procesa como texto |
| **Imagen** | Enviar foto | Vision (llava:7b) → descripción → respuesta (**sin tools**) |
| **Imagen + caption** | Enviar foto con texto | Vision + caption como contexto |
| **Reply** | Responder a un mensaje del bot | Inyecta texto citado como contexto |

> **Importante**: Mensajes de imagen **no pasan por el tool calling loop** — van directo a llava:7b para descripción visual, luego qwen3:8b para respuesta.

---

## 15. Comandos (bypasean skills)

Los comandos `/` se procesan **antes** de llegar al LLM.

| Comando | Resultado |
|---|---|
| `/help` | Lista de comandos disponibles |
| `/remember Mi cumple es el 15 de marzo` | Guardado en SQLite + MEMORY.md |
| `/memories` | Lista de memorias guardadas |
| `/forget 1` | Borra memoria por ID |
| `/clear` | Limpia historial de conversación |

---

## 16. Rate Limiting

- Default: 10 mensajes por 60 segundos (por número de teléfono)
- Enviar >10 mensajes rápido → algunos rechazados con mensaje de rate limit
- Verificar en logs: `Rate limited: <phone_number>`

---

## Troubleshooting

| Problema | Solución |
|---|---|
| `Tool not found` | Verificar logs de arranque — skill/MCP no se registró |
| `MCP connection refused` | Verificar `npx --version` dentro del container |
| `Search failed` | DuckDuckGo puede rate-limitear; esperar y reintentar |
| `Weather service unavailable` | Problema de red/IPv6; verificar DNS en el container |
| `GitHub auth error` | Verificar token en `.env` y scope `repo` |
| Tool loop infinito | No debería pasar (max 5 iteraciones), pero verificar en logs |
| `think` aparece en respuesta con tools | Bug: `think: True` no se deshabilitó; verificar `chat_with_tools()` |

### Logs útiles

```bash
# Todos los logs
docker compose logs -f wasap

# Solo errores
docker compose logs -f wasap 2>&1 | grep -i error

# Tool calls
docker compose logs -f wasap 2>&1 | grep -i "tool\|executing\|skill"

# MCP
docker compose logs -f wasap 2>&1 | grep -i "mcp\|server"
```
