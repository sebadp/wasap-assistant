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
                                 │  dominio estático│
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
                                 │  │  ├─ Message router      │        │
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
5. Se carga el historial de conversación de SQLite
6. Se arma el prompt (system + memoria + historial + mensaje nuevo)
7. Se envía a Ollama API local (`localhost:11434`)
8. La respuesta se envía de vuelta via WhatsApp Cloud API
9. Se guarda el intercambio en SQLite

---

## 3. Stack Tecnológico

| Componente | Tecnología | Por qué |
|---|---|---|
| Servidor | **Python 3.11+ / FastAPI** | Async, rápido, ideal para webhooks |
| WhatsApp | **WhatsApp Cloud API** (oficial) | Gratis para servicio, sin riesgo de ban |
| Túnel | **ngrok** (free tier) | Dominio estático gratis, sin timeout, 1GB/mes sobra |
| LLM | **Ollama** | Local, gratuito, múltiples modelos |
| Base de datos | **SQLite** (WAL mode) | Sin servidor, suficiente para 1 usuario |
| Config | **archivo .env** | Simple, estándar |
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

### Fase 1: MVP - Chat funcional
> Poder mandar un mensaje por WhatsApp y recibir respuesta del LLM local.

- Webhook receiver con validación de firma de Meta
- Envío de respuestas via Cloud API
- Conexión a Ollama API (`/api/chat`)
- System prompt configurable
- Historial de conversación en memoria (últimos N mensajes)
- Whitelist de números (solo responde a tu número)
- Indicador de "visto" / acuse de recibo
- Health check endpoint
- Script de setup (guía para crear app en Meta Developer Portal)
- **Dockerizado**: Dockerfile + docker-compose.yml (wasap + ollama como servicios)
- Volume para SQLite y modelos de Ollama (persistencia entre reinicios)
- ngrok corre en host o como servicio adicional en compose

### Fase 2: Persistencia y Memoria
> El asistente recuerda conversaciones anteriores y datos que le pedís guardar.

- Almacenar conversaciones en SQLite
- Cargar últimos N mensajes como contexto al recibir mensaje nuevo
- Resumen automático de conversaciones largas (evitar overflow de context window)
- Comandos de usuario:
  - `/remember <dato>` - guardar info importante
  - `/forget <dato>` - borrar info guardada
  - `/memories` - listar datos guardados
  - `/clear` - limpiar historial de conversación
- Inyectar memorias relevantes en el system prompt

### Fase 3: UX y Multimedia
> El asistente se siente más natural y maneja más que texto.

- Mensajes de audio entrantes → transcripción con Whisper (local via Ollama)
- Imágenes entrantes → descripción con modelo multimodal (llava)
- Formato WhatsApp en respuestas (negritas, listas, cursiva)
- Respuestas largas divididas en múltiples mensajes
- Manejo de errores user-friendly (Ollama caído, timeout, etc.)
- Rate limiting (prevenir loops)
- Logging estructurado

### Fase 4: Herramientas
> El asistente puede hacer cosas, no solo conversar.

- Tool calling via Ollama (modelos compatibles)
- Herramientas iniciales:
  - Recordatorios (scheduler local)
  - Clima (API pública)
  - Notas / listas de tareas persistentes
  - Cálculos
  - Búsqueda web
- Arquitectura de plugins extensible

### Fase 5: Memoria Avanzada (futuro)
> Memoria semántica de largo plazo.

- Embeddings locales (via Ollama)
- Búsqueda semántica con sqlite-vec
- RAG sobre documentos/notas personales
- Auto-resumen periódico de conversaciones

---

## 5. Modelo de Datos (SQLite)

```
conversations
├── id            INTEGER PRIMARY KEY
├── phone_number  TEXT
├── created_at    TIMESTAMP
└── updated_at    TIMESTAMP

messages
├── id              INTEGER PRIMARY KEY
├── conversation_id INTEGER FK
├── role            TEXT (user/assistant/system)
├── content         TEXT
├── wa_message_id   TEXT (ID de WhatsApp, para dedup)
├── token_count     INTEGER
└── created_at      TIMESTAMP

memories
├── id          INTEGER PRIMARY KEY
├── content     TEXT
├── category    TEXT (nullable)
├── created_at  TIMESTAMP
└── active      BOOLEAN

config
├── key    TEXT PRIMARY KEY
└── value  TEXT
```

---

## 6. Modelos Recomendados (Ollama)

| Modelo | Params | RAM Mín. | Caso de uso | Español |
|---|---|---|---|---|
| `qwen2.5:7b` | 7B | 8GB | **Recomendado para empezar** | Excelente |
| `llama3.2:8b` | 8B | 8GB | Balance velocidad/calidad | Bueno |
| `mistral:7b` | 7B | 8GB | Buen razonamiento | Aceptable |
| `llama3.2:3b` | 3B | 4GB | Hardware limitado | Aceptable |
| `llava:7b` | 7B | 8GB | Multimodal (fase 3) | Limitado |
| `qwen3:8b` | 8B | 8GB | Más nuevo, function calling | Excelente |

**Recomendación**: empezar con `qwen2.5:7b` o `qwen3:8b` por su buen soporte de español y function calling.

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
- **Rate limiting**: máximo N mensajes por minuto
- **No logging de tokens**: cuidado con los logs

---

## 9. Requisitos del Sistema

- **Docker** y **Docker Compose**
- **ngrok** instalado (CLI) o como container
- **RAM**: 8GB mínimo (16GB recomendado)
- **GPU**: opcional pero 5-20x más rápido (pass-through con `nvidia-container-toolkit` si usás NVIDIA)
- **Disco**: ~5GB por modelo 7B + ~500MB imagen Docker
- **Internet**: necesaria (WhatsApp Cloud API + ngrok)
- **Cuenta Meta Developer** (gratis)

---

## 10. Métricas de Éxito (MVP)

- Responde en <10s con GPU, <30s sin GPU
- No pierde mensajes (dedup por `wa_message_id`)
- Mantiene conversación coherente de 20+ mensajes
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
| Context window overflow | Media | Bajo | Resumen automático, truncar historial |
| Meta cambia pricing de Cloud API | Baja | Bajo | Monitorear, los mensajes de servicio son gratis desde 2023 |
| ngrok cambia free tier | Baja | Medio | Alternativas: cloudflare tunnel, localhost.run |

---

## 12. Fuera de Alcance (No-Goals)

- Grupos de WhatsApp (solo chat 1:1)
- Interfaz web de admin
- Multi-usuario
- Fine-tuning de modelos
- Deploy en cloud/VPS
- Mensajes proactivos (el bot no inicia conversación, solo responde)

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
- `wasap_data` → SQLite DB + archivos de configuración

### GPU pass-through
- Para NVIDIA: `nvidia-container-toolkit` + `deploy.resources.reservations.devices` en compose
- Sin GPU: Ollama corre en CPU automáticamente, no requiere config extra

### Workflow
```bash
# Primer uso
cp .env.example .env        # Configurar tokens
docker compose up -d         # Levanta todo
docker compose exec ollama ollama pull qwen2.5:7b  # Descargar modelo

# Uso diario
docker compose up -d         # Listo

# Ver logs
docker compose logs -f wasap
```
