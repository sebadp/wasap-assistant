# Planes de Ejecución

Documentos técnicos que bajan una intención de producto a cambios concretos en el codebase.

## Planes disponibles

| Plan | Archivo | Estado |
|---|---|---|
| Arquitectura de Evaluación y Mejora Continua | [`eval_implementation_plan.md`](eval_implementation_plan.md) | 📋 Pendiente |
| Sesiones Agénticas (Agent Mode) | [`agentic_sessions_plan.md`](agentic_sessions_plan.md) | ✅ Completado |

## Convenciones

- Crear el exec plan **antes** de implementar una feature compleja (>3 archivos afectados)
- El plan es un artefacto de primera clase: documenta decisiones, no solo pasos
- Incluir siempre: objetivo, archivos a modificar, schema de datos, orden de implementación
- Marcar el estado al terminar: 📋 Pendiente → 🚧 En progreso → ✅ Completado

## Template mínimo de exec plan

```markdown
# Plan: [Nombre]

## Objetivo
[Qué problema resuelve esta implementación]

## Archivos a modificar
| Archivo | Cambio |
|---|---|

## Schema de datos (si aplica)
[Tablas SQL nuevas, modelos Pydantic, etc.]

## Orden de implementación
1. [Paso 1 — sin dependencias]
2. [Paso 2 — depende de 1]
...

## Decisiones de diseño
[Por qué este enfoque y no otro]
```
