# Testing: Planner-Orchestrator

## Tests unitarios

### `tests/test_planner.py`
- `test_parse_plan_json_valid` — JSON válido genera AgentPlan con tasks correctos
- `test_parse_plan_json_markdown_fences` — JSON dentro de ``` se parsea correctamente
- `test_parse_plan_json_fallback` — texto inválido genera plan fallback con 1 task general
- `test_fallback_plan` — plan fallback tiene 1 task con worker_type="general"
- `test_agent_plan_next_task` — respeta depends_on
- `test_agent_plan_all_done` — detecta cuando todos los tasks están done/failed
- `test_agent_plan_to_markdown` — renderiza markdown con checkmarks correctos

### `tests/test_workers.py`
- `test_build_worker_prompt` — prompts distintos por worker_type
- `test_select_worker_tools` — filtra tools según WORKER_TOOL_SETS

### `tests/test_debug_tools.py`
- `test_review_interactions` — formatea trazas con scores y flags
- `test_get_tool_output_full` — muestra tool calls con input/output
- `test_get_conversation_transcript` — reconstruye transcript legible
- `test_write_debug_report` — guarda archivo markdown

### `tests/test_repository.py` (nuevos métodos)
- `test_get_traces_by_phone` — trazas con scores agregados
- `test_get_trace_tool_calls` — spans kind=tool con output
- `test_get_conversation_transcript` — mensajes en orden cronológico

## Testing manual

### 1. Planner crea plan estructurado
```
/agent "Lee el código de notes_tools.py y haz un resumen"
```
Verificar en logs: `Planner created plan: N tasks`
Verificar en WA: recibe mensaje con plan en formato checklist

### 2. Workers ejecutan secuencialmente
Verificar en logs:
- `Worker [reader] task #1 completed: ...`
- `Worker [coder] task #2 completed: ...`

### 3. Fallback a reactive loop
Si el planner falla (timeout, JSON inválido), debe caer al reactive loop.
Verificar en logs: `Planner session failed, falling back to reactive loop`

### 4. Dev-review end-to-end
```
/dev-review +5491234567890
```
Verificar:
1. Lee la conversación primero
2. Crea plan de análisis (4-6 pasos)
3. Ejecuta diagnóstico
4. Genera reporte en `data/debug_reports/`

### 5. Replanning
Provocar un escenario donde un task falle:
- El planner debería detectar el fallo
- Crear un nuevo plan (max 3 replans)
- Logs: `Replanned (attempt N): M tasks`

## Edge cases

- Plan vacío (0 tasks) → fallback a plan lineal
- Tasks circulares en depends_on → next_task() retorna None → session termina
- Worker timeout → task marcado como "failed"
- Planner JSON con campos faltantes → valores default
