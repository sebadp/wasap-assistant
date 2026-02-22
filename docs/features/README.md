# Walkthroughs de Features

Cada archivo en este directorio documenta una feature implementada: qué hace, cómo funciona internamente, cómo extenderla.

## Convenciones

- Un archivo por feature o fase significativa
- Usar `TEMPLATE.md` como punto de partida
- Nombre del archivo: `<nombre-en-kebab-case>.md`
- Linkear siempre a la guía de testing correspondiente en `docs/testing/`

## Features documentadas

| Feature | Archivo | Fase |
|---|---|---|
| Chat Funcional | [`chat_funcional.md`](chat_funcional.md) | Fase 1 |
| Conversation Skill & Auto Debug | [`conversation_skill.md`](conversation_skill.md) | Fase 1 |
| Persistencia y Memoria | [`persistencia_memoria.md`](persistencia_memoria.md) | Fase 2 |
| Context Compaction (LLM-based) | [`context_compaction.md`](context_compaction.md) | Fase 2 |
| UX y Multimedia | [`ux_multimedia.md`](ux_multimedia.md) | Fase 3 |
| Skills y Herramientas | [`skills_herramientas.md`](skills_herramientas.md) | Fase 4 |
| Memoria Avanzada | [`memoria_avanzada.md`](memoria_avanzada.md) | Fase 5 |
| Context Engineering | [`context_engineering.md`](context_engineering.md) | Fase 5 |
| Búsqueda Semántica | [`busqueda_semantica.md`](busqueda_semantica.md) | Fase 6 |
| CI/CD | [`cicd.md`](cicd.md) | Fase 7 |
| Guardrails y Trazabilidad | [`eval_guardrails_tracing.md`](eval_guardrails_tracing.md) | Fase 8 |
| Dataset Vivo | [`eval_dataset.md`](eval_dataset.md) | Fase 8 |
| User Signals | [`eval_user_signals.md`](eval_user_signals.md) | Fase 8 |
| Auto-evolución | [`eval_auto_evolution.md`](eval_auto_evolution.md) | Fase 8 |
| Eval Skill | [`eval_skill.md`](eval_skill.md) | Fase 8 |
| Maduración del Pipeline | [`eval_maduración.md`](eval_maduración.md) | Fase 8 |
| Sesiones Agénticas | [`agentic_sessions.md`](agentic_sessions.md) | Agent Mode |

## Cómo crear un nuevo walkthrough

1. Copiar `TEMPLATE.md` con el nombre de la feature
2. Completar todas las secciones (especialmente "Decisiones de diseño" y "Gotchas")
3. Agregar la fila correspondiente a la tabla de arriba
4. Crear la guía de testing en `docs/testing/<nombre>_testing.md`
