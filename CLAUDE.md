# WasAP — Convenciones del Proyecto

## Stack
- **Framework**: FastAPI (async, lifespan pattern)
- **LLM**: Ollama con **qwen3:8b** (chat) y **llava:7b** (vision)
- **Audio**: faster-whisper (transcripcion local)
- **DB**: SQLite via aiosqlite
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
  llm/client.py        # OllamaClient (chat + tool calling)
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
  conversation/         # ConversationManager + Summarizer
  database/             # SQLite init + Repository
  memory/               # Markdown memory mirror
skills/                 # SKILL.md definitions (configurable via skills_dir)
tests/
```

## Tests
- Correr: `.venv/bin/python -m pytest tests/ -v`
- `asyncio_mode = "auto"` — no hace falta `@pytest.mark.asyncio`
- `TestClient` (sync) para integration tests del webhook
- Async fixtures para unit tests
- Mockear siempre Ollama y WhatsApp API en tests

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
