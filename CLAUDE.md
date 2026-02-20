# WasAP — Convenciones del Proyecto

> **Mapa del proyecto** → `AGENTS.md` (dónde está cada cosa, workflow, skills activos)
> Este archivo documenta **convenciones de código y patrones arquitectónicos**.

## Protocolo de Documentación (OBLIGATORIO al terminar una feature)
1. Crear `docs/features/<nombre>.md` (template: `docs/features/TEMPLATE.md`)
2. Crear `docs/testing/<nombre>_testing.md` (template: `docs/testing/TEMPLATE.md`)
3. Para features complejas: crear `docs/exec-plans/<nombre>.md` **antes** de implementar
4. Actualizar `CLAUDE.md` con patrones que deben preservarse
5. Actualizar `AGENTS.md` si se agrega un skill, módulo o comando nuevo

## Stack
- **Framework**: FastAPI (async, lifespan pattern)
- **LLM**: Ollama con **qwen3:8b** (chat) y **llava:7b** (vision)
- **Audio**: faster-whisper (transcripcion local)
- **DB**: SQLite via aiosqlite + sqlite-vec (vector search)
- **Embeddings**: nomic-embed-text via Ollama (768 dims)
- **Python**: 3.11+

## Modelos de Ollama
- Chat principal: `qwen3:8b` — NO usar qwen2.5
- Vision: `llava:7b`
- Los defaults estan en `app/config.py`, overrideables via env vars
- `think: True` solo para qwen3 sin tools. Cuando hay tools en el payload, NO se usa `think`

## Estructura
```
app/
  main.py              # FastAPI app + lifespan
  config.py            # Settings (pydantic-settings, .env)
  models.py            # Pydantic models
  dependencies.py      # FastAPI dependency injection
  logging_config.py    # JSON structured logging
  embeddings/          # Embedding indexer
    indexer.py         # embed_memory, backfill_embeddings (best-effort)
  llm/client.py        # OllamaClient (chat + tool calling + embeddings)
  whatsapp/client.py   # WhatsApp Cloud API client
  webhook/router.py    # Webhook endpoints + process_message + graceful shutdown
  webhook/parser.py    # Extrae mensajes del payload (text, audio, image, reply context)
  webhook/security.py  # HMAC signature validation
  webhook/rate_limiter.py
  audio/transcriber.py # faster-whisper wrapper
  formatting/whatsapp.py  # Markdown -> WhatsApp
  formatting/splitter.py  # Split mensajes largos
  skills/              # Sistema de skills y tool calling
    models.py          # ToolDefinition, ToolCall, ToolResult, SkillMetadata
    loader.py          # Parser de SKILL.md (frontmatter con regex, sin PyYAML)
    registry.py        # SkillRegistry (registro, schemas Ollama, ejecucion) — get_skill(), get_tools_for_skill(), reload()
    executor.py        # Tool calling loop (max 5 iteraciones) — reset_tools_cache()
    router.py          # classify_intent, select_tools, TOOL_CATEGORIES — register_dynamic_category()
    tools/             # Handlers de tools builtin
      datetime_tools.py
      calculator_tools.py
      weather_tools.py
      notes_tools.py
      selfcode_tools.py  # Auto-inspección: version, source, config, health, search
      expand_tools.py    # Auto-expansión: Smithery registry, hot-install MCP, skill from URL
      project_tools.py   # Proyectos, tareas, actividad y notas con embeddings
  commands/             # Sistema de comandos (/remember, /forget, etc)
  conversation/         # ConversationManager + Summarizer (con pre-compaction flush)
  database/             # SQLite init + sqlite-vec + Repository
  memory/               # Sistema de memoria
    markdown.py        # Sync bidireccional SQLite <-> MEMORY.md
    watcher.py         # File watcher (watchdog) para edición manual de MEMORY.md
    daily_log.py       # Daily logs append-only + session snapshots
    consolidator.py    # Dedup/merge de memorias via LLM
  mcp/                  # MCP server integration
skills/                 # SKILL.md definitions (configurable via skills_dir)
tests/
```

