# Execution Plan: Autonomous Agent — Sprint 2 (UX Premium)

> **Status:** ✅ Completado
> **Módulo:** Agentic Sessions
> **Objetivo:** Mejorar la experiencia de usuario (UX) del agente autónomo implementado en el Sprint 1, añadiendo visualización de diffs, creación de PRs, persistencia entre reinicios y personalización del comportamiento.


---

## Estado de Implementación

- [x] F4: preview_patch en selfcode_tools.py — unified diff en memoria sin modificar el archivo
- [x] F4: _AGENT_SYSTEM_PROMPT actualizado en loop.py para solicitar preview antes de apply_patch
- [x] F5: GITHUB_TOKEN y github_repo_owner/repo_name en app/config.py
- [x] F5: git_create_pr en git_tools.py usando GitHub REST API (POST /repos/{owner}/{repo}/pulls)
- [x] F6: app/agent/persistence.py — append-only JSONL en data/agent_sessions/{session_id}.jsonl
- [x] F6: run_agent_session() guarda eventos (start, round, tool_call, end) en persistence.py
- [x] F7: Bootstrap files (SOUL.md, USER.md, TOOLS.md) en directorio configurable (agent_bootstrap_dir)
- [x] F7: Cargados en run_agent_session() al inicio del system prompt del agente

---

## Descripción General

El Sprint 1 estableció la fundación del agente autónomo (ejecución de comandos, protección contra loops, prompts especializados). El **Sprint 2** (UX Premium) se enfoca en hacer que esta herramienta sea más confiable, transparente y adaptable para el usuario de WhatsApp.

Se implementarán 4 features clave (F4-F7 del plan original):
1. **F4: Diff Preview** — Permitir al usuario ver qué código va a cambiar antes de aplicarlo.
2. **F5: PR Creation** — Automatizar la creación de Pull Requests en GitHub.
3. **F6: Session Persistence** — Guardar el estado del agente en disco para sobrevivir a reinicios del bot.
4. **F7: Bootstrap Files** — Permitir personalizar la "personalidad" y contexto base del agente sin tocar el código.

---

## Modificaciones Propuestas

### F4: Diff Preview (Visualización previa de cambios)

Reemplaza la aplicación a ciegas del código por un paso de validación visual.

#### [MODIFY] [selfcode_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/selfcode_tools.py)
Añadir herramienta `preview_patch`:
- **Firma:** `preview_patch(path: str, search: str, replace: str)`
- **Lógica:** Intenta aplicar el parche en memoria. Si tiene éxito, genera un *unified diff* usando la librería estándar `difflib`.
- **Retorno:** El diff formateado como texto, para que el LLM lo lea y se lo envíe al usuario usando `request_user_approval`.
- **Importante:** Esta tool **NO** modifica el archivo real. Solo sirve para visualización.

**Impacto en Loop:**
Se debe modificar el `_AGENT_SYSTEM_PROMPT` en [loop.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/agent/loop.py) para indicar al agente que **siempre** debe usar `preview_patch` y obtener aprobación antes de usar `apply_patch` en archivos críticos o cuando hay dudas.

### F5: PR Creation (Integración con GitHub)

Permite al agente completar el ciclo de vida del desarrollo.

#### [MODIFY] [config.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/config.py)
Añadir soporte para credenciales de GitHub:
- `github_token: str | None = None`
- `github_repo: str | None = None` (ej: `"sebastiandavila/wasap"`)

#### [MODIFY] [git_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/git_tools.py)
Añadir herramienta `git_create_pr`:
- **Firma:** `git_create_pr(title: str, body: str, head_branch: str, base_branch: str = "main")`
- **Lógica:** Hace un request HTTP a la GitHub API (`POST /repos/{owner}/{repo}/pulls`).
- **Seguridad:** Requiere que `GITHUB_TOKEN` y `GITHUB_REPO` estén configurados.
- **Retorno:** URL del PR creado o mensaje de error claro (conflictos, tokens inválidos). Se usará `httpx` (ya presente en el proyecto).

### F6: Session Persistence (JSONL)

Resolución de uno de los mayores problemas actuales: si el bot se reinicia, las tareas en background del agente se pierden silenciosamente.

#### [NEW] [persistence.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/agent/persistence.py)
Crear módulo dedicado a persistencia usando formato JSONL (fácil de appendear, robusto ante caídas):
- **Estructura Directorio:** `data/agent_sessions/<phone_number>_<session_id>.jsonl`
- **Lógica de Guardado:** `append_to_session(session_id, phone_number, data_dict)` -> Escribe una línea JSON.
- **Lógica de Carga:** `load_session_history(session_id, phone_number)` -> Reconstruye la sesión iterando línea por línea.
- *Nota: la persistencia en DB relacional es overkill para este caso de uso donde solo nos importa el log estructurado de qué hizo.*

#### [MODIFY] [loop.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/agent/loop.py)
- En `run_agent_session`, al final de cada round, llamar a `append_to_session(...)` para guardar el estado actual (messages, task_plan).
- Añadir comando `/agent-resume` (podría ir en router o un handler específico) para cargar la última sesión si el estado en memoria está vacío pero hay archivos JSONL recientes.

### F7: Bootstrap Files (Personalización Base)

Inspirado en Claude Code, permite "customizar" el comportamiento del agente mediante archivos flat.

#### [MODIFY] [loop.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/agent/loop.py)
- Al inicializar el `_AGENT_SYSTEM_PROMPT`, el agente debe revisar el directorio del workspace (o la raíz del proyecto) buscando archivos de bootstrap opcionales.
- Archivos objetivo:
  - `SOUL.md`: Injecta personalidad o estilo (ej: "Respuestas concisas", "Usa emojis").
  - `TOOLS.md`: Comandos o notas específicas del proyecto (ej: "Usa npm run build para empaquetar").
  - `USER.md`: Preferencias del usuario logueado.
- Si los archivos existen, se abren (`read()` simple) y se inyectan en el prompt del sistema antes del `objective`. Si no, se ignoran sin error.

---

## Plan de Verificación

### Validación de la integración (End-to-End)
Al terminar el sprint, se probará un flujo completo simulado por WA:
1. **F7:** Se creará un `SOUL.md` experimental (verificando vía tracing/logs que se inyecta en el prompt).
2. **F4:** El agente propondrá un cambio a un archivo via `preview_patch`, requiriendo aprobación.
3. **F6:** (Simulación de fallo) Se enviará un kill al proceso. Al reiniciar, un comando de resume debe retomar el `task_plan`.
4. **F5:** El agente creará una nueva rama, commiteará y subirá el branch, llamando finalmente a `git_create_pr`. Validar que el PR de prueba efectivamente aparezca en GitHub.

### Pruebas Individuales (Happy path / Edge cases)
- `preview_patch`: Confirmar fallos esperados si `search` string no coincide linealmente.
- `git_create_pr`: Probar falla intencional con un branch inexistente o sin token configurado.
- `persistence.py`: Simular archivos JSONL corrompidos (última línea cortada) para validar graceful degradation al cargar sesión.

---

## Dependencias de otras Tareas

- Requiere el completamiento del Sprint 1 (ya realizado).
- Requiere acceso temporal a un repositorio GitHub para pruebas de API de Pull Requests.
