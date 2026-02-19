# WasAP — Convenciones del Proyecto

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
    registry.py        # SkillRegistry (registro, schemas Ollama, ejecucion)
    executor.py        # Tool calling loop (max 5 iteraciones)
    tools/             # Handlers de tools builtin
      datetime_tools.py
      calculator_tools.py
      weather_tools.py
      notes_tools.py
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
- SKILL.md: frontmatter parseado con regex (sin PyYAML), instrucciones se cargan lazy en primer uso
- Calculator: AST safe eval con whitelist estricta, NO eval() directo
- Docker: container corre como `appuser` (UID=1000), no root
- Memoria en 3 capas: semántica (MEMORY.md), episódica reciente (daily logs), episódica histórica (snapshots)
- Pre-compaction flush: antes de borrar mensajes, el LLM extrae facts→memories + events→daily log
- Dedup de facts: `difflib.SequenceMatcher(ratio > 0.8)` contra memorias existentes
- Session snapshots: `/clear` guarda últimos 15 msgs con slug LLM-generated en `data/memory/snapshots/`
- Memory consolidation: LLM revisa memorias para duplicados/contradicciones después del flush
- `CommandContext` tiene `ollama_client`, `daily_log` y `embed_model` para snapshot generation y auto-indexing
- Búsqueda semántica: `_get_query_embedding()` se computa una vez y se reutiliza para memorias + notas
- `init_db()` retorna `(conn, vec_available)` — fallback graceful si sqlite-vec no disponible
- sqlite-vec: `check_same_thread=False` + `conn._connection.enable_load_extension()` durante init
- Vectores serializados con `struct.pack(f"{len(v)}f", *v)` para blob storage
- Embeddings best-effort: errores logueados, nunca propagados — la app funciona sin embeddings
- MEMORY.md watcher: watchdog con sync guard (`threading.Event`) para prevenir loops
- `MemoryFile.set_watcher()` conecta el guard; `on_created` maneja editores con atomic rename
