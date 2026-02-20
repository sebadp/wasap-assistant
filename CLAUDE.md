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
  guardrails/          # Validación pre-entrega (Eval Fase 1)
    models.py          # GuardrailResult, GuardrailReport
    checks.py          # check_not_empty, check_language_match, check_no_pii, etc.
    pipeline.py        # run_guardrails() — orquesta checks, fail-open
  tracing/             # Trazabilidad estructurada (Eval Fase 2)
    context.py         # TraceContext (async ctx mgr), SpanData, get_current_trace()
    recorder.py        # TraceRecorder — persistencia SQLite best-effort
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
  eval/                 # Dataset vivo + curación automática
    dataset.py         # maybe_curate_to_dataset() (3-tier), add_correction_pair()
    exporter.py        # export_to_jsonl() para tests offline
  mcp/                  # MCP server integration
skills/                 # SKILL.md definitions (configurable via skills_dir)
tests/
```

## Tests
- Correr: `make test` o `.venv/bin/python -m pytest tests/ -v`
- `asyncio_mode = "auto"` — no hace falta `@pytest.mark.asyncio`
- `TestClient` (sync) para integration tests del webhook
- Async fixtures para unit tests
- Mockear siempre Ollama y WhatsApp API en tests

## Calidad de código
- **Linter**: `ruff` — `make lint` / `make format`
- **Type checking**: `mypy app/` — `make typecheck` (solo `app/`, no `tests/`)
- **Pre-commit hooks**: ruff → mypy → pytest — instalar con `make dev`
- **CI**: GitHub Actions en `.github/workflows/ci.yml` — 3 jobs: lint → typecheck → test
- **mypy lenient**: `ignore_missing_imports = true` porque faster-whisper, sqlite-vec, mcp, watchdog no tienen stubs
- **ruff ignores**: `E501` (lineas largas), `B008` (FastAPI usa `Depends(...)` como default)
- Antes de pushear: `make check` (lint + typecheck + tests)

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
- Guardrails LLM checks (Iteración 6): `check_tool_coherence` y `check_hallucination` en `checks.py` — async, prompt binario (yes/no), fail open. Integrados via `_run_async_check(timeout=0.5s)` en `pipeline.py`. Gated por `guardrails_llm_checks=False` (opt-in). Call site en `router.py` pasa `ollama_client` a `run_guardrails`.
- Span instrumentation de tools: `_run_tool_call` en `executor.py` llama `get_current_trace()` — si hay traza activa, wrappea ejecución en `trace.span(f"tool:{name}", kind="tool")` con input/output. Sin traza → ejecución directa sin overhead.
- Trace cleanup job: APScheduler cron 03:00 UTC registrado en `main.py` gated por `tracing_enabled`. Closure sobre `repository` + `settings`. Llama `repository.cleanup_old_traces(days=settings.trace_retention_days)`.
- Dashboard queries eval: `repository.get_failure_trend(days)` (tendencia diaria) + `repository.get_score_distribution()` (stats por check). Tool `get_dashboard_stats` en eval skill.
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
- **Guardrails** (`app/guardrails/`): pipeline de validación pre-entrega. Checks determinísticos (sin LLM): `not_empty`, `language_match` (solo si ≥30 chars — `langdetect` falla en textos cortos), `no_pii`/`redact_pii` (regex), `excessive_length` (>8000 chars), `no_raw_tool_json`. Fail-open: errores en checks → pasan. Remediation single-shot en `_handle_guardrail_failure` (sin recursión). Scores de guardrails → `trace_scores` (value=1.0/0.0, source="system"). Integrado en `_run_normal_flow()` dentro de `_handle_message`.
- **Trazabilidad** (`app/tracing/`): `TraceContext` usa `contextvars.ContextVar` — sub-tasks de asyncio heredan el trace automáticamente sin cambiar firmas. `TraceRecorder` best-effort (excepciones capturadas, nunca propagadas). `TRACING_SCHEMA` en `db.py` crea tablas `traces`, `trace_spans`, `trace_scores` con `CREATE TABLE IF NOT EXISTS`. `WhatsAppClient.send_message()` retorna `str | None` (wa_message_id del primer chunk) para vincular trazas a mensajes WA. Flujo normal refactorizado en `_run_normal_flow()` inner function en `router.py` — permite toggle de tracing sin duplicar lógica. `tracing_sample_rate` check con `random.random()` antes de crear el `TraceContext` (sampling a nivel de mensaje completo).
- **Dataset vivo** (`app/eval/`): `DATASET_SCHEMA` en `db.py` — tablas `eval_dataset` + `eval_dataset_tags` (tags como tabla join separada, no JSON array — permite índices eficientes). Curación 3-tier en `maybe_curate_to_dataset()`: failure (guardrail<0.3 o usuario negativo) > golden confirmado (sistema OK + usuario positivo) > golden candidato (sistema OK, sin señal de usuario, `metadata.confirmed=False`). Se llama como background task al final de `_run_normal_flow()` cuando `eval_auto_curate=True`. Correction pairs: `add_correction_pair()` guarda `entry_type="correction"` con `expected_output=correction_text` al detectar corrección high-confidence (score==0.0). FK de `eval_dataset.trace_id` → `traces(id)` enforced con `PRAGMA foreign_keys=ON`. `exporter.py`: `export_to_jsonl()` exporta a JSONL para tests offline.
- **Auto-evolución** (`app/eval/prompt_manager.py` + `app/eval/evolution.py`): `PROMPT_SCHEMA` en `db.py` — tabla `prompt_versions` (unique index por `prompt_name+version`, constraint `is_active` enforced a nivel app en `activate_prompt_version()` — SQLite no soporta partial unique index). Cache en memoria `_active_prompts` dict en `prompt_manager.py` — se invalida vía `invalidate_prompt_cache()`. `get_active_prompt()` lazy-loads desde DB, fallback al default de `config.py`. Integrado en `_run_normal_flow()` reemplazando `settings.system_prompt`. Memorias de auto-corrección: guardrail failure → `_save_self_correction_memory()` background task → `add_memory(category="self_correction")` + `memory_file.sync()` + embed best-effort. `propose_prompt_change()` en `evolution.py`: LLM genera prompt modificado → `save_prompt_version(created_by="agent")`. Comando `/approve-prompt <nombre> <versión>` → `activate_prompt_version()` + `invalidate_prompt_cache()`.
- **Eval skill** (`skills/eval/SKILL.md` + `app/skills/tools/eval_tools.py`): 8 tools — `get_eval_summary` (métricas agregadas de scores), `list_recent_failures` (trazas con score<0.5), `diagnose_trace` (deep-dive con spans y scores), `propose_correction` (correction pair vía LLM), `add_to_dataset` (curación manual), `get_dataset_stats` (composición del dataset), `run_quick_eval` (eval offline usando `ollama_client.chat()` directo — SIN tool loop para evitar recursión). Registrado en `register_builtin_tools()` con guard `settings.tracing_enabled`. Categoría `"evaluation"` agregada a `TOOL_CATEGORIES` en `app/skills/router.py` — el classifier dinámicamente incluye la categoría (usa `TOOL_CATEGORIES.keys()`). Patrón: closures sobre `repository` + `ollama_client` dentro de `register()`, igual que `selfcode_tools.py`.
