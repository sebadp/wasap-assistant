# PRP: Planner-Orchestrator para el Agent Loop

## Archivos a Modificar

### Sprint 1: Foundation
- `app/agent/models.py`: Agregar `TaskStep` y `AgentPlan` dataclasses
- `app/agent/planner.py`: NUEVO — PlannerAgent con create_plan, replan, synthesize
- `app/agent/workers.py`: NUEVO — build_worker_prompt, select_worker_tools, execute_worker
- `app/agent/loop.py`: Refactor run_agent_session para 3 fases
- `app/skills/router.py`: Agregar WORKER_TOOL_SETS dict
- `app/agent/persistence.py`: Extender JSONL para plan snapshots

### Sprint 2: Debug Tools
- `app/database/repository.py`: 3 nuevos métodos (get_traces_by_phone, get_trace_tool_calls, get_conversation_transcript)
- `app/skills/tools/debug_tools.py`: NUEVO — 4 tools (review_interactions, get_tool_output_full, get_interaction_context, write_debug_report)
- `app/skills/router.py`: Agregar categoría "debugging"
- `app/skills/tools/__init__.py`: Registrar debug_tools

### Sprint 3: Command + Docs
- `app/commands/builtins.py`: Agregar cmd_dev_review
- `skills/debug/SKILL.md`: NUEVO — instrucciones para debug workers
- `docs/features/planner_orchestrator.md`: Feature doc
- `docs/testing/planner_orchestrator_testing.md`: Testing doc
- `CLAUDE.md`: Patrones nuevos
- `AGENTS.md`: Nuevos módulos

## Fases de Implementación (con Checkboxes)

### Sprint 1: Foundation

- [x] Agregar `TaskStep` y `AgentPlan` a `app/agent/models.py`
- [x] Crear `app/agent/planner.py` con PlannerAgent
- [x] Crear `app/agent/workers.py` con worker execution
- [x] Agregar `WORKER_TOOL_SETS` a `app/skills/router.py`
- [x] Refactorear `app/agent/loop.py` para 3 fases
- [x] Extender persistencia con plan snapshots
- [x] Verificar `make check`

### Sprint 2: Debug Tools

- [x] Agregar `get_traces_by_phone()` a repository
- [x] Agregar `get_trace_tool_calls()` a repository
- [x] Agregar `get_conversation_transcript()` a repository
- [x] Crear `app/skills/tools/debug_tools.py` con 5 tools
- [x] Agregar categoría "debugging" a router.py
- [x] Registrar debug_tools en `__init__.py`
- [x] Verificar `make check`

### Sprint 3: Command + Documentation

- [x] Agregar `cmd_dev_review` a builtins.py
- [x] Crear `skills/debug/SKILL.md`
- [x] Escribir `docs/features/planner_orchestrator.md`
- [x] Escribir `docs/testing/planner_orchestrator_testing.md`
- [x] Actualizar `docs/features/README.md`
- [x] Actualizar `docs/testing/README.md`
- [x] Actualizar `docs/exec-plans/README.md`
- [x] Actualizar `CLAUDE.md`
- [x] Actualizar `AGENTS.md`
- [x] Verificar `make check` final
