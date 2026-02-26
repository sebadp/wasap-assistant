# Planner-Orchestrator para el Agent Loop

## Resumen

Implementa un patrón Planner-Orchestrator que separa planificación de ejecución en las sesiones agénticas. En lugar de un single-loop reactivo donde el mismo LLM hace todo, ahora hay 3 fases distintas:

1. **UNDERSTAND** — El planner lee el contexto y crea un plan estructurado (JSON)
2. **EXECUTE** — Workers especializados ejecutan cada tarea con tools filtrados
3. **SYNTHESIZE** — El planner revisa resultados y decide si replanear o responder

## Archivos clave

| Archivo | Función |
|---------|---------|
| `app/agent/planner.py` | Planner agent: `create_plan()`, `replan()`, `synthesize()` |
| `app/agent/workers.py` | Worker execution: `execute_worker()`, `build_worker_prompt()` |
| `app/agent/models.py` | `TaskStep`, `AgentPlan` dataclasses |
| `app/agent/loop.py` | `_run_planner_session()` (3 fases) + `_run_reactive_session()` (fallback) |
| `app/skills/router.py` | `WORKER_TOOL_SETS` (worker_type → categories) |
| `app/skills/tools/debug_tools.py` | 5 debug tools para introspección |
| `app/commands/builtins.py` | `/dev-review` command |

## Modelo de datos

### TaskStep
```python
@dataclass
class TaskStep:
    id: int
    description: str
    worker_type: str  # reader | analyzer | coder | reporter | general
    tools: list[str]
    status: str  # pending | in_progress | done | failed
    result: str | None
    depends_on: list[int]
```

### AgentPlan
```python
@dataclass
class AgentPlan:
    objective: str
    context_summary: str
    tasks: list[TaskStep]
    replans: int  # max 3
```

## Worker types

| Type | Enfoque | Categorías de tools |
|------|---------|-------------------|
| `reader` | Lee y resume información | conversation, selfcode, evaluation, notes, debugging |
| `analyzer` | Analiza datos y encuentra patrones | evaluation, selfcode, debugging |
| `coder` | Lee y modifica código fuente | selfcode, shell |
| `reporter` | Sintetiza hallazgos en reportes | evaluation, notes, debugging |
| `general` | Fallback con todos los tools | selfcode, shell, notes, evaluation, conversation, debugging |

## Debug tools

5 tools para introspección de conversaciones y trazas:

- `review_interactions(phone)` — overview de trazas con anomalías
- `get_tool_output_full(trace_id)` — input/output completo de tool calls
- `get_interaction_context(trace_id)` — deep-dive en una traza
- `write_debug_report(title, content)` — guarda reporte markdown
- `get_conversation_transcript(phone)` — lee mensajes reales

## Decisiones de diseño

1. **Planner como default**: Todas las sesiones agénticas usan el planner. Si falla el JSON parse → fallback a plan lineal (1 task general).
2. **Workers secuenciales**: Los workers se ejecutan uno a uno respetando `depends_on`. No hay paralelismo entre workers (simplifica el estado).
3. **Max replans = 3**: Hard cap para evitar loops infinitos (patrón Magentic-One).
4. **JSON tolerante**: El parser de planes intenta extraer JSON de markdown fences, busca `{...}` en el texto, y usa fallback si todo falla.
5. **Reactive session preservada**: El loop reactivo original queda como `_run_reactive_session()` y se usa como fallback o con `use_planner=False`.

## Gotchas

- `think: False` en todas las llamadas del planner (structured output, sin thinking blocks)
- Los workers usan `execute_tool_loop` internamente, que incluye `request_more_tools` meta-tool
- `session.plan` y `session.task_plan` coexisten: el plan estructurado se renderiza como markdown en `task_plan` para backwards compat
- Debug tools requieren `tracing_enabled=True` (gated en `__init__.py`)

## Testing

Ver: [`docs/testing/28-planner_orchestrator_testing.md`](../testing/28-planner_orchestrator_testing.md)
