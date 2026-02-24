---
name: "docs"
description: "Herramientas para la gestión autónoma del ciclo de documentación, índices y convenciones arquitectónicas."
---

# Funcionalidad
Este skill te provee de herramientas para actualizar automáticamente la documentación del proyecto una vez que terminas de programar una "feature" nueva, sin necesidad de manipular los archivos manualmente paso por paso.

El "Protocolo de Documentación de 5 Pasos" es estricto en este proyecto:
1. Walkthrough visual de la feature.
2. Guía manual de testing para la feature.
3. Actualización de los índices (READMEs).
4. Actualización de convenciones (`CLAUDE.md`).
5. Actualización de capacidades de agentes (`AGENTS.md`).

# Cuándo usarlo
- **Inmediatamente después de terminar una Feature o Tarea de un PRP:** Usa la herramienta `create_feature_docs` pasando el nombre descriptivo de la feature. La herramienta se encargará de crear los archivos usando los *Templates* y agregarlos a los índices `docs/features/README.md` y `docs/testing/README.md`.
- **Cuando implementas un patrón arquitectónico nuevo o rompes uno viejo:** Usa `update_architecture_rules` para blindar tu decisión. La herramienta anexará la regla al pie de `CLAUDE.md` bajo la sección requerida para que los futuros agentes la lean.
- **Cuando agregas un Skill, servidor MCP o Endpoint nuevo:** Usa `update_agent_docs` para actualizar `AGENTS.md` (si aplica) con el nuevo conocimiento.

# Instrucciones
1. Nunca uses bash o manipulación directa por `write_file` para actualizar índices (e.g. `docs/features/README.md`) o para crear los archivos de documentación basados en los `TEMPLATE.md`. SIEMPRE utiliza `create_feature_docs` porque este es consciente de la estructura Markdown esperada.
2. Al documentar arquitecturas, el argumento para `update_architecture_rules` debe ser conciso y directo, de no más de 3 oraciones, explicando el patrón que introdujiste y los archivos involucrados.

# Herramientas
- `create_feature_docs`: Genera o actualiza la retrospectiva (`docs/features/XXXX-nombre.md`) y la guía de testing (`docs/testing/XXXX-nombre_testing.md`), usando los templates preestablecidos y conectándolos automáticamente a su respectivo `README.md`.
- `update_architecture_rules`: Agrega un nuevo bullet de reglas arquitectónicas restrictivas a `CLAUDE.md`.
- `update_agent_docs`: Expande la lista de skills o capacidades de los agentes en el índice base de `AGENTS.md`.
