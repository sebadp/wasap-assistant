# Guías de Testing Manual

Cada archivo en este directorio cubre el testing manual de una feature específica.

## Guías disponibles

| Feature | Archivo |
|---|---|
| Testing completo del sistema | [`manual_testing_guide.md`](../../manual_testing_guide.md) *(en la raíz del proyecto)* |
| Chat Funcional (Fase 1) | [`01-chat_funcional_testing.md`](01-chat_funcional_testing.md) |
| Conversation Skill (Fase 1) | [`02-conversation_skill_testing.md`](02-conversation_skill_testing.md) |
| Persistencia y Memoria (Fase 2) | [`03-persistencia_memoria_testing.md`](03-persistencia_memoria_testing.md) |
| UX y Multimedia (Fase 3) | [`05-ux_multimedia_testing.md`](05-ux_multimedia_testing.md) |
| Skills y Herramientas (Fase 4) | [`06-skills_herramientas_testing.md`](06-skills_herramientas_testing.md) |
| Memoria Avanzada (Fase 5) | [`07-memoria_avanzada_testing.md`](07-memoria_avanzada_testing.md) |
| Context Engineering (Fase 5) | [`08-context_engineering_testing.md`](08-context_engineering_testing.md) |
| Búsqueda Semántica (Fase 6) | [`09-busqueda_semantica_testing.md`](09-busqueda_semantica_testing.md) |
| CI/CD (Fase 7) | [`10-cicd_testing.md`](10-cicd_testing.md) |
| Guardrails y Trazabilidad (Fase 8) | [`12-eval_guardrails_tracing_testing.md`](12-eval_guardrails_tracing_testing.md) |
| Dataset Vivo (Fase 8) | [`13-eval_dataset_testing.md`](13-eval_dataset_testing.md) |
| User Signals (Fase 8) | [`14-eval_user_signals_testing.md`](14-eval_user_signals_testing.md) |
| Auto-evolución (Fase 8) | [`15-eval_auto_evolution_testing.md`](15-eval_auto_evolution_testing.md) |
| Eval Skill (Fase 8) | [`16-eval_skill_testing.md`](16-eval_skill_testing.md) |
| Maduración del Pipeline (Fase 8) | [`17-eval_maduracion_testing.md`](17-eval_maduracion_testing.md) |
| Sesiones Agénticas | [`18-agentic_sessions.md`](18-agentic_sessions.md) |
| Autonomous Agent (Shell, Loop Detection) | [`19-autonomous_agent_testing.md`](19-autonomous_agent_testing.md) |

## Convenciones

- Un archivo por feature o área funcional
- Usar `TEMPLATE.md` como punto de partida
- Nombre del archivo: `<nombre>_testing.md`
- Cada guía debe incluir: casos felices, edge cases, verificación en logs, queries de DB si aplica

## Nota sobre el testing general

La guía completa de testing del sistema está en `manual_testing_guide.md` (raíz del proyecto).
Las guías en este directorio son específicas por feature, creadas al implementar cada una.