## Tests
- Correr: `.venv/bin/python -m pytest tests/ -v`
- `asyncio_mode = "auto"` — no hace falta `@pytest.mark.asyncio`
- `TestClient` (sync) para integration tests del webhook
- Async fixtures para unit tests
- Mockear siempre Ollama y WhatsApp API en tests

## Fase 7 — Performance Optimization
- Critical path parallelizado en `_handle_message` (router.py) en fases:
  - **Phase A** (`asyncio.gather`): embed(query) ‖ save_message(conv_id) ‖ load_daily_logs()
  - **Phase B** (`asyncio.gather`): search_memories ‖ search_notes ‖ get_latest_summary ‖ get_recent_messages
  - **Phase C**: `await classify_task` (kicked off antes de Phase A, corre en paralelo)
  - **Phase D**: `_build_context()` (sync) → chat_with_tools (LLM principal)
- `_build_context()` helper en router.py — construye el contexto LLM a partir de datos ya pre-fetched (sin DB calls)
- `pre_classified_categories` param en `execute_tool_loop` — evita segunda llamada a `classify_intent`
- Cache module-level `_cached_tools_map` en executor.py — `_get_cached_tools_map()` construye el map una sola vez
- Parallel tool calls dentro de una iteración: `asyncio.gather(*[_run_tool_call(...) for tc in tool_calls])`
- `_run_tool_call()` helper en executor.py para ejecutar un tool call y retornar `ChatMessage(role="tool")`
- WA calls iniciales (mark_as_read + send_reaction) paralelizadas con `asyncio.gather`
- Blocking I/O en `daily_log.py` y `markdown.py` → `asyncio.to_thread()` (stdlib Python 3.9+)
- Cache de conv_id en `ConversationManager._conv_id_cache` (dict phone→id, permanente durante runtime)
  - Método privado `_get_conv_id()` usado por todos los métodos del manager
- `get_active_memories(limit=...)` — fallback con límite (`settings.semantic_search_top_k`) para evitar cargar todo
- SQLite PRAGMA tuning en `db.py`: `synchronous=NORMAL`, `cache_size=-32000` (32MB), `temp_store=MEMORY`
- Model warmup en `main.py` startup: `embed(["warmup"]) ‖ chat_with_tools([...])` — non-critical, wrapped in try/except
- `import datetime` movido al top de router.py (era inline dentro de la función)

