# Feature: Observabilidad de Agentes y Mejora de Trazabilidad

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-27
> **Fase**: Agent Mode / Fase 8
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Instrumenta el agent loop y el tool executor con spans jerárquicos para Langfuse, captura métricas de tokens y latencia de cada llamada a Ollama, y convierte el `TraceRecorder` en singleton para evitar múltiples clientes Langfuse por request.

---

## Arquitectura

```
[WhatsApp Message]
       │
       ▼
[router.py: _run_normal_flow()]
   TraceContext (trace_id) ──────────────────────────────────────────────────┐
       │                                                                      │
       ├─ span "tool_loop" (kind=span) ─────────────────────────────────────┤
       │      │                                                               │
       │      ├─ span "llm:iteration_1" (kind=generation) → tokens captured  │
       │      │      └─ span "tool:get_weather" (kind=tool)                  │
       │      └─ span "llm:iteration_2" (kind=generation) → final reply      │
       │                                                                      │
       └─ span "llm:chat" (kind=generation) [sin tools, direct chat]         │
                                                                              │
[agent/loop.py: run_agent_session()]                                          │
   TraceContext (message_type="agent") ─────────────────────────────────────┤
       │                                                                      │
       ├─ span "planner:create_plan" (kind=generation)                       │
       ├─ span "worker:task_1" (kind=span) ──────────────────────────────────┤
       │      └─ (inner execute_tool_loop con parent_span_id)                │
       ├─ span "worker:task_2" (kind=span)                                   │
       ├─ span "planner:replan" (kind=generation) [si aplica]                │
       └─ span "planner:synthesize" (kind=generation)                        │
                                                                              │
[TraceRecorder singleton en app.state] ──────────────────────────────────────┘
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/llm/client.py` | `ChatResponse` extendido con `input_tokens`, `output_tokens`, `model`, `total_duration_ms` |
| `app/tracing/recorder.py` | `TraceRecorder.create()` classmethod — singleton factory |
| `app/main.py` | Inicializa singleton `TraceRecorder` en `app.state.trace_recorder` |
| `app/dependencies.py` | `get_trace_recorder()` dependency |
| `app/webhook/router.py` | Usa singleton; spans `tool_loop` y `llm:chat`; pasa `parent_span_id` a executor |
| `app/skills/executor.py` | Spans `llm:iteration_N` (generation) y `tool:name` (tool) con parent linking |
| `app/agent/loop.py` | `TraceContext` para sesiones agénticas; spans planner/worker/synthesize |
| `app/agent/workers.py` | Propaga `parent_span_id` a `execute_tool_loop` |
| `app/commands/context.py` | `CommandContext.trace_recorder` field |
| `app/commands/builtins.py` | Pasa `recorder=context.trace_recorder` a `run_agent_session` |
| `tests/test_tracing.py` | Tests: singleton, token capture, generation spans |
| `tests/test_agent_tracing.py` | Tests: agent trace creation, planner/worker spans |

---

## Walkthrough técnico: cómo funciona

### Métricas de Ollama en `ChatResponse`

1. **`chat_with_tools()` extrae métricas** → `app/llm/client.py`
   - `data.get("prompt_eval_count")` → `input_tokens`
   - `data.get("eval_count")` → `output_tokens`
   - `data.get("total_duration") / 1_000_000` → `total_duration_ms`
   - `use_model` → `model`

2. **Span de generación captura metadata OTel** → `app/skills/executor.py`
   ```python
   gen_span.set_metadata({
       "gen_ai.usage.input_tokens": response.input_tokens,
       "gen_ai.usage.output_tokens": response.output_tokens,
       "gen_ai.request.model": response.model,
   })
   ```
   Langfuse mapea estos tags automáticamente a su sección "Usage".

### Singleton de TraceRecorder

1. **`TraceRecorder.create(repository)`** → `app/tracing/recorder.py`
   - Lee `Settings()` una sola vez
   - Inicializa `Langfuse(public_key=..., secret_key=..., host=...)` una vez
   - Retorna instancia con el cliente Langfuse ya creado

2. **Stored in `app.state`** → `app/main.py` lifespan
   - `app.state.trace_recorder = TraceRecorder.create(repository)`
   - En shutdown: `recorder.langfuse.flush()` — garantiza envío final de eventos pendientes

