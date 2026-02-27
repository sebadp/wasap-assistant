# Planes de Ejecución

Documentos técnicos que bajan una intención de producto a cambios concretos en el codebase.

## Planes disponibles

| Plan | Archivo | Estado |
|---|---|---|
| Arquitectura de Evaluación y Mejora Continua | [`11-eval_implementation_plan.md`](11-eval_implementation_plan.md) | 📋 Pendiente |
| Sesiones Agénticas (Agent Mode) | [`18-agentic_sessions_plan.md`](18-agentic_sessions_plan.md) | ✅ Completado |
| Context Engineering | [`08-context_engineering_plan.md`](08-context_engineering_plan.md) | ✅ Completado |
| Claude Code Experience | [`EX-claude_code_experience.md`](EX-claude_code_experience.md) | 📋 Evaluación |
| OpenClaw Experience | [`EX-openclaw_experience.md`](EX-openclaw_experience.md) | 📋 Evaluación |
| **Autonomous Agent Experience** | [`19-autonomous_agent_plan.md`](19-autonomous_agent_plan.md) | **✅ Sprint 1 done** |
| Autonomous Agent Sprint 2 | [`20-autonomous_agent_sprint2_plan.md`](20-autonomous_agent_sprint2_plan.md) | **✅ Completado** |
| Autonomous Agent Sprint 3 | [`21-autonomous_agent_sprint3_plan.md`](21-autonomous_agent_sprint3_plan.md) | **✅ Completado** |
| Dynamic Tool Budget & `request_more_tools` | [`27-dynamic_tool_budget_prd.md`](27-dynamic_tool_budget_prd.md) / [`27-dynamic_tool_budget_prp.md`](27-dynamic_tool_budget_prp.md) | ✅ Completado |
| Planner-Orchestrator | [`28-planner_orchestrator_prd.md`](28-planner_orchestrator_prd.md) / [`28-planner_orchestrator_prp.md`](28-planner_orchestrator_prp.md) | 🚧 En progreso |
| Observabilidad de Agentes | [`29-observability_prd.md`](29-observability_prd.md) / [`29-observability_prp.md`](29-observability_prp.md) | ✅ Completado |

## Convenciones

- Crear el exec plan **antes** de implementar una feature compleja (>3 archivos afectados)
- El plan es un artefacto de primera clase: documenta decisiones, no solo pasos
- Incluir siempre: objetivo, archivos a modificar, schema de datos, orden de implementación
- Marcar el estado al terminar: 📋 Pendiente → 🚧 En progreso → ✅ Completado

## Template de PRD (Product Requirements Document)

Usar este como `docs/exec-plans/<numero>-<nombre>_prd.md` para asentar propósitos e intención.

```markdown
# PRD: [Nombre de la Feature]

## Objetivo y Contexto
[Qué problema resuelve esta implementación y por qué es importante]

## Alcance (In Scope & Out of Scope)
- **In Scope:** [Lista...]
- **Out of Scope:** [Lista...]

## Casos de Uso Críticos
1. [Escenario 1]
2. [Escenario 2]

## Restricciones Arquitectónicas / Requerimientos Técnicos
- [Dependencias o frameworks que no deben evadirse]
- [Criterios de seguridad]
```

## Template de PRP (Product Requirements Plan)

Usar este como `docs/exec-plans/<numero>-<nombre>_prp.md` para asentar ejecución técnica y checkboxes. **OBLIGATORIO: MARCAR LOS CHECKS DURANTE LA EJECUCIÓN.**

```markdown
# PRP: [Nombre de la Feature]

## Archivos a Modificar
- `ruta/al/archivo1.py`: [Qué se cambia]
- `ruta/al/archivo2.md`: [Nuevo archivo]

## Fases de Implementación (con Checkboxes)

### Phase 1: Fundamentos
- [ ] Implementar X
- [ ] Escribir tests para X

### Phase 2: Integración
- [ ] Agregar Y al webhook router
- [ ] Escribir validaciones de borde de Y

### Phase 3: Documentación
- [ ] Correr `make check`
- [ ] Escribir `docs/features/...`
- [ ] Escribir `docs/testing/...`
```