## Patrones
- Todo async, nunca bloquear el event loop (usar `run_in_executor` para sync code como Whisper)
- Background tasks via `BackgroundTasks` de FastAPI, trackeados con `_track_task()` para graceful shutdown
- Dependencies via `app.state.*` + funciones `get_*()` en `dependencies.py`
- Mensajes de WhatsApp se formatean (markdown->whatsapp) y splitean antes de enviar
- Tool calling loop: LLM llama tools → se ejecutan → resultados vuelven al LLM → repite hasta texto o max 5 iteraciones
- Dedup atomico: `processed_messages` tabla con INSERT OR IGNORE (sin race conditions)
- Reply context: si el usuario responde a un mensaje, se inyecta el texto citado en el prompt
- `_build_capabilities_section()` en router.py construye sección estructurada de capacidades (commands + skills + MCP) para el contexto LLM — reemplaza el summary plano anterior. Se auto-actualiza al agregar skills/commands/MCP servers
- SKILL.md: frontmatter parseado con regex (sin PyYAML), instrucciones se cargan lazy en primer uso
- `selfcode` skill: `register()` recibe `settings` (no `repository`). `_PROJECT_ROOT` resuelto una sola vez al importar. `_is_safe_path()` previene path traversal + bloquea archivos sensibles. `_SENSITIVE` hardcodeado oculta tokens de WhatsApp en `get_runtime_config`. `register_builtin_tools` acepta `settings=None` — selfcode solo se registra si `settings` no es None
- Hot-reload: `McpManager` usa `_server_stacks: dict[str, AsyncExitStack]` (uno por servidor) en lugar de un stack global — permite `hot_add_server()` / `hot_remove_server()` sin restart. `hot_add_server` persiste config + llama `reset_tools_cache()` + `register_dynamic_category()`. `SkillRegistry.reload()` re-escanea `skills/` y limpia `_loaded_instructions`. `reset_tools_cache()` en executor.py pone `_cached_tools_map = None`
- MCP HTTP transport: `McpManager._connect_server()` detecta `cfg["type"]` — `"http"` usa `streamable_http_client(url)` (3-tuple read/write/session_id), `"stdio"` usa `stdio_client` (2-tuple). Servidores Smithery son siempre tipo `"http"`
- `expand` skill: `register()` recibe `mcp_manager` (no `repository`). MCP manager se inicializa ANTES que skills en `main.py` para que `expand_tools` pueda referenciar el manager. Smithery API: `GET https://registry.smithery.ai/servers?q=<query>` — no requiere auth
- Calculator: AST safe eval con whitelist estricta, NO eval() directo
- Docker: container corre como `appuser` (UID=1000), no root
- Memoria en 3 capas: semántica (MEMORY.md), episódica reciente (daily logs), episódica histórica (snapshots)
- Pre-compaction flush: antes de borrar mensajes, el LLM extrae facts→memories + events→daily log
- Dedup de facts: `difflib.SequenceMatcher(ratio > 0.8)` contra memorias existentes
- Session snapshots: `/clear` guarda últimos 15 msgs con slug LLM-generated en `data/memory/snapshots/`
- Memory consolidation: LLM revisa memorias para duplicados/contradicciones después del flush
- `/review-skill` command: sin args lista skills + MCP servers; con nombre muestra detalle (tools, estado, instrucciones para skills; tipo, estado, tools para MCP)
- `CommandContext` tiene `ollama_client`, `daily_log` y `embed_model` para snapshot generation y auto-indexing
- Búsqueda semántica: `_get_query_embedding()` se computa una vez y se reutiliza para memorias + notas
- `init_db()` retorna `(conn, vec_available)` — fallback graceful si sqlite-vec no disponible
- sqlite-vec: `check_same_thread=False` + `conn._connection.enable_load_extension()` durante init
- Vectores serializados con `struct.pack(f"{len(v)}f", *v)` para blob storage
- Embeddings best-effort: errores logueados, nunca propagados — la app funciona sin embeddings
- MEMORY.md watcher: watchdog con sync guard (`threading.Event`) para prevenir loops
- `MemoryFile.set_watcher()` conecta el guard; `on_created` maneja editores con atomic rename
- `projects` skill: 4 tablas (`projects`, `project_tasks`, `project_activity`, `project_notes`) + `vec_project_notes` (sqlite-vec). `phone_number` en `projects` (no FK a `conversations`) — proyectos sobreviven `/clear`. `UNIQUE(phone_number, name)` — el LLM identifica proyectos por nombre. `project_tools.register()` recibe `repository`, `daily_log`, `ollama_client`, `embed_model`, `vec_available`. `set_current_user(phone)` module-level seteado per-request en `_handle_message`. `_resolve_project(name)` helper interno que busca COLLATE NOCASE. `update_task` a "done" loguea al `daily_log`. Si todas las tareas están done → sugiere `update_project_status`. `update_project_status` a archived/completed → registra resumen final automático. `_get_active_projects_summary()` en webhook/router.py — inyectada en Phase B (`asyncio.gather` con memorias/notas/summary/history). `register_builtin_tools` acepta `daily_log=None` — pasado desde `main.py`. Embeddings de project notes via `embed_project_note()` en indexer.py (best-effort). Búsqueda semántica en `search_project_notes` con fallback a list all.
