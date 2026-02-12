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
- Cero costo de operación

## Quickstart

```bash
# 1. Configurar
cp .env.example .env
# Editar .env con tus credenciales (ver SETUP.md para detalle)

# 2. Levantar
docker compose up -d

# 3. Descargar modelo
docker compose exec ollama ollama pull qwen2.5:7b

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

## Arquitectura

```
app/
├── main.py                  # FastAPI app, lifespan, wiring
├── config.py                # Pydantic Settings (.env)
├── models.py                # Modelos de datos (ChatMessage, Memory, etc.)
├── dependencies.py          # FastAPI dependency injection
├── database/
│   ├── db.py                # Inicialización SQLite (WAL, schema)
│   └── repository.py        # Queries (conversations, messages, memories, summaries)
├── conversation/
│   ├── manager.py           # ConversationManager (historial, contexto, dedup)
│   └── summarizer.py        # Resumen automático en background
├── commands/
│   ├── registry.py          # Registry extensible de comandos
│   ├── parser.py            # Detección de /comandos
│   ├── builtins.py          # Comandos built-in (remember, forget, etc.)
│   └── context.py           # Contexto de ejecución de comandos
├── llm/
│   └── client.py            # Cliente Ollama (/api/chat)
├── whatsapp/
│   └── client.py            # Cliente WhatsApp Cloud API
├── webhook/
│   ├── router.py            # Endpoints POST/GET /webhook
│   ├── parser.py            # Extracción de mensajes del payload de Meta
│   └── security.py          # Validación HMAC-SHA256
└── health/
    └── router.py            # GET /health
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
3. FastAPI valida firma HMAC, extrae el mensaje
4. Si es un `/comando` → se ejecuta directamente, sin pasar por el LLM
5. Si es texto normal:
   - Se guarda en SQLite
   - Se cargan memorias activas + resumen previo + historial reciente
   - Se arma el contexto y se envía a Ollama
   - La respuesta se guarda y se envía por WhatsApp
   - Si el historial supera el threshold, se lanza un resumen en background

### Base de datos

SQLite con 4 tablas:

- **conversations** — una por número de teléfono
- **messages** — historial completo con `wa_message_id` para deduplicación
- **memories** — datos del usuario (soft-delete con `active` flag)
- **summaries** — resúmenes automáticos de conversaciones largas

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
| `OLLAMA_MODEL` | Modelo a usar | `qwen2.5:7b` |
| `SYSTEM_PROMPT` | Prompt del sistema | (ver .env.example) |
| `CONVERSATION_MAX_MESSAGES` | Mensajes recientes en contexto | `20` |
| `DATABASE_PATH` | Ruta al archivo SQLite | `data/wasap.db` |
| `SUMMARY_THRESHOLD` | Mensajes antes de resumir | `40` |
| `LOG_LEVEL` | Nivel de logging | `INFO` |

## Tests

```bash
# Con el venv local
.venv/bin/python -m pytest tests/ -v

# Con Docker
docker compose run --rm wasap python -m pytest tests/ -v
```

70+ tests cubriendo: repository, conversation manager, comandos, parser de comandos, markdown memory, summarizer, webhook (verificación, mensajes, comandos), health check, cliente Ollama, cliente WhatsApp, validación de firma.

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

El directorio `data/` se monta como volume y persiste la base de datos y memorias entre reinicios.

## Modelos recomendados

| Modelo | Params | RAM | Español |
|--------|--------|-----|---------|
| `qwen2.5:7b` | 7B | 8GB | Excelente |
| `qwen3:8b` | 8B | 8GB | Excelente |
| `llama3.2:8b` | 8B | 8GB | Bueno |
| `llama3.2:3b` | 3B | 4GB | Aceptable |

## Roadmap

- [x] **Fase 1**: Chat funcional (webhook, Ollama, historial en memoria)
- [x] **Fase 2**: Persistencia y memoria (SQLite, comandos, summarization)
- [ ] **Fase 3**: UX y multimedia (audio, imágenes, formato WhatsApp)
- [ ] **Fase 4**: Herramientas (tool calling, plugins)
- [ ] **Fase 5**: Memoria avanzada (embeddings, RAG)

Ver [PRODUCT_PLAN.md](PRODUCT_PLAN.md) para el detalle de cada fase.
