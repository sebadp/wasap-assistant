# WasAP

Asistente personal de WhatsApp con LLM local via Ollama. Privado, gratuito, dockerizado.

```
Tu celular ──► WhatsApp ──► Meta Cloud API ──► ngrok ──► FastAPI ──► Ollama (local)
                                                              │
                                                           SQLite
```

## Qué hace

- Recibe mensajes de WhatsApp via la API oficial de Meta (sin riesgo de ban)
- Los procesa con un LLM local corriendo en Ollama
- Mantiene historial de conversación persistente en SQLite
- Sistema de memorias: el asistente recuerda datos entre sesiones
- Resumen automático de conversaciones largas
- Comandos interactivos via `/slash`
- **Skills con tool calling**: el asistente puede consultar el clima, calcular, tomar notas, decir la hora
- Audio entrante (transcripción local con Whisper) e imágenes (vision con llava)
- Formato WhatsApp, splitting de mensajes largos, rate limiting
- Cero costo de operación

## Quickstart

```bash
# 1. Configurar
cp .env.example .env
# Editar .env con tus credenciales (ver SETUP.md para detalle)

# 2. Levantar
docker compose up -d

# 3. Descargar modelos
docker compose exec ollama ollama pull qwen3:8b
docker compose exec ollama ollama pull llava:7b

# 4. Configurar webhook en Meta Developer Portal
#    Callback URL: https://tu-dominio-ngrok/webhook
```

Ver [SETUP.md](SETUP.md) para la guía completa paso a paso.

## Comandos

| Comando | Descripción |
|---------|-------------|
| `/remember <dato>` | Guardar información importante |
| `/forget <dato>` | Olvidar un recuerdo guardado |
| `/memories` | Listar todos los recuerdos |
| `/clear` | Borrar historial de conversación |
| `/help` | Mostrar comandos disponibles |

Las memorias persisten entre reinicios y se inyectan automáticamente en el contexto del LLM.

## Skills

El asistente tiene capacidades más allá de conversar, usando tool calling nativo de qwen3:

| Skill | Tools | Descripción |
|-------|-------|-------------|
| `datetime` | `get_current_datetime`, `convert_timezone` | Hora actual, conversión de zonas horarias |
| `calculator` | `calculate` | Cálculos matemáticos (evaluación segura via AST) |
| `weather` | `get_weather` | Clima actual y pronóstico via wttr.in |
| `notes` | `save_note`, `list_notes`, `search_notes`, `delete_note` | Notas persistentes en SQLite |

Los skills se definen con archivos `SKILL.md` en `skills/`. Para agregar un skill nuevo: crear una carpeta con `SKILL.md` + registrar los handlers en Python.

## Arquitectura

```
app/
├── main.py                  # FastAPI app, lifespan, wiring
├── config.py                # Pydantic Settings (.env)
├── models.py                # Modelos de datos (ChatMessage, Memory, Note, etc.)
├── dependencies.py          # FastAPI dependency injection
├── logging_config.py        # JSON structured logging
├── database/
│   ├── db.py                # Inicialización SQLite (WAL, schema)
│   └── repository.py        # Queries (conversations, messages, memories, notes, dedup)
├── conversation/
│   ├── manager.py           # ConversationManager (historial, contexto)
│   └── summarizer.py        # Resumen automático en background
├── commands/
│   ├── registry.py          # Registry extensible de comandos
│   ├── parser.py            # Detección de /comandos
│   ├── builtins.py          # Comandos built-in (remember, forget, etc.)
│   └── context.py           # Contexto de ejecución de comandos
├── skills/
│   ├── models.py            # ToolDefinition, ToolCall, ToolResult, SkillMetadata
│   ├── loader.py            # Parser de SKILL.md (frontmatter con regex)
│   ├── registry.py          # SkillRegistry (registro, schemas Ollama, ejecución)
│   ├── executor.py          # Tool calling loop (max 5 iteraciones)
│   └── tools/               # Handlers de tools builtin
│       ├── datetime_tools.py
│       ├── calculator_tools.py
│       ├── weather_tools.py
│       └── notes_tools.py
├── llm/
│   └── client.py            # Cliente Ollama (chat + tool calling)
├── whatsapp/
│   └── client.py            # Cliente WhatsApp Cloud API
├── webhook/
│   ├── router.py            # Endpoints POST/GET /webhook + graceful shutdown
│   ├── parser.py            # Extracción de mensajes del payload de Meta
│   ├── security.py          # Validación HMAC-SHA256
│   └── rate_limiter.py      # Rate limiting por número
├── audio/
│   └── transcriber.py       # Transcripción con faster-whisper
├── formatting/
│   ├── whatsapp.py          # Markdown -> formato WhatsApp
│   └── splitter.py          # Split de mensajes largos
├── memory/
│   └── markdown.py          # Mirror SQLite -> MEMORY.md
└── health/
    └── router.py            # GET /health

skills/                      # Definiciones de skills (SKILL.md)
├── datetime/SKILL.md
├── calculator/SKILL.md
├── weather/SKILL.md
└── notes/SKILL.md
```

### Stack