3. **Inyectado via dependency** → `app/dependencies.py`
   - `get_trace_recorder(request)` retorna `request.app.state.trace_recorder`

### Spans jerárquicos en el flujo normal

```
TraceContext (trace root)
  └─ tool_loop (span)
       ├─ llm:iteration_1 (generation) — input_tokens=X, output_tokens=Y
       │    └─ tool:get_current_datetime (tool)
       └─ llm:iteration_2 (generation) — final reply
```

- `execute_tool_loop` recibe `parent_span_id` del `tool_loop` span
- Cada iteración crea un span de generación con el `parent_span_id` del tool_loop
- `_run_tool_call` recibe el `iteration_span_id` como parent → cada tool es hijo de su iteración LLM

### Spans agénticos

```
TraceContext (message_type="agent")
  ├─ planner:create_plan (generation)
  ├─ worker:task_1 (span)
  │    ├─ llm:iteration_1 (generation)
  │    │    └─ tool:list_files (tool)
  │    └─ llm:iteration_2 (generation)
  ├─ worker:task_2 (span)
  ├─ planner:replan (generation) [opcional]
  └─ planner:synthesize (generation)
```

- `run_agent_session` crea el `TraceContext` con `message_type="agent"` si se pasa `recorder`
- `_run_agent_body` (inner function) usa `get_current_trace()` via contextvar — sin cambiar firmas
- `execute_worker` propaga `parent_span_id` del worker span a `execute_tool_loop`

---

## Cómo extenderla

- **Para agregar métricas nuevas de Ollama**: extender `ChatResponse` en `client.py` y agregar el campo a `gen_span.set_metadata()` en `executor.py`
- **Para agregar un nuevo tipo de span en el agent loop**: usar `get_current_trace()` en `loop.py` y abrir un span con `trace.span("nombre", kind="span|generation|tool")`
- **Para cambiar el sample rate de tracing**: ajustar `TRACING_SAMPLE_RATE` en `config.py`
- **Para deshabilitar Langfuse** (solo SQLite): no setear `LANGFUSE_PUBLIC_KEY` y `LANGFUSE_SECRET_KEY` en `.env`

---

## Guía de testing

→ Ver [`docs/testing/29-observability_testing.md`](../testing/29-observability_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| `TraceRecorder` singleton en `app.state` | Instanciar por request | Langfuse SDK crea un background flush thread al inicializar — recrearlo por request causaba leak de threads |
| `classmethod create()` como factory | Pasar `Settings` al constructor | Permite testear el constructor directamente con un `langfuse=None` mock sin tocar Settings |
| `parent_span_id` threading explícito | Confiar solo en contextvar | contextvar propaga el trace root, pero el parent span cambia en cada iteración — necesita ser explícito |
| `_run_agent_body` inner function | Duplicar código con/sin TraceContext | Evita duplicación; `TraceContext` como wrapper opcional en `run_agent_session` |
| `message_type="agent"` en trace de sesión | Un único tipo de trace | Permite filtrar en Langfuse por tipo de interacción (chat vs agente) |

---

## Gotchas y edge cases

- **Langfuse stubs**: mypy reporta 7 errores pre-existentes en `recorder.py` porque `langfuse` no tiene stubs de tipos completos — son errores pre-existentes, no introducidos por esta feature
- **`if not tools: return`**: si el executor sale antes del loop (sin tools seleccionadas), no se crea ningún span de generación — normal, el LLM no fue invocado
- **contextvar en agent loop**: `TraceContext` usa `contextvars.ContextVar` — las sub-coroutines del agent body heredan el trace automáticamente. Si se usa `asyncio.create_task` sin `copy_context()`, el trace no se propagaría
- **Langfuse flush en shutdown**: se llama `langfuse.flush()` sincrónicamente en el lifespan de FastAPI antes del `yield` final — garantiza que todos los eventos en el buffer del SDK se envíen

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `tracing_enabled` | `True` | Activa SQLite tracing + Langfuse si keys presentes |
| `langfuse_public_key` | `""` | Si vacío, Langfuse deshabilitado (solo SQLite) |
| `langfuse_secret_key` | `""` | Si vacío, Langfuse deshabilitado |
| `langfuse_host` | `"https://cloud.langfuse.com"` | URL del servidor Langfuse |
| `trace_retention_days` | `30` | Días antes de limpiar traces en SQLite |
