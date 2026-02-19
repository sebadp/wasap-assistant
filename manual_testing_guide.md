# Guía de Testing Manual

## Requisitos previos

- Container corriendo: `docker compose up --build -d`
- Ollama con `qwen3:8b`, `llava:7b` y `nomic-embed-text` disponibles
- WhatsApp configurado (token, phone number ID, verify token, app secret en `.env`)
- Número de teléfono en `ALLOWED_PHONE_NUMBERS`
- Para MCP: `data/mcp_servers.json` con servers habilitados (`"enabled": true`)

### Verificar arranque

```bash
docker compose logs -f wasap | head -50
```

Buscar en los logs:
- `sqlite-vec loaded successfully (dims=768)` — sqlite-vec activo
- `Backfilled N memory embeddings` — embeddings creados al startup
- `Memory watcher started for data/MEMORY.md` — watcher bidireccional activo
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
| `/clear` | Limpia historial + guarda snapshot de sesión |

---

## 16. Memoria Avanzada (Fase 5)

### 16a. Daily Logs — Bootstrap Loading

Los daily logs se cargan automáticamente en el contexto del LLM. Para verificar:

1. Enviar muchos mensajes hasta que el summarizer se active (>40 mensajes)
2. Verificar en `data/memory/` que aparece un archivo `YYYY-MM-DD.md`
3. El archivo debería contener eventos extraídos de la conversación

### 16b. Pre-Compaction Flush

**Objetivo**: Antes de borrar mensajes viejos, el LLM extrae hechos y eventos.

1. Enviar >40 mensajes incluyendo hechos memorables (ej: "Mi color favorito es el azul", "Vivo en Córdoba")
2. Esperar que se active el summarizer
3. Verificar:
   - `data/MEMORY.md` contiene los hechos extraídos automáticamente
   - `data/memory/YYYY-MM-DD.md` contiene eventos del día
   - `sqlite3 data/wasap.db "SELECT * FROM memories;"` muestra las memorias auto-extraídas

### 16c. Session Snapshots

**Objetivo**: `/clear` guarda un snapshot antes de borrar.

1. Tener una conversación de varios mensajes
2. Enviar `/clear`
3. Verificar:
   - `data/memory/snapshots/` contiene un archivo `.md` con slug descriptivo
   - El archivo contiene los últimos mensajes (user/assistant)
   - El daily log tiene una entrada "Session cleared: ..."

### 16d. Memory Consolidation

**Objetivo**: Memorias duplicadas se consolidan automáticamente.

1. Usar `/remember` para guardar datos similares:
   - `/remember Mi color favorito es azul`
   - `/remember Me gusta el color azul`
   - (agregar al menos 8 memorias en total)
2. Enviar suficientes mensajes para activar el summarizer
3. Verificar que memorias duplicadas fueron removidas de `data/MEMORY.md`

---

## 17. Rate Limiting

- Default: 10 mensajes por 60 segundos (por número de teléfono)
- Enviar >10 mensajes rápido → algunos ignorados silenciosamente
- Verificar en logs: `Rate limit exceeded for <phone_number>`

---

## 18. Búsqueda Semántica de Memorias (Fase 6)

**Objetivo**: Verificar que solo memorias relevantes se inyectan en el contexto del LLM.

### 18a. Setup

```bash
# Verificar que nomic-embed-text está disponible
docker compose exec ollama ollama list | grep nomic

# Si no:
docker compose exec ollama ollama pull nomic-embed-text
```

### 18b. Prueba de relevancia

1. Guardar varias memorias diversas:
   ```
   /remember Mi color favorito es el azul
   /remember Trabajo como ingeniero de software
   /remember Tengo un perro llamado Max
   /remember Mi cumpleaños es el 15 de marzo
   /remember Prefiero café sin azúcar
   ```

2. Preguntar algo específico:
   - `Tengo mascotas?` → Debe mencionar a Max (la memoria del perro es relevante)
   - `A qué me dedico?` → Debe mencionar ingeniería de software

3. **Verificar en logs** (con `LOG_LEVEL=DEBUG`):
   - `Semantic memory search` — indica que se usó búsqueda semántica
   - Si falla → `falling back to all memories` — fallback automático