| Componente | Tecnología |
|------------|------------|
| Servidor | Python 3.11+ / FastAPI |
| WhatsApp | Cloud API oficial de Meta |
| Túnel | ngrok (free tier) |
| LLM | Ollama (local) |
| Base de datos | SQLite (WAL mode) + aiosqlite |
| Contenedores | Docker + Docker Compose |

### Flujo de un mensaje

1. Mensaje llega de WhatsApp → Meta lo envía como webhook POST
2. ngrok tuneliza a `localhost:8000`
3. FastAPI valida firma HMAC, dedup atómico, extrae el mensaje
4. Si es audio → se transcribe con Whisper; si es imagen → se describe con llava
5. Si es un `/comando` → se ejecuta directamente, sin pasar por el LLM
6. Si es texto normal:
   - Se guarda en SQLite (con reply context si es respuesta a un mensaje)
   - Se cargan memorias activas + skills summary + resumen previo + historial reciente
   - Si hay skills disponibles → tool calling loop (LLM ↔ tools, max 5 iteraciones)
   - Si no hay skills → chat directo con Ollama
   - La respuesta se formatea (markdown→WhatsApp), se splitea si es larga, y se envía
   - Si el historial supera el threshold, se lanza un resumen en background

### Base de datos

SQLite con 6 tablas:

- **conversations** — una por número de teléfono
- **messages** — historial completo con `wa_message_id`
- **memories** — datos del usuario (soft-delete con `active` flag)
- **summaries** — resúmenes automáticos de conversaciones largas
- **notes** — notas del usuario (title, content) via skill de notas
- **processed_messages** — deduplicación atómica de webhooks (INSERT OR IGNORE)

El archivo `data/MEMORY.md` es un mirror de solo lectura de las memorias activas.

## Configuración

Variables de entorno (ver [.env.example](.env.example)):

| Variable | Descripción | Default |
|----------|-------------|---------|
| `WHATSAPP_ACCESS_TOKEN` | Token de la API de Meta | (requerido) |
| `WHATSAPP_PHONE_NUMBER_ID` | ID del número de WhatsApp | (requerido) |
| `WHATSAPP_VERIFY_TOKEN` | Token de verificación del webhook | (requerido) |
| `WHATSAPP_APP_SECRET` | Secret de la app de Meta | (requerido) |
| `ALLOWED_PHONE_NUMBERS` | Números permitidos (comma-separated) | (requerido) |
| `OLLAMA_BASE_URL` | URL de Ollama | `http://ollama:11434` |
| `OLLAMA_MODEL` | Modelo de chat | `qwen3:8b` |
| `VISION_MODEL` | Modelo de visión | `llava:7b` |
| `SYSTEM_PROMPT` | Prompt del sistema | (ver .env.example) |
| `CONVERSATION_MAX_MESSAGES` | Mensajes recientes en contexto | `20` |
| `DATABASE_PATH` | Ruta al archivo SQLite | `data/wasap.db` |
| `SUMMARY_THRESHOLD` | Mensajes antes de resumir | `40` |
| `SKILLS_DIR` | Directorio de skills | `skills` |
| `LOG_LEVEL` | Nivel de logging | `INFO` |

## Tests

```bash
# Con el venv local
.venv/bin/python -m pytest tests/ -v

# Con Docker
docker compose run --rm wasap python -m pytest tests/ -v
```

180+ tests cubriendo: repository, conversation manager, comandos, parser, markdown memory, summarizer, webhook (verificación, mensajes, comandos), health check, cliente Ollama, cliente WhatsApp, validación de firma, skill loader, skill registry, tool executor, y cada skill (datetime, calculator, weather, notes).

## Docker

```bash
# Levantar todo
docker compose up -d

# Con GPU NVIDIA
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# Ver logs
docker compose logs -f wasap

# Rebuild después de cambios
docker compose up -d --build wasap
```

El container corre como usuario no-root (`appuser`, UID=1000) para que los archivos en `data/` tengan los permisos correctos. Si venís de una versión anterior donde `data/` quedó como root, corregí los permisos una vez con:

```bash
sudo chown -R $(id -u):$(id -g) data/
```

## Modelos recomendados

| Modelo | Params | RAM | Español | Tools |
|--------|--------|-----|---------|-------|
| `qwen3:8b` | 8B | 8GB | Excelente | Si |
| `llava:7b` | 7B | 8GB | Limitado | No (vision) |
| `llama3.2:8b` | 8B | 8GB | Bueno | Si |
| `llama3.2:3b` | 3B | 4GB | Aceptable | Limitado |

## Roadmap

- [x] **Fase 1**: Chat funcional (webhook, Ollama, historial en memoria)
- [x] **Fase 2**: Persistencia y memoria (SQLite, comandos, summarization)
- [x] **Fase 3**: UX y multimedia (audio, imágenes, formato WhatsApp, rate limiting, logging)
- [x] **Fase 4**: Skills y herramientas (tool calling, datetime, calculator, weather, notes) + reliability (dedup atómico, reply context, graceful shutdown)
- [ ] **Fase 5**: Memoria avanzada (embeddings, RAG)

Ver [PRODUCT_PLAN.md](PRODUCT_PLAN.md) para el detalle de cada fase.
