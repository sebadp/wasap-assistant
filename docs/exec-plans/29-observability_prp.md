# PRP: Observabilidad de Agentes y Mejora de Trazabilidad

## Objetivo

Instrumentar el agent loop con spans jerárquicos, capturar métricas de generación LLM,
y mejorar calidad de datos de tracing. Ver PRD para contexto y decisiones arquitectónicas.

## Archivos a Modificar

| Archivo | Cambio |
|---|---|
| `app/llm/client.py` | Extender `ChatResponse` con `input_tokens`, `output_tokens`, `model`, `total_duration_ms`. Extraer de response JSON de Ollama |
| `app/tracing/recorder.py` | Eliminar `Settings()` del constructor, recibir Langfuse ya inicializado. Agregar classmethod `create()` para init |
| `app/main.py` | Inicializar `TraceRecorder` como singleton en `app.state` durante lifespan |
| `app/webhook/router.py` | Usar `TraceRecorder` de `app.state`. Agregar span `kind="generation"` para LLM principal. Pasar `parent_span_id` a `execute_tool_loop()` |
| `app/skills/executor.py` | Aceptar `parent_span_id` en `execute_tool_loop()` y `_run_tool_call()`. Agregar span `kind="generation"` para cada iteración LLM. Incrementar tool output a 1000 chars |
| `app/agent/loop.py` | Crear `TraceContext` en `run_agent_session()`. Spans para planner/worker/replan/synthesize |
| `app/agent/planner.py` | Retornar `ChatResponse` (con tokens) desde `create_plan()`, `replan()`, `synthesize()` para que el caller pueda loguear métricas |
| `app/agent/workers.py` | Pasar trace context al inner `execute_tool_loop()` |
| `tests/test_tracing.py` | Tests para singleton, generación spans, token capture |
| `tests/test_agent_tracing.py` | Tests para spans agénticos |
| `docs/exec-plans/README.md` | Agregar entrada 29 |

## Phase 1: Métricas de Ollama en `ChatResponse`

- [ ] Extender `ChatResponse` en `app/llm/client.py`:
  - Agregar campos opcionales: `input_tokens: int | None = None`, `output_tokens: int | None = None`, `model: str | None = None`, `total_duration_ms: float | None = None`
  - En `chat_with_tools()`, extraer de `data` (response JSON de Ollama):
    - `data.get("prompt_eval_count")` → `input_tokens`
    - `data.get("eval_count")` → `output_tokens`
    - `use_model` → `model`
    - `data.get("total_duration")` → convertir de nanoseconds a ms → `total_duration_ms`
  - En `chat()`, propagar el `ChatResponse` completo (actualmente retorna solo `str` — no cambiar la firma, pero el response interno tiene los datos)
- [ ] Agregar tests en `tests/test_llm_client.py`:
  - `test_chat_response_includes_token_counts` — mock de response JSON de Ollama con `eval_count` y `prompt_eval_count`
  - `test_chat_response_handles_missing_token_fields` — response sin esos campos → `None`

## Phase 2: Singleton de `TraceRecorder`

- [ ] Refactorear `TraceRecorder.__init__()` en `app/tracing/recorder.py`:
  - Eliminar `Settings()` del constructor
  - Constructor recibe `repository` y `langfuse: Langfuse | None` (ya inicializado)
  - Agregar classmethod `create(repository) -> TraceRecorder` que lee `Settings()` e inicializa Langfuse (factory method)
- [ ] En `app/main.py` lifespan:
  - Después de inicializar `repository`, crear `recorder = TraceRecorder.create(repository)`
  - Guardar como `app.state.trace_recorder = recorder`
  - En shutdown, si `recorder.langfuse`: llamar `recorder.langfuse.flush()` para asegurar envío final
- [ ] En `app/webhook/router.py`:
  - Reemplazar `recorder = TraceRecorder(repository)` por `recorder = app.state.trace_recorder`
  - Agregar `recorder` como parámetro de `process_message()` o acceder via dependency injection
- [ ] Agregar `get_trace_recorder()` en `app/dependencies.py` (misma pattern que `get_repository()`)
- [ ] Tests: `test_trace_recorder_singleton_reused` — verificar que la misma instancia se usa

## Phase 3: Span de generación LLM en flujo normal

- [ ] En `app/skills/executor.py`:
  - `execute_tool_loop()` acepta nuevo param `parent_span_id: str | None = None`
  - Dentro del `for iteration` loop, wrappear `ollama_client.chat_with_tools()` en:
    ```python
    trace = get_current_trace()
    if trace:
        async with trace.span(f"llm:iteration_{iteration+1}", kind="generation", parent_id=parent_span_id) as gen_span:
            response = await ollama_client.chat_with_tools(working_messages, tools=tools)
            gen_span.set_metadata({
                "gen_ai.usage.input_tokens": response.input_tokens,
                "gen_ai.usage.output_tokens": response.output_tokens,
                "gen_ai.request.model": response.model,
            })
            gen_span.set_input({"message_count": len(working_messages), "tool_count": len(tools)})
            gen_span.set_output({"content": response.content[:500], "tool_calls_count": len(response.tool_calls or [])})
    else:
        response = await ollama_client.chat_with_tools(working_messages, tools=tools)
    ```
  - `_run_tool_call()` acepta `parent_span_id: str | None = None`
    - Pasar `parent_id=parent_span_id` al `trace.span()` existente (linea 160)
    - Dentro del loop, pasar el `gen_span.span_id` como parent a `_run_tool_call()`
  - Incrementar tool output capture: `result.content[:200]` → `result.content[:1000]`
