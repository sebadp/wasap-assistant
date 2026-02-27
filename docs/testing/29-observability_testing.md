# Testing Manual: Observabilidad de Agentes y Mejora de Trazabilidad

> **Feature documentada**: [`docs/features/29-observability.md`](../features/29-observability.md)
> **Requisitos previos**: Container corriendo (`docker compose up -d`), modelos de Ollama disponibles. Langfuse opcional pero recomendado para smoke tests.

---

## Verificar que la feature está activa

Al arrancar el container, buscar en los logs:

```bash
docker compose logs -f wasap | head -60
```

Con Langfuse configurado, confirmar:
- `INFO: Langfuse tracing enabled`

Sin Langfuse (solo SQLite):
- No habrá línea de Langfuse; tracing funciona igual en SQLite

---

## Tests unitarios

Los tests automatizados cubren las partes críticas:

```bash
# Tests de TraceRecorder singleton y ChatResponse métricas
.venv/bin/python -m pytest tests/test_tracing.py -v

# Tests de spans agénticos (planner/worker)
.venv/bin/python -m pytest tests/test_agent_tracing.py -v
```

Tests incluidos:
- `test_trace_recorder_create_without_keys` — langfuse=None si sin keys
- `test_trace_recorder_create_with_langfuse_keys` — Langfuse inicializado con keys
- `test_trace_recorder_create_langfuse_init_failure` — falla graceful si SDK falla
- `test_chat_response_includes_token_counts` — ChatResponse captura eval_count y prompt_eval_count
- `test_chat_response_handles_missing_token_fields` — None si campos ausentes en respuesta Ollama
- `test_execute_tool_loop_creates_generation_span` — span llm:iteration_1 creado en tool loop
- `test_tool_output_captures_1000_chars` — output no truncado a 200 chars
- `test_agent_session_creates_trace_when_recorder_provided` — TraceContext creado
- `test_agent_session_no_trace_without_recorder` — funciona sin recorder
- `test_planner_creates_span` — spans planner:create_plan y planner:synthesize
- `test_worker_creates_span_with_parent` — spans worker:task_1 y worker:task_2

---

## Casos de prueba principales (Smoke Tests)

### Flujo normal con tools

| Acción | Resultado esperado |
|---|---|
| Enviar "¿Qué hora es?" | Tool `get_current_datetime` invocada. En Langfuse: trace con span `tool_loop` → `llm:iteration_1` (generation con tokens) → `tool:get_current_datetime` |
| Enviar "Cuál es el clima en Buenos Aires" | Cadena completa en Langfuse con tokens capturados en span `llm:iteration_1` |
| Enviar "Hola, cómo estás?" | Sin tools. Span `llm:chat` (generation) con tokens. Sin `tool_loop` span |

### Flujo agéntico

| Acción | Resultado esperado |
|---|---|
| `/dev-review` | En Langfuse: trace con `message_type=agent`. Span `planner:create_plan` con JSON del plan. Spans `worker:task_N` para cada tarea |
| `/dev-review` con múltiples tasks | Múltiples spans `worker:task_1`, `worker:task_2`, etc. anidados correctamente |

---

## Verificar en Langfuse UI

1. Abrir `https://cloud.langfuse.com` (o tu instancia)
2. Ir a **Traces**
3. Buscar la última traza — verificar:
   - Span tree jerárquico visible (no lista plana)
   - Span `tool_loop` → hijos `llm:iteration_N` → nietos `tool:nombre`
   - En spans de generación: sección "Usage" con input/output tokens
   - `user_id` = número de teléfono

### Para sesiones agénticas:
- Filtrar por `metadata.message_type = "agent"`
- Verificar span `planner:create_plan` con output del plan
- Verificar `worker:task_N` con input (description, worker_type) y output (result)

---

## Verificar en logs

```bash
# Verificar que TraceRecorder se inicializa correctamente
docker compose logs wasap 2>&1 | grep -i "langfuse"

# Verificar spans de workers
docker compose logs -f wasap 2>&1 | grep "Worker \["

# Errores de tracing (best-effort, no deben romper el flujo)
docker compose logs wasap 2>&1 | grep "TraceRecorder"
```

---

## Queries de verificación en DB

```bash
# Ver traces recientes
sqlite3 data/wasap.db "SELECT id, phone_number, message_type, status, created_at FROM traces ORDER BY created_at DESC LIMIT 5;"

# Ver spans de un trace específico
sqlite3 data/wasap.db "SELECT name, kind, status, latency_ms FROM trace_spans WHERE trace_id = '<trace_id>' ORDER BY created_at;"

# Verificar que hay spans de tipo 'generation'
sqlite3 data/wasap.db "SELECT name, kind, COUNT(*) FROM trace_spans GROUP BY name, kind ORDER BY COUNT(*) DESC LIMIT 20;"

# Verificar metadata de tokens en spans
sqlite3 data/wasap.db "SELECT name, metadata FROM trace_spans WHERE name LIKE 'llm:%' LIMIT 5;"
```

---

## Verificar graceful degradation

### Sin Langfuse keys:

1. En `.env`, borrar o vaciar `LANGFUSE_PUBLIC_KEY` y `LANGFUSE_SECRET_KEY`
2. Reiniciar el container
3. Verificar que el sistema funciona normalmente (sin crash)
4. Verificar que traces se siguen guardando en SQLite
5. Logs NO deben mostrar "Langfuse tracing enabled"

### Con Langfuse caído:

1. En `.env`, poner keys inválidas: `LANGFUSE_PUBLIC_KEY=fake` `LANGFUSE_SECRET_KEY=fake`
2. Reiniciar
3. Verificar que logs muestran `WARNING: Failed to initialize Langfuse client`
4. Sistema debe funcionar normalmente — tracing en SQLite sigue funcionando

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| Spans aparecen como lista plana (no árbol) en Langfuse | `parent_span_id` no propagado | Verificar que `execute_tool_loop` recibe y usa `parent_span_id` |
| Tokens siempre `None` en spans | Ollama no devuelve `eval_count` | Verificar versión de Ollama — v0.1.x+ incluye métricas. Verificar que el modelo no hace streaming |
| "Failed to initialize Langfuse client" en startup | Keys incorrectas o host inalcanzable | Verificar keys en `.env` y conectividad a `LANGFUSE_HOST` |
| `TraceRecorder.finish_trace failed` en logs DEBUG | Error al guardar en SQLite | Verificar que `data/wasap.db` existe y tiene permisos correctos |
| Sesiones agénticas sin trace | `recorder=None` pasado a `run_agent_session` | Verificar que `CommandContext.trace_recorder` se setea en `process_message` |

---

## Variables relevantes para testing

| Variable (`.env`) | Valor de test | Efecto |
|---|---|---|
| `TRACING_ENABLED` | `true` / `false` | Activa/desactiva tracing completo |
| `LANGFUSE_PUBLIC_KEY` | key real o vacío | Activa/desactiva envío a Langfuse |
| `LANGFUSE_SECRET_KEY` | key real o vacío | Activa/desactiva envío a Langfuse |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | URL del servidor Langfuse |
| `TRACE_RETENTION_DAYS` | `30` | Días de retención en SQLite |
