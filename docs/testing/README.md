# Guías de Testing Manual

Cada archivo en este directorio cubre el testing manual de una feature específica.

## Guías disponibles

| Feature | Archivo |
|---|---|
| Testing completo del sistema | [`manual_testing_guide.md`](../../manual_testing_guide.md) *(en la raíz del proyecto)* |
| Chat Funcional (Fase 1) | [`chat_funcional_testing.md`](chat_funcional_testing.md) |
| Conversation Skill (Fase 1) | [`conversation_skill_testing.md`](conversation_skill_testing.md) |
| Persistencia y Memoria (Fase 2) | [`persistencia_memoria_testing.md`](persistencia_memoria_testing.md) |
| UX y Multimedia (Fase 3) | [`ux_multimedia_testing.md`](ux_multimedia_testing.md) |
| Skills y Herramientas (Fase 4) | [`skills_herramientas_testing.md`](skills_herramientas_testing.md) |
| Memoria Avanzada (Fase 5) | [`memoria_avanzada_testing.md`](memoria_avanzada_testing.md) |
| Context Engineering (Fase 5) | [`context_engineering_testing.md`](context_engineering_testing.md) |
| Búsqueda Semántica (Fase 6) | [`busqueda_semantica_testing.md`](busqueda_semantica_testing.md) |
| CI/CD (Fase 7) | [`cicd_testing.md`](cicd_testing.md) |
| Guardrails y Trazabilidad (Fase 8) | [`eval_guardrails_tracing_testing.md`](eval_guardrails_tracing_testing.md) |
| Dataset Vivo (Fase 8) | [`eval_dataset_testing.md`](eval_dataset_testing.md) |
| User Signals (Fase 8) | [`eval_user_signals_testing.md`](eval_user_signals_testing.md) |
| Auto-evolución (Fase 8) | [`eval_auto_evolution_testing.md`](eval_auto_evolution_testing.md) |
| Eval Skill (Fase 8) | [`eval_skill_testing.md`](eval_skill_testing.md) |
| Maduración del Pipeline (Fase 8) | [`eval_maduración_testing.md`](eval_maduración_testing.md) |
| Sesiones Agénticas | [`agentic_sessions.md`](agentic_sessions.md) |

## Convenciones

- Un archivo por feature o área funcional
- Usar `TEMPLATE.md` como punto de partida
- Nombre del archivo: `<nombre>_testing.md`
- Cada guía debe incluir: casos felices, edge cases, verificación en logs, queries de DB si aplica

## Nota sobre el testing general

La guía completa de testing del sistema está en `manual_testing_guide.md` (raíz del proyecto).
Las guías en este directorio son específicas por feature, creadas al implementar cada una.
