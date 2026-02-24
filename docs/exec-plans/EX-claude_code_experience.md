# Evaluación: Experiencia Claude Code desde WhatsApp

> **Fecha**: 2026-02-22
> **Estado**: 📋 Evaluación — pendiente de decisión

---

## Objetivo

Convertir el agente WasAP en un asistente de programación autónomo que el usuario pueda manejar desde WhatsApp, con una experiencia similar a Claude Code / cursor / aider. El usuario describe qué quiere hacer ("agregá dark mode al portfolio", "arreglá el bug de login") y el agente navega el código, edita archivos, corre tests, y commitea — pidiendo aprobación en los momentos clave.

---

## Auditoría: ¿qué ya tenemos?

### ✅ Ya implementado

| Capacidad | Implementación |  Estado |
|---|---|---|
| Leer archivos | `selfcode_tools.read_source_file` | ✅ |
| Escribir archivos | `selfcode_tools.write_source_file` (gated: `AGENT_WRITE_ENABLED`) | ✅ |
| Editar archivos (patch) | `selfcode_tools.apply_patch` (search & replace) | ✅ |
| Listar archivos | `selfcode_tools.list_source_files` (tree recursivo) | ✅ |
| Buscar en código | `selfcode_tools.search_source_code` (grep) | ✅ |
| Ver logs | `selfcode_tools.get_recent_logs` | ✅ |
| Git status/diff | `git_tools.git_status`, `git_tools.git_diff` | ✅ |
| Git branch/commit/push | `git_tools.git_create_branch/commit/push` | ✅ |
| Task planning | `create_task_plan`, `update_task_status` (agent/task_memory) | ✅ |
| Multi-round execution | Agent loop: 15 rounds × 8 tools (agent/loop.py) | ✅ |
| Human-in-the-loop | `request_user_approval` con pausa/resume | ✅ |
| Context clearing | `_clear_old_tool_results` entre rounds | ✅ |
| MCP expansion | Hot-install de MCP servers (expand_tools) | ✅ |
| Path safety | `_is_safe_path` bloquea .env, tokens, binarios | ✅ |

### ❌ Lo que falta (gap analysis)

| Capacidad | Impacto | Complejidad |
|---|---|---|
| **Ejecución de comandos shell** | 🔴 Crítico | Media |
| **Loop de test-fix automático** | 🔴 Crítico | Media |
| **Preview de diff antes de aplicar** | 🟡 Alto | Baja |
| **Selección de proyecto/workspace** | 🟡 Alto | Media |
| **Creación de PRs** | 🟡 Alto | Baja |
| **Context loading inteligente (tree → outline → file)** | 🟡 Alto | Alta |
| **System prompt especializado para coding** | 🟢 Medio | Baja |
| **Progress updates vía WhatsApp** | 🟢 Medio | Baja |
| **Undo / rollback** | 🟢 Medio | Media |

---

## Features propuestas (ordenadas por impacto)

### Feature 1: Shell Command Execution 🔴

**Qué**: tool `run_command(command, timeout)` que ejecuta un comando arbitrario en el container y retorna stdout+stderr.

**Por qué**: sin esto, el agente no puede correr tests, instalar deps, correr linters, ni validar sus cambios. Es la diferencia entre "sugeridor de código" y "programador autónomo".

**Cómo**:
```python
async def run_command(command: str, timeout: int = 30) -> str:
    """Execute a shell command in the project directory."""
    # Sanitization: block dangerous commands (rm -rf /, etc)
    # Run via asyncio.create_subprocess_shell
    # Capture stdout + stderr, truncar si > 4000 chars
    # Return formatted output with exit code
```

**Seguridad**:
- Whitelist de comandos seguros (`pytest`, `ruff`, `mypy`, `make`, `npm`, `pip`, etc.)
- O bien: blacklist de comandos peligrosos + HITL para commands no reconocidos
- Timeout configurable (default 30s, max 120s)
- Gated por `AGENT_WRITE_ENABLED` (misma flag que write_source_file)

**Archivos afectados**: `app/skills/tools/selfcode_tools.py` (1 tool nuevo)

---

### Feature 2: Test-Fix Loop 🔴