### 18c. Fallback sin embeddings

1. Setear `SEMANTIC_SEARCH_ENABLED=false` en `.env`
2. Reiniciar: `docker compose restart wasap`
3. Enviar un mensaje → todas las memorias deben aparecer en contexto (comportamiento anterior)
4. Volver a `SEMANTIC_SEARCH_ENABLED=true` y reiniciar

### 18d. Verificar embeddings en DB

```bash
# Contar embeddings de memorias
sqlite3 data/wasap.db "SELECT COUNT(*) FROM vec_memories;"

# Contar memorias sin embedding (deberían ser 0 después de backfill)
sqlite3 data/wasap.db "
  SELECT m.id, m.content FROM memories m
  LEFT JOIN vec_memories v ON v.memory_id = m.id
  WHERE m.active = 1 AND v.memory_id IS NULL;
"
```

---

## 19. MEMORY.md Bidireccional (Fase 6)

**Objetivo**: Editar `data/MEMORY.md` a mano y verificar que los cambios se sincronizan a SQLite.

### 19a. Sync File → DB (agregar)

1. Abrir `data/MEMORY.md` con un editor de texto
2. Agregar una línea: `- Editado desde el archivo`
3. Guardar
4. Esperar 1-2 segundos
5. Verificar:
   ```bash
   sqlite3 data/wasap.db "SELECT * FROM memories WHERE content = 'Editado desde el archivo';"
   ```
   Debe existir la memoria en la DB.

### 19b. Sync File → DB (borrar)

1. Abrir `data/MEMORY.md`
2. Eliminar una línea de memoria existente
3. Guardar
4. Verificar que la memoria fue desactivada en SQLite:
   ```bash
   sqlite3 data/wasap.db "SELECT id, content, active FROM memories ORDER BY id DESC LIMIT 5;"
   ```

### 19c. Sync DB → File

1. Usar el comando de WhatsApp: `/remember Agregado desde WhatsApp`
2. Verificar que `data/MEMORY.md` contiene la nueva línea
3. El archivo debe estar formateado correctamente

### 19d. Prevención de loops

1. Hacer un cambio via `/remember` → verificar que no se generan múltiples syncs en los logs
2. Editar el archivo → verificar que el watcher no entra en loop

**Verificar en logs:**
- `Synced from file → added: ...` — sync exitoso (file → DB)
- `Synced from file → removed: ...` — sync exitoso (eliminación)
- `Skipping sync (guard set)` — guard funcionando (previene loops)

### 19e. Memorias con categoría

1. Editar `data/MEMORY.md` y agregar: `- [hobby] Juega al fútbol`
2. Verificar en DB:
   ```bash
   sqlite3 data/wasap.db "SELECT content, category FROM memories WHERE content LIKE '%fútbol%';"
   ```
   Debe tener `category = 'hobby'`.

---

## 20. Búsqueda Semántica de Notas (Fase 6)

**Objetivo**: Verificar que `search_notes` usa búsqueda semántica con fallback a keyword.

### 20a. Crear notas y buscar semánticamente

1. Crear notas variadas:
   - `Guardá una nota: Receta de pizza - Harina, tomate, mozzarella, albahaca`
   - `Guardá una nota: Lista de compras - Leche, pan, huevos, manteca`
   - `Guardá una nota: Ideas proyecto - App de recetas con IA`

2. Buscar con términos semánticos (no exactos):
   - `Buscá notas sobre cocina` → debería encontrar la receta de pizza
   - `Buscá notas sobre comida` → debería encontrar la receta y la lista de compras
   - `Qué ideas tengo anotadas?` → debería encontrar ideas de proyecto

3. **Verificar en logs:**
   - `Semantic search found N matching notes` — búsqueda semántica usada
   - Si falla: `Semantic note search failed, falling back to keyword` — fallback

### 20b. Notas inyectadas en contexto

Las notas relevantes se inyectan automáticamente en el contexto del LLM:

1. Crear una nota: `Guardá una nota: Reunión lunes - Hablar con Juan sobre el deploy`
2. Preguntar: `Qué tengo pendiente para el lunes?`
3. El LLM debería mencionar la reunión con Juan (inyectada como contexto, no via tool)