- [ ] En `app/webhook/router.py`:
  - En `_run_normal_flow()`, wrappear la llamada `execute_tool_loop()` con un span:
    ```python
    if trace_ctx:
        async with trace_ctx.span("tool_loop", kind="span") as loop_span:
            reply = await execute_tool_loop(..., parent_span_id=loop_span.span_id)
    ```
  - Para el fallback `ollama_client.chat()` (sin tools), agregar span `kind="generation"`:
    ```python
    if trace_ctx:
        async with trace_ctx.span("llm:chat", kind="generation") as gen_span:
            response = await ollama_client.chat_with_tools(...)
            gen_span.set_metadata({...tokens...})
            reply = response.content
    ```
- [ ] Tests en `tests/test_tool_executor.py`:
  - `test_execute_tool_loop_creates_generation_spans` — mock trace, verificar que `span()` se llama con `kind="generation"`
  - `test_tool_output_captures_1000_chars` — verificar que el output no se trunca a 200

## Phase 4: Instrumentación del agent loop

- [ ] En `app/agent/loop.py`, dentro de `run_agent_session()`:
  - Import `TraceContext`, `TraceRecorder`
  - Obtener `recorder` (pasado como param o importado desde dependencies)
  - Wrappear el cuerpo principal en `TraceContext`:
    ```python
    if settings.tracing_enabled:
        async with TraceContext(
            phone_number=session.phone_number,
            input_text=session.objective,
            recorder=recorder,
            message_type="agent",
        ) as trace_ctx:
            # ... existing logic ...
    ```
  - Agregar `session_id` como metadata: `trace_ctx` gets metadata via recorder
- [ ] En `_run_planner_session()`:
  - Span `planner:create_plan` wrapping `create_plan()`:
    ```python
    trace = get_current_trace()
    if trace:
        async with trace.span("planner:create_plan", kind="generation") as span:
            plan = await create_plan(...)
            span.set_output({"tasks": len(plan.tasks), "plan": plan.to_markdown()[:500]})
    ```
  - Span `worker:task_{task.id}` wrapping cada `execute_worker()`:
    ```python
    if trace:
        async with trace.span(f"worker:task_{task.id}", kind="span") as worker_span:
            worker_span.set_input({"description": task.description, "worker_type": task.worker_type})
            result = await execute_worker(..., parent_span_id=worker_span.span_id)
            worker_span.set_output({"result": result[:500], "status": task.status})
    ```
  - Span `planner:replan` wrapping `replan()` (si aplica)
  - Span `planner:synthesize` wrapping `synthesize()`
- [ ] En `_run_reactive_session()`:
  - Span `reactive:round_{iteration+1}` wrapping cada iteración del loop
  - Pasar span_id como `parent_span_id` a `execute_tool_loop()`
- [ ] En `app/agent/workers.py`:
  - `execute_worker()` acepta `parent_span_id: str | None = None`
  - Pasarlo a `execute_tool_loop()` interno
- [ ] Pasar `recorder` a `run_agent_session()`:
  - Agregar `recorder: TraceRecorder | None = None` como param
  - En `builtins.py` donde se llama, pasar `recorder` desde `context`
  - `CommandContext` extendido con `trace_recorder` field

## Phase 5: Tests

- [ ] `tests/test_tracing.py` (nuevos o extender existentes):
  - `test_trace_recorder_create_with_langfuse_keys` — mock Langfuse SDK, verificar init
  - `test_trace_recorder_create_without_keys` — `langfuse` queda None
  - `test_generation_span_includes_token_metadata` — mock recorder, verificar metadata OTel
- [ ] `tests/test_agent_tracing.py` (nuevo archivo):
  - `test_agent_session_creates_trace_context` — mock recorder, verificar que se crea trace
  - `test_planner_creates_span` — verificar span `planner:create_plan`
  - `test_worker_creates_span_with_parent` — verificar parent linking
  - `test_agent_trace_includes_session_metadata` — verificar `session_id` en metadata

## Phase 6: Verificación y Documentación

- [ ] Correr `make check` (lint + typecheck + tests) — 0 errores
- [ ] Smoke test Langfuse: enviar mensaje por WhatsApp, verificar en UI de Langfuse:
  - Trace visible con spans jerárquicos
  - Tokens de input/output en span de generación
  - Tool outputs de 1000 chars
- [ ] Smoke test agente: ejecutar `/agent listar archivos`, verificar en Langfuse:
  - Trace con `message_type=agent`
  - Span `planner:create_plan` con plan JSON
  - Spans `worker:task_N` con tool calls como hijos
- [ ] Actualizar `CLAUDE.md` con patrones nuevos:
  - `TraceRecorder` singleton en `app.state`
  - `ChatResponse` con métricas de Ollama
  - Agent loop tracing pattern
  - `parent_span_id` threading pattern
- [ ] Actualizar `docs/exec-plans/README.md` con entrada 29
- [ ] Crear `docs/features/29-observability.md` con documentación de la feature
- [ ] Crear `docs/testing/29-observability_testing.md` con guía de testing