**Qué**: después de editar código, el agente automáticamente corre tests, observa los errores, y entra en un ciclo de fix→test→fix hasta que pasan (o max N intentos).

**Por qué**: esto es lo que hace a Claude Code realmente útil. Sin feedback de tests, el agente programa "a ciegas".

**Cómo**: no es un tool nuevo — es un **patrón en el system prompt** del agent mode. El agente ya tiene `run_command` (Feature 1) y `apply_patch`. Solo necesita instrucciones para:
1. Después de editar → correr tests
2. Si fallan → leer errores → editar → volver a correr
3. Repetir hasta pasen o se gasten 3 intentos

**System prompt addition**:
```
CODING RULES:
- After EVERY code edit, run the relevant tests to verify.
- If tests fail, read the error, fix the code, and re-run.
- Never commit code that hasn't passed tests.
- Use `apply_patch` for small edits, `write_source_file` only for new files.
```

**Archivos afectados**: `app/agent/loop.py` (system prompt), posiblemente un "coding mode" flag

---

### Feature 3: Diff Preview 🟡

**Qué**: antes de aplicar un patch, mostrar el diff al usuario vía WhatsApp y esperar confirmación. Similar a cómo Claude Code muestra los cambios antes de aplicarlos.

**Cómo**: envolver `apply_patch` con un paso de preview. El agente genera el diff, lo envía como mensaje formateado, y espera aprobación via `request_user_approval`.

**Formato WhatsApp del diff**:
```
📝 *Cambio propuesto en* `app/main.py`:
```
- old_code()
+ new_code()
```
¿Aplico este cambio? (sí/no)
```

**Archivos afectados**: `app/skills/tools/selfcode_tools.py` (wrapper de `apply_patch`)

---

### Feature 4: Multi-Project Workspace 🟡

**Qué**: el agente puede trabajar en distintos repositorios, no solo en el propio (`wasap-assistant`). El usuario dice "trabajá en mi portfolio" y el agente cambia el `_PROJECT_ROOT`.

**Cómo**:
- Directorio base configurable: `PROJECTS_DIR=/home/appuser/projects`
- Tool `switch_project(name)` que cambia el root
- `list_projects()` que muestra repos disponibles
- Los repos se clonan previamente o se montan como volúmenes Docker

**Seguridad**: el path safety (`_is_safe_path`) se adapta al nuevo root. Cada proyecto tiene su propio scope de lectura/escritura.

**Archivos afectados**: `selfcode_tools.py`, `git_tools.py`, `config.py`, `docker-compose.yml`

---

### Feature 5: PR Creation 🟡

**Qué**: tool `create_pr(title, body)` que crea un Pull Request en GitHub desde la branch actual.

**Cómo**: usar la GitHub API directamente (el agente ya tiene MCP de GitHub, pero un tool nativo es más confiable). Flujo:
1. `git_create_branch("fix/header-color")`
2. `apply_patch(...)` × N
3. `git_commit("fix: correct header color")`
4. `git_push("fix/header-color")`
5. `create_pr("Fix header color", "Changes: ...")` ← nuevo

**Archivos afectados**: `app/skills/tools/git_tools.py` (1 tool nuevo, usa `httpx` con GitHub API)

---

### Feature 6: Intelligent Context Loading 🟡

**Qué**: en lugar de leer archivos uno por uno, el agente sigue una estrategia de "drill-down":
1. `list_source_files("app/")` → ver estructura
2. Pedir outline/resumen de un archivo (funciones, clases, imports)
3. Leer solo las funciones relevantes

**Por qué**: el contexto de WhatsApp es limitado. No se pueden leer archivos de 500 líneas enteros — necesita ser quirúrgico.

**Cómo**: 
- Tool `get_file_outline(path)` que retorna solo definiciones de funciones/clases con línea de inicio
- Tool `read_lines(path, start, end)` que lee un rango específico
- Mejorar `search_source_code` para retornar más contexto alrededor del match

**Archivos afectados**: `selfcode_tools.py` (2-3 tools nuevos)

---

### Feature 7: Coding System Prompt 🟢

**Qué**: cuando el agente detecta que el usuario quiere programar (o entra en `/agent` con un objetivo de código), usar un system prompt especializado:

```
You are a senior software engineer working autonomously on this codebase.

WORKFLOW:
1. Understand: read relevant files, search for patterns, understand the architecture
2. Plan: create a task plan with concrete steps
3. Execute: edit files, run tests after each change
4. Verify: ensure all tests pass before committing
5. Deliver: commit, push, create PR if appropriate

RULES:
- Use apply_patch for edits, never rewrite entire files
- Always run tests after changes
- Ask for approval before destructive operations
- Write conventional commit messages
```

**Archivos afectados**: `app/agent/loop.py` (nuevo prompt template para coding sessions)

---

### Feature 8: Progress Updates 🟢

**Qué**: enviar mensajes periódicos al usuario mientras el agente trabaja en background. Ej: "📍 Leyendo app/main.py...", "✅ Tests pasaron", "📝 Commit creado".

**Cómo**: el agent loop ya tiene la referencia de `wa_client`. En cada iteración/hito significativo, enviar un mensaje corto vía WhatsApp sin esperar respuesta.

**Archivos afectados**: `app/agent/loop.py` (enviar updates entre rounds)

---

### Feature 9: Undo / Rollback 🟢

**Qué**: tool `undo_last_change()` que revierte el último commit o el último patch aplicado.

**Cómo**: `git checkout -- <file>` para revertir cambios no commitados, `git revert HEAD` para el último commit.

**Archivos afectados**: `app/skills/tools/git_tools.py` (1-2 tools nuevos)

---

## Roadmap sugerido

### Sprint 1 — Mínimo viable (1-2 días)
- [ ] Feature 1: `run_command` (habilita test-fix)
- [ ] Feature 7: Coding system prompt
- [ ] Feature 8: Progress updates en agent loop

→ Con estos 3, el agente ya puede: leer código → editar → correr tests → arreglar → commitear.

### Sprint 2 — UX premium (2-3 días)
- [ ] Feature 3: Diff preview antes de aplicar
- [ ] Feature 5: PR creation
- [ ] Feature 6: Outline + read_lines (context inteligente)
- [ ] Feature 9: Undo/rollback

### Sprint 3 — Multi-proyecto (3-5 días)
- [ ] Feature 4: Workspace selection + Docker mounts
- [ ] Feature 2: Test-fix loop como modo explícito

---

## Ejemplo de sesión ideal

```
👤 /agent Arreglá el bug de login: cuando el usuario pone un email inválido, crashea

🤖 📍 Entendiendo el objetivo...
🤖 📋 Plan creado:
   - [ ] Encontrar el código de login
   - [ ] Reproducir el bug (leer tests existentes)
   - [ ] Implementar validación de email
   - [ ] Agregar test para email inválido
   - [ ] Correr tests
   - [ ] Commitear y pushear

🤖 📍 Buscando "login" en el código...
   Encontré: app/auth/views.py:45, app/auth/forms.py:12

🤖 📍 Leyendo app/auth/views.py...
   El problema está en línea 52: `user = User.objects.get(email=email)`
   No valida el formato del email antes de la query.

🤖 📝 Cambio propuesto en app/auth/views.py:
   - user = User.objects.get(email=email)
   + if not validate_email(email):
   +     return JsonResponse({"error": "Invalid email"}, status=400)
   + user = User.objects.get(email=email)
   ¿Aplico este cambio? (sí/no)

👤 sí

🤖 ✅ Patch aplicado
🤖 📍 Corriendo tests...
🤖 ✅ 47 tests passed, 0 failed
🤖 ✅ Commit: "fix: validate email format before login query"
🤖 ✅ Push a branch fix/validate-login-email
🤖 ✅ PR creado: "Fix: validate email format before login query"

✅ *Sesión agéntica completada*
_Plan: 6 pasos completados, 0 pendientes._
```

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El agente borra código importante | `_is_safe_path` + HITL + git rollback |
| `run_command` ejecuta algo peligroso | Whitelist o HITL para commands no reconocidos |
| Contexto de WhatsApp se llena con output largo | `_clear_old_tool_results` + compactación JSON-aware |
| El agente entra en loop de fix infinito | Max 3 intentos de fix por test failure |
| El usuario quiere trabajar en un repo que no está montado | Mensaje claro de error + instrucciones de setup |