### 20c. Verificar embeddings de notas

```bash
# Contar embeddings de notas
sqlite3 data/wasap.db "SELECT COUNT(*) FROM vec_notes;"

# Notas sin embedding
sqlite3 data/wasap.db "
  SELECT n.id, n.title FROM notes n
  LEFT JOIN vec_notes v ON v.note_id = n.id
  WHERE v.note_id IS NULL;
"
```

---

## 21. Auto-indexing (Fase 6)

**Objetivo**: Verificar que los embeddings se crean/borran automáticamente.

### 21a. /remember embede

1. Enviar `/remember Dato nuevo para embeder`
2. Verificar:
   ```bash
   sqlite3 data/wasap.db "
     SELECT m.id, m.content, CASE WHEN v.memory_id IS NOT NULL THEN 'embedded' ELSE 'pending' END
     FROM memories m
     LEFT JOIN vec_memories v ON v.memory_id = m.id
     WHERE m.content LIKE '%embeder%';
   "
   ```
   Debe mostrar `embedded`.

### 21b. /forget borra embedding

1. Enviar `/forget Dato nuevo para embeder`
2. Verificar que el embedding fue borrado:
   ```bash
   sqlite3 data/wasap.db "SELECT COUNT(*) FROM vec_memories WHERE memory_id NOT IN (SELECT id FROM memories WHERE active = 1);"
   ```
   Debe ser 0 (no hay embeddings huérfanos).

### 21c. Backfill al startup

1. Agregar una memoria directamente en SQLite (sin embedding):
   ```bash
   sqlite3 data/wasap.db "INSERT INTO memories (content) VALUES ('Memoria manual sin embedding');"
   ```
2. Reiniciar: `docker compose restart wasap`
3. Verificar en logs: `Backfilled N memory embeddings`
4. Verificar que ahora tiene embedding:
   ```bash
   sqlite3 data/wasap.db "
     SELECT m.content FROM memories m
     JOIN vec_memories v ON v.memory_id = m.id
     WHERE m.content LIKE '%manual%';
   "
   ```

---

## 22. Graceful Degradation (Fase 6)

**Objetivo**: Verificar que la app funciona cuando fallan los componentes de Fase 6.

### 22a. Sin modelo de embedding

1. Borrar el modelo: `docker compose exec ollama ollama rm nomic-embed-text`
2. Reiniciar: `docker compose restart wasap`
3. Enviar un mensaje → debe funcionar normalmente (fallback a todas las memorias)
4. Verificar en logs: `Failed to compute query embedding` o similar
5. Restaurar: `docker compose exec ollama ollama pull nomic-embed-text`

### 22b. SEMANTIC_SEARCH_ENABLED=false

1. Setear `SEMANTIC_SEARCH_ENABLED=false` en `.env`
2. Reiniciar
3. Verificar que la app funciona con el comportamiento pre-Fase 6
4. No se computan embeddings, no se busca semánticamente

### 22c. MEMORY_FILE_WATCH_ENABLED=false

1. Setear `MEMORY_FILE_WATCH_ENABLED=false` en `.env`
2. Reiniciar
3. Editar `data/MEMORY.md` → los cambios NO se sincronizan a SQLite
4. `/remember` sigue funcionando normalmente (DB → archivo, dirección única)

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
| `sqlite-vec not available` | Instalar `sqlite-vec` o verificar wheels en Docker; app sigue funcionando sin él |
| `Failed to compute query embedding` | Modelo `nomic-embed-text` no descargado; `ollama pull nomic-embed-text` |
| Watcher no detecta cambios | Verificar `MEMORY_FILE_WATCH_ENABLED=true` y que el archivo existe |
| Watcher entra en loop | Bug en sync guard; verificar logs por `Skipping sync (guard set)` repetido |
| Embeddings no se crean | Verificar `SEMANTIC_SEARCH_ENABLED=true` y que el modelo está disponible |

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

# Embeddings y búsqueda semántica
docker compose logs -f wasap 2>&1 | grep -i "embed\|vec\|semantic\|backfill"

# Memory watcher
docker compose logs -f wasap 2>&1 | grep -i "watcher\|sync\|guard"
```
