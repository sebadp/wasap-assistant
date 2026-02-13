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

## Estructura
```
app/
  main.py              # FastAPI app + lifespan
  config.py            # Settings (pydantic-settings, .env)
  models.py            # Pydantic models
  dependencies.py      # FastAPI dependency injection
  logging_config.py    # JSON structured logging
  llm/client.py        # OllamaClient
  whatsapp/client.py   # WhatsApp Cloud API client
  webhook/router.py    # Webhook endpoints + process_message
  webhook/parser.py    # Extrae mensajes del payload
  webhook/security.py  # HMAC signature validation
  webhook/rate_limiter.py
  audio/transcriber.py # faster-whisper wrapper
  formatting/whatsapp.py  # Markdown -> WhatsApp
  formatting/splitter.py  # Split mensajes largos
  commands/             # Sistema de comandos (/remember, /forget, etc)
  conversation/         # ConversationManager + Summarizer
  database/             # SQLite init + Repository
  memory/               # Markdown memory mirror
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
- Background tasks via `BackgroundTasks` de FastAPI
- Dependencies via `app.state.*` + funciones `get_*()` en `dependencies.py`
- Mensajes de WhatsApp se formatean (markdown->whatsapp) y splitean antes de enviar
