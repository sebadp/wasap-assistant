# WasAP - Plan de Producto
## Asistente Personal vía WhatsApp con LLM Local (Ollama)

---

## 1. Visión del Producto

Un asistente personal inteligente al que le hablás por WhatsApp y te responde usando un LLM corriendo en tu máquina via Ollama. Conversaciones contextuales, memoria persistente, y cero costo de operación.

**Principios:**
- **Privacidad**: el LLM y toda la lógica corren local. Los mensajes pasan por Meta (inevitable con WhatsApp) pero el procesamiento es 100% tuyo
- **Costo cero**: WhatsApp Cloud API gratis para mensajes de servicio + Ollama local + ngrok free
- **Simplicidad**: se levanta con `docker compose up`, no requiere infra cloud
- **Conversacional**: mantiene contexto y memoria entre sesiones
- **Extensible**: sistema de skills/plugins inspirado en [OpenClaw](https://openclaw.ai), donde agregar capacidades nuevas es escribir un archivo markdown

**Inspiración — OpenClaw:**
WasAP toma varios patrones de diseño de OpenClaw, el asistente personal open-source que usa markdown como capa de configuración y memoria. En particular:
- **Archivos markdown como fuente de verdad** para memorias y configuración de skills
- **Skills como carpetas con SKILL.md** que definen capacidades del agente
- **Memoria en dos capas**: hechos curados (MEMORY.md) + notas diarias (logs)
- **Carga progresiva**: solo se lee el detalle de un skill cuando el agente lo necesita

La diferencia clave: OpenClaw es un framework multi-canal multi-agente. WasAP es un asistente personal single-user, single-channel (WhatsApp), optimizado para simplicidad.

---

## 2. Arquitectura

```
┌──────────────┐    internet     ┌─────────────────┐
│  Tu celular  │◄───────────────►│  Meta / WhatsApp │
│  (WhatsApp)  │                 │  Cloud API       │
└──────────────┘                 └────────┬─────────┘
                                          │ webhook HTTPS
                                          ▼
                                 ┌─────────────────┐
                                 │  ngrok tunnel    │
                                 │  (free tier)     │
                                 └────────┬─────────┘
                                          │ localhost:8000
                                          ▼
                                 ┌─── Docker Compose ────────────────────┐
                                 │                                      │
                                 │  ┌─────────────────────────┐        │
                                 │  │  WasAP Server (Python)   │        │
                                 │  │                         │        │
                                 │  │  FastAPI                │        │
                                 │  │  ├─ Webhook receiver    │        │
                                 │  │  ├─ Command router      │        │
                                 │  │  ├─ Skill engine        │        │
                                 │  │  ├─ Conversation mgr    │        │
                                 │  │  ├─ Memory manager      │        │
                                 │  │  └─ WhatsApp sender     │        │
                                 │  └───┬─────────┬───────────┘        │
                                 │      │         │                    │
                                 │ ┌────┴───┐ ┌───┴──────┐            │
                                 │ │ Ollama │ │  SQLite  │            │
                                 │ │ (LLM)  │ │ (volume) │            │
                                 │ └────────┘ └──────────┘            │
                                 └──────────────────────────────────────┘
```

### Flujo de un mensaje

1. Escribís un mensaje en WhatsApp
2. Meta lo envía como webhook POST a tu dominio ngrok
3. ngrok lo tuneliza a tu `localhost:8000`
4. FastAPI recibe el webhook, valida la firma, extrae el mensaje
5. Si es un `/comando` → se ejecuta directamente sin pasar por el LLM
6. Si es texto normal:
   - Se guarda en SQLite
   - Se cargan memorias activas + resumen previo + historial reciente
   - Se arma el contexto (system prompt + memorias + summary + historial)
   - Se envía a Ollama API local
   - La respuesta se guarda y se envía por WhatsApp
   - Si el historial supera el threshold, se lanza un resumen en background

---

## 3. Stack Tecnológico

| Componente | Tecnología | Por qué |
|---|---|---|
| Servidor | **Python 3.11+ / FastAPI** | Async, rápido, ideal para webhooks |
| WhatsApp | **WhatsApp Cloud API** (oficial) | Gratis para servicio, sin riesgo de ban |
| Túnel | **ngrok** (free tier) | Dominio estático gratis, sin timeout, 1GB/mes sobra |
| LLM | **Ollama** | Local, gratuito, múltiples modelos, tool calling |
| Base de datos | **SQLite** (WAL mode) + **aiosqlite** | Sin servidor, async, suficiente para 1 usuario |
| Config | **archivo .env** + **markdown** | Simple, estándar, human-readable |
| Contenedores | **Docker + Docker Compose** | Setup reproducible, un solo comando para levantar todo |

### Por qué NO Baileys
- Riesgo creciente de ban permanente en 2026
- Viola ToS de WhatsApp
- Meta está detectando activamente clientes no oficiales
- Para un asistente personal de largo plazo, la estabilidad es clave

### Por qué WhatsApp Cloud API + ngrok
- **Oficial**: cero riesgo de ban
- **Gratis**: mensajes de servicio (respuesta dentro de 24h) no tienen costo
- **ngrok free**: dominio estático, sin timeout, 20k requests/mes
- **Trade-off aceptable**: el túnel pasa por ngrok pero el procesamiento es local

---

## 4. Funcionalidades por Fase

### Fase 1: MVP - Chat funcional ✅
> Poder mandar un mensaje por WhatsApp y recibir respuesta del LLM local.

- Webhook receiver con validación de firma de Meta
- Envío de respuestas via Cloud API
- Conexión a Ollama API (`/api/chat`)
- System prompt configurable
- Historial de conversación en memoria (últimos N mensajes)
- Whitelist de números (solo responde a tu número)
- Indicador de "visto" / acuse de recibo
- Health check endpoint
- Guía de setup completa (SETUP.md)
- **Dockerizado**: Dockerfile + docker-compose.yml (wasap + ollama + ngrok)
- Volume para modelos de Ollama (persistencia entre reinicios)
- Tests unitarios completos

### Fase 2: Persistencia y Memoria ✅
> El asistente recuerda conversaciones anteriores y datos que le pedís guardar.

- Persistencia en SQLite (WAL mode, aiosqlite)
- Cargar últimos N mensajes como contexto al recibir mensaje nuevo
- Resumen automático de conversaciones largas en background
- Sistema de memorias globales (SQLite source of truth + `data/MEMORY.md` mirror)
- Sistema de comandos extensible (registry pattern):
  - `/remember <dato>` — guardar información importante
  - `/forget <dato>` — olvidar un recuerdo guardado
  - `/memories` — listar recuerdos guardados
  - `/clear` — borrar historial de conversación
  - `/help` — mostrar comandos disponibles
- Memorias inyectadas automáticamente en el contexto del LLM
- Mensajes de error claros para token expirado, permisos faltantes, modelo no descargado
- Tests: 70+ tests cubriendo repository, commands, summarizer, memory mirror

### Fase 3: UX y Multimedia ✅
> El asistente se siente más natural y maneja más que texto.

- **Audio entrante**: descarga de WhatsApp → transcripción con faster-whisper local (async via run_in_executor)
- **Imágenes entrantes**: descarga → descripción con llava:7b → respuesta contextual con qwen3:8b
- **Formato WhatsApp**: conversión markdown→WhatsApp (*bold*, _italic_, ```code```, listas)
- **Mensajes largos**: split automático (>4096 chars) en múltiples mensajes
- **Indicador de typing**: emoji ⏳ como reacción durante procesamiento, removido en finally
- **Rate limiting**: in-memory, por número de teléfono
- **Logging estructurado**: JSON con python-json-logger

### Fase 4: Skills y Herramientas ✅
> El asistente puede hacer cosas, no solo conversar.

Inspirado en el [sistema de skills de OpenClaw](https://docs.openclaw.ai/tools/skills), donde cada skill es una carpeta con un archivo markdown que define qué puede hacer el agente.

#### Arquitectura de Skills

```
skills/
├── datetime/
│   └── SKILL.md
├── calculator/
│   └── SKILL.md
├── weather/
│   └── SKILL.md
└── notes/
    └── SKILL.md
```

Cada `SKILL.md` tiene frontmatter YAML (parseado con regex, sin PyYAML) + instrucciones en prosa:

```yaml
---
name: weather
description: Consultar el clima actual y pronóstico
version: 1
tools:
  - get_weather
---

Cuando el usuario pregunte por el clima, usá la tool `get_weather` con la ciudad.
Si no dice ciudad, preguntale cuál.
Respondé en el idioma del usuario.
```

#### Carga progresiva (patrón OpenClaw)

1. **Al iniciar**: se lee solo `name` y `description` de cada SKILL.md (~30 tokens por skill)
2. **Al usar una tool**: se carga el cuerpo del SKILL.md correspondiente (lazy, una vez por skill)
3. **Ejecución**: tool calling loop con max 5 iteraciones como safety cap

#### Tool calling via Ollama

`think: True` es incompatible con tools en qwen3. Cuando hay tools en el payload, se desactiva automáticamente. El flujo:

1. El mensaje del usuario llega con la lista de tools disponibles
2. Ollama responde con tool_calls en vez de texto
3. WasAP ejecuta cada tool, appendea resultados como role="tool"
4. Se reenvía a Ollama → puede llamar más tools o responder con texto
5. Después de MAX_TOOL_ITERATIONS (5), se fuerza respuesta sin tools

#### Skills implementados

| Skill | Tools | Mecanismo |
|-------|-------|-----------|
| `datetime` | `get_current_datetime`, `convert_timezone` | zoneinfo stdlib |
| `calculator` | `calculate` | AST safe eval (whitelist estricta, NO eval()) |
| `weather` | `get_weather` | wttr.in API (gratis, sin API key) |
| `notes` | `save_note`, `list_notes`, `search_notes`, `delete_note` | SQLite |

#### Reliability (incluido en Fase 4)

- **Dedup atómico**: tabla `processed_messages` con INSERT OR IGNORE (sin race conditions entre webhooks concurrentes)
- **Reply context**: si el usuario responde a un mensaje específico, se inyecta `[Replying to: "..."]` en el prompt
- **Graceful shutdown**: tracking de background tasks, wait con timeout de 30s antes de cerrar DB/HTTP

#### Extensibilidad

- Agregar un skill = crear carpeta con SKILL.md + registrar handlers en Python
- El directorio de skills es configurable via `SKILLS_DIR` (default: `skills/`)
- Sin skills disponibles, el sistema se comporta exactamente como antes (backward compatible)

### Fase 5: Memoria Avanzada
> Memoria semántica de largo plazo, inspirada en el [sistema de memoria de OpenClaw](https://docs.openclaw.ai/concepts/memory).

#### Modelo de memoria en dos capas (patrón OpenClaw)

OpenClaw separa la memoria en dos niveles:

| Capa | Archivo | Propósito | Carga |
|------|---------|-----------|-------|
| **Curada** | `data/MEMORY.md` | Hechos duraderos, preferencias, decisiones clave | Siempre (cada request) |
| **Diaria** | `data/memory/YYYY-MM-DD.md` | Notas del día, contexto temporal | Hoy + ayer |

El LLM puede **promocionar** información de notas diarias a MEMORY.md cuando detecta patrones recurrentes (ej: "el usuario siempre pide respuestas cortas" → se agrega a MEMORY.md).

#### Memory flush antes de compactación

Antes de que el summarizer borre mensajes viejos, se dispara un paso donde el LLM revisa si hay algo que debería persistir en MEMORY.md. Esto previene pérdida de información importante durante la compactación del historial.

#### Búsqueda semántica

- **Embeddings locales** via Ollama (`nomic-embed-text` o similar)
- **sqlite-vec** para almacenar y buscar vectores directamente en SQLite
- **Búsqueda híbrida**: vector similarity + FTS5 full-text (mismo patrón que OpenClaw)
  - Vector: captura equivalencia semántica ("mi cumpleaños" ≈ "fecha de nacimiento")
  - FTS5: exacto para nombres, fechas, códigos
  - Score combinado: `finalScore = vectorWeight * vecScore + textWeight * ftsScore`
- Los chunks de MEMORY.md y notas diarias se indexan automáticamente

#### RAG sobre documentos personales

- Directorio `data/docs/` para archivos del usuario (PDF, TXT, MD)
- Indexación automática con embeddings
- El LLM consulta documentos relevantes cuando necesita información específica

#### MEMORY.md bidireccional

En Fase 2, MEMORY.md es un mirror de solo escritura (SQLite → archivo). En Fase 5:
- Editar MEMORY.md a mano → se sincroniza a SQLite
- File watcher detecta cambios y actualiza la DB
- El usuario puede curar sus memorias editando un archivo de texto

---

## 5. Modelo de Datos (SQLite)

### Actual (Fase 1-4)

```
conversations
├── id            INTEGER PRIMARY KEY
├── phone_number  TEXT UNIQUE
├── created_at    TEXT
└── updated_at    TEXT

messages
├── id              INTEGER PRIMARY KEY
├── conversation_id INTEGER FK
├── role            TEXT (user/assistant/system)
├── content         TEXT
├── wa_message_id   TEXT UNIQUE
└── created_at      TEXT

summaries
├── id              INTEGER PRIMARY KEY
├── conversation_id INTEGER FK
├── content         TEXT
├── message_count   INTEGER
└── created_at      TEXT

memories
├── id         INTEGER PRIMARY KEY
├── content    TEXT
├── category   TEXT (nullable)
├── active     INTEGER (soft delete)
└── created_at TEXT

notes
├── id         INTEGER PRIMARY KEY
├── title      TEXT
├── content    TEXT
└── created_at TEXT

processed_messages
└── wa_message_id  TEXT PRIMARY KEY  (dedup atómico)
└── processed_at   TEXT
```

### Futuro (Fase 5)

```
embeddings (sqlite-vec)
├── id         INTEGER PRIMARY KEY
├── source     TEXT (memory/note/doc)
├── source_id  INTEGER
├── chunk      TEXT
├── vector     BLOB
└── created_at TEXT
```

---

## 6. Modelos Recomendados (Ollama)

| Modelo | Params | RAM Mín. | Caso de uso | Español | Tools |
|---|---|---|---|---|---|
| `qwen2.5:7b` | 7B | 8GB | **Recomendado para empezar** | Excelente | Sí |
| `qwen3:8b` | 8B | 8GB | Más nuevo, mejor razonamiento | Excelente | Sí |
| `llama3.2:8b` | 8B | 8GB | Balance velocidad/calidad | Bueno | Sí |
| `llama3.2:3b` | 3B | 4GB | Hardware limitado | Aceptable | Limitado |
| `llava:7b` | 7B | 8GB | Multimodal — imágenes (Fase 3) | Limitado | No |
| `nomic-embed-text` | — | 1GB | Embeddings (Fase 5) | Sí | — |

**Recomendación**: usar `qwen3:8b` para chat + tool calling y `llava:7b` para visión.

---

## 7. Configuración Necesaria (Meta Developer)

Para usar WhatsApp Cloud API necesitás:

1. **Cuenta de Meta Developer** (gratis) → developers.facebook.com
2. **Crear una App** tipo "Business"
3. **Agregar producto WhatsApp** a la app
4. **Número de prueba**: Meta te da un número de test gratuito
5. **Webhook URL**: tu dominio ngrok estático
6. **Verify token**: string secreto que elegís vos
7. **Access token**: lo genera la plataforma (permanente con System User)

Todo gratis. El número de test tiene limitación de 5 destinatarios en modo desarrollo, pero para uso personal (vos mismo) es suficiente.

---

## 8. Seguridad

- **Validación de firma**: verificar `X-Hub-Signature-256` en cada webhook (evita requests falsos)
- **Whitelist**: solo procesar mensajes de tu número
- **Variables de entorno**: tokens y secrets en `.env`, nunca hardcodeados
- **ngrok**: el túnel usa HTTPS automáticamente
- **SQLite**: opcionalmente cifrar con SQLCipher
- **Rate limiting**: máximo N mensajes por minuto (Fase 3)
- **No logging de tokens**: cuidado con los logs
- **Skills sandboxing**: los skills no pueden ejecutar código arbitrario, solo tools pre-definidas (Fase 4)

---

## 9. Requisitos del Sistema

- **Docker** y **Docker Compose**
- **ngrok** instalado (CLI) o como container
- **RAM**: 8GB mínimo (16GB recomendado)
- **GPU**: opcional pero 5-20x más rápido (pass-through con `nvidia-container-toolkit` si usás NVIDIA)
- **Disco**: ~5GB por modelo 7B + ~500MB imagen Docker + SQLite negligible
- **Internet**: necesaria (WhatsApp Cloud API + ngrok)
- **Cuenta Meta Developer** (gratis)

---

## 10. Métricas de Éxito

- Responde en <10s con GPU, <30s sin GPU
- No pierde mensajes (dedup por `wa_message_id`)
- Mantiene conversación coherente de 20+ mensajes
- Memorias persisten entre reinicios
- Se levanta con `docker compose up`
- Cero costos de operación mensuales
- Sin bans ni warnings de WhatsApp

---

## 11. Riesgos y Mitigaciones

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| ngrok free tiene downtime | Baja | Medio | Los mensajes quedan en cola de Meta, llegan al reconectar |
| Calidad LLM local | Media | Medio | System prompt bien diseñado, probar varios modelos |
| Latencia sin GPU | Alta | Medio | Modelos más chicos (3B), o invertir en GPU |
| Context window overflow | Media | Bajo | Resumen automático, truncar historial (implementado Fase 2) |
| Meta cambia pricing de Cloud API | Baja | Bajo | Monitorear, los mensajes de servicio son gratis desde 2023 |
| ngrok cambia free tier | Baja | Medio | Alternativas: cloudflare tunnel, localhost.run |
| Tool calling unreliable en modelos chicos | Media | Medio | Fallback a regex parsing, limitar tools por modelo |

---

## 12. Fuera de Alcance (No-Goals)

- Grupos de WhatsApp (solo chat 1:1)
- Interfaz web de admin
- Multi-usuario (es un asistente personal single-user)
- Fine-tuning de modelos
- Deploy en cloud/VPS
- Mensajes proactivos (el bot no inicia conversación, solo responde)
- Multi-canal (solo WhatsApp — a diferencia de OpenClaw que soporta Telegram, Slack, etc.)

---

## 13. Estrategia Docker

### Servicios en `docker-compose.yml`

| Servicio | Imagen | Propósito |
|---|---|---|
| `wasap` | Build local (Dockerfile) | App FastAPI |
| `ollama` | `ollama/ollama` | LLM server |
| `ngrok` | `ngrok/ngrok` (opcional) | Túnel al webhook |

### Volumes persistentes
- `ollama_data` → modelos descargados (no re-descargar en cada restart)
- `./data` → SQLite DB + MEMORY.md + documentos

### GPU pass-through
- Para NVIDIA: `nvidia-container-toolkit` + `deploy.resources.reservations.devices` en compose
- Sin GPU: Ollama corre en CPU automáticamente, no requiere config extra

### Workflow
```bash
# Primer uso
cp .env.example .env        # Configurar tokens
docker compose up -d         # Levanta todo
docker compose exec ollama ollama pull qwen3:8b   # Descargar modelo

# Uso diario
docker compose up -d         # Listo

# Ver logs
docker compose logs -f wasap
```

---

## 14. Comparación con OpenClaw

WasAP se inspira en varios patrones de OpenClaw pero con un enfoque más simple:

| Aspecto | OpenClaw | WasAP |
|---------|----------|-------|
| **Canales** | 12+ (WhatsApp, Telegram, Slack, Discord...) | Solo WhatsApp |
| **Usuarios** | Multi-agente, multi-usuario | Single-user |
| **LLM** | Cloud (Claude, GPT) + local | Solo local (Ollama) |
| **Skills** | 3000+ en ClawHub, carga en 3 tiers | Directorio local, carga progresiva |
| **Memoria** | MEMORY.md + daily notes + semantic search | MEMORY.md mirror + SQLite + semantic search (Fase 5) |
| **Identidad** | SOUL.md + AGENTS.md + USER.md | System prompt en .env |
| **Hosting** | Gateway WS local | FastAPI + ngrok |
| **Costo** | API keys de LLM cloud | Cero (todo local) |
| **Setup** | CLI install + gateway | `docker compose up` |

**Lo que tomamos de OpenClaw:**
- SKILL.md como definición declarativa de capacidades
- MEMORY.md como fuente de verdad human-readable
- Carga progresiva de skills (solo metadata al inicio, detalle on-demand)
- Memoria en dos capas (curada + diaria)
- Búsqueda híbrida (vector + full-text)

**Lo que NO tomamos:**
- Gateway WebSocket (innecesario para single-channel)
- Multi-agente (somos single-user)
- Marketplace de skills (comunidad, ClawHub)
- Node system para dispositivos (cámara, pantalla, etc.)
