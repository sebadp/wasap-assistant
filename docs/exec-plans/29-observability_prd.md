# PRD: Observabilidad de Agentes y Mejora de Trazabilidad

## 1. Objetivo y Contexto

WasAP tiene un sistema de trazabilidad funcional (SQLite + Langfuse dual-backend) para el flujo
normal de mensajes, pero el flujo agéntico (planner-orchestrator) es completamente invisible:
no genera spans, no captura pasos intermedios, y no se correlaciona con traces. Además, la
llamada LLM principal no tiene span de generación, los tokens de Ollama se descartan, y los
tool outputs se truncan agresivamente.

**Problema observado:** El usuario configuró Langfuse con variables de entorno pero no veía
traces porque las vars no estaban en `.env` (ya corregido). Ahora que Langfuse recibe datos,
la calidad de lo que se reporta es insuficiente para debugging de agentes.

**Objetivo:** Instrumentar el agent loop completo con spans jerárquicos, capturar métricas
de generación LLM (tokens, latencia, modelo), y mejorar la calidad de datos de tracing
para que Langfuse sea una herramienta útil de debugging y observabilidad.

## 2. Alcance

**In Scope:**
- Singleton de `TraceRecorder` (una instancia en `app.state`, no por request)
- `ChatResponse` extendido con métricas de Ollama (`eval_count`, `prompt_eval_count`, modelo)
- Span `kind="generation"` para la llamada LLM principal en `execute_tool_loop()` y en `router.py`
- `TraceContext` dedicado para sesiones agénticas en `run_agent_session()`
- Spans para cada fase del agent loop: `planner:create_plan`, `worker:task_N`, `planner:replan`, `planner:synthesize`
- Span parent-child linking (tools como hijos de su fase/iteración)
- Incrementar tool output capture de 200 a 1000 chars
- Cross-reference `session_id` como metadata en traces agénticos
- Tests unitarios para cada cambio

**Out of Scope:**
- Spans para audio transcription (faster-whisper) — bajo volumen, no prioritario
- Spans para vision (llava:7b) — bajo volumen
- Dashboard custom de observabilidad (Langfuse ya tiene UI)
- Alerting automático sobre degradación
- Cambios a la persistencia JSONL del agente (coexiste con traces)
- Cambios al `classify_intent` o `select_tools`

## 3. Casos de Uso Críticos

1. **Debug de sesión agéntica:** Usuario ejecuta `/agent refactorizar auth module`. La sesión
   falla en el tercer step. En Langfuse se ve: trace raíz con `session_id`, span de
   `planner:create_plan` (con el JSON del plan), 3 spans de `worker:task_N` (cada uno con
   sus tool calls como hijos), el tercero marcado como `failed`. Latencia y tokens de cada
   llamada LLM visibles.

2. **Diagnóstico de lentitud:** Un mensaje normal tarda 12s. En Langfuse se ve el trace con
   spans `phase_a` (200ms), `phase_b` (300ms), `llm:chat` (8s, 450 input tokens, 200 output
   tokens), `guardrails` (150ms). El cuello de botella es la generación LLM.

3. **Correlación tool-call → output:** Tool `search_source_code` retorna resultado largo.
   En Langfuse el span muestra input (query) y output (1000 chars en vez de 200), suficiente
   para entender qué encontró.

4. **Replan debugging:** El planner decide replanear después de que un worker falla. En Langfuse
   se ve el span `planner:replan` con input (resultados de tareas) y output (nuevo plan JSON).
   El `replans` counter visible como metadata.

## 4. Decisiones Arquitectónicas

### ¿Por qué un singleton de `TraceRecorder`?

Actualmente `TraceRecorder(repository)` se instancia en cada request (`router.py:816`),
creando un nuevo `Langfuse()` client cada vez. El SDK de Langfuse usa un background thread
para flush — crear y destruir clientes por request puede causar pérdida de datos si el GC
recoge el objeto antes del flush. Un singleton en `app.state` resuelve esto y es consistente
con el patrón de `OllamaClient` y `McpManager`.

### ¿Por qué extender `ChatResponse` y no crear un wrapper?

Ollama devuelve `eval_count`, `prompt_eval_count`, `eval_duration`, `total_duration` en la
response JSON. Actualmente `chat_with_tools()` descarta todo excepto `data["message"]`.
Extender `ChatResponse` con campos opcionales (`input_tokens`, `output_tokens`, `model`,
`total_duration_ms`) es el cambio mínimo — no requiere refactorear callers, los campos son
opcionales con default `None`.

### ¿Por qué `TraceContext` separado para agentes?

El agent loop corre como `asyncio.create_task()` en background. Cuando se lanza, el
`TraceContext` del mensaje original ya terminó (`__aexit__`). Crear un `TraceContext` nuevo
dentro de `run_agent_session()` con lifecycle ligado a la sesión completa resuelve esto.
Los tool calls del agente heredan el trace via `contextvars` automáticamente.

### ¿Por qué span parent linking?

Actualmente los spans de tools son hijos directos del trace (flat). En Langfuse esto se ve
como una lista plana, no un árbol. Pasar `parent_id` del span de la fase/iteración actual
a `_run_tool_call()` permite visualizar: `trace → phase_b → tool:search_notes`. El cambio
requiere threading un `parent_span_id: str | None` a través de `execute_tool_loop()` y
`_run_tool_call()`.

## 5. Restricciones

- `TraceRecorder` best-effort: NUNCA propagar excepciones de tracing al flujo principal
- `ChatResponse` fields nuevos son opcionales — callers existentes no se rompen
- `get_current_trace()` sigue siendo el mecanismo de propagación — sin cambios de firma en
  funciones que no necesitan trace explícito
- Los tests del agent loop deben mockear `TraceRecorder` (no hacer I/O real a Langfuse)
- Mantener retrocompatibilidad: si `tracing_enabled=False`, cero overhead
- El span de generación LLM NO debe duplicarse con el span de tool iteration —
  es un hijo de la iteración, no un sibling

## 6. Métricas de Éxito

- Langfuse muestra traces completos para mensajes normales (con span de generación LLM)
- Langfuse muestra traces completos para sesiones agénticas (con plan, workers, replan)
- Tokens de entrada/salida visibles en spans de generación
- Tool outputs legibles (1000 chars) en spans de tool
- Hierarchy visible en Langfuse: trace → phase → tool / trace → worker → tool
