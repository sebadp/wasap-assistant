# Feature: Autonomous Agent — Shell Execution & Coding Mode

> **Version**: v1.0
> **Implemented**: 2026-02-22
> **Phase**: Agent Mode (Sprint 1)
> **Status**: ✅ Implemented

---

## Qué hace

Extiende el Agent Mode con capacidades que lo convierten en un **programador autónomo**:

1. **Shell Execution** — ejecuta comandos (`pytest`, `ruff`, `git`, etc.) desde el container
2. **Loop Detection** — previene que el agente entre en loops infinitos
3. **Coding Prompt + Progress** — instrucciones especializadas para programar + updates por WhatsApp
4. **Diff Preview** — permite previsualizar diffs antes de aplicar cambios
5. **PR Creation** — creación automatizada de Pull Requests en GitHub
6. **Session Persistence** — guardado de estado en JSONL para retomar sesiones interrumpidas
7. **Bootstrap Files** — personalización del agente vía `SOUL.md`, `USER.md` y `TOOLS.md`

---

## Arquitectura

```
app/skills/tools/
├── shell_tools.py            # run_command, manage_process, gc_stale_processes
├── selfcode_tools.py         # preview_patch, apply_patch, etc.
└── git_tools.py              # git_create_pr, git_commit, etc.

app/agent/
├── loop.py                   # _check_loop_detection, _extract_tool_history
                              # _AGENT_SYSTEM_PROMPT (coding-aware, carga bootstrap files)
                              # Progress updates (WA messages entre rounds)
└── persistence.py            # append_to_session, load_session_history

app/config.py                 # agent_shell_allowlist
app/database/db.py            # agent_command_log (audit table)
app/skills/router.py          # categoría "shell"
```

---

## Shell Execution: `run_command` + `manage_process`

### `run_command(command, timeout, background)`

Ejecuta un comando shell en `_PROJECT_ROOT`:

```
run_command("pytest tests/ -v")
→ Exit code: 0 | Duration: 1234ms
  stdout:
  ===== 47 passed in 1.23s =====

run_command("ruff check app/", timeout=60)
→ Exit code: 1 | Duration: 312ms
  stdout:
  app/main.py:5:1: F401 [*] `os` imported but unused
  Found 1 error.
```

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `command` | — | Comando a ejecutar |
| `timeout` | 30s | Max tiempo de espera (max 300s) |
| `background` | false | Si true, retorna `process_id` inmediato |

### `manage_process(action, process_id, limit)`

Gestiona procesos en background:

| Action | Qué hace |
|--------|----------|
| `list` | Muestra todos los procesos (activos y terminados) |
| `poll` | Nuevo output + exit status desde última lectura |
| `log` | Últimas N líneas (default 50, max 200) |
| `kill` | Termina el proceso (SIGTERM → SIGKILL) |

---

## Modelo de seguridad (defense-in-depth)

```
Capa 1: AGENT_WRITE_ENABLED=false → todo bloqueado
         │
Capa 2: _validate_command(command)
         ├── Denylist (rm, sudo, chmod) → 🚫 BLOQUEO
         ├── Shell operators (|, &&, ;) → ⚠️ HITL
         ├── Allowlist (pytest, ruff, git) → ✅ OK
         └── Unknown → ⚠️ HITL
         │
Capa 3: Execution sandbox
         ├── shell=False (no injection)
         ├── stdin=DEVNULL (no interactive)
         ├── cwd=PROJECT_ROOT
         └── timeout hard
         │
Capa 4: Resource limits
         ├── Max 5 procesos background
         ├── Output truncado a 50KB (4K al LLM)
         ├── Kill automático a 30 min
         └── GC cada 5 min
```

### Auditoría

Cada comando se registra en `agent_command_log`:

```sql
SELECT command, decision, exit_code, duration_ms FROM agent_command_log ORDER BY id DESC LIMIT 5;
```

---

## Loop Detection

Detecta dos patrones de loop:

| Detector | Patrón | Warning | Circuit Breaker |
|----------|--------|---------|-----------------|
| **genericRepeat** | Mismo tool + mismos params | 3× → mensaje ⚠️ | 5× → abortar sesión |
| **pingPong** | A→B→A→B sin progreso | 4 alternaciones → mensaje ⚠️ | — |

Implementado en `_check_loop_detection()` y `_extract_tool_history()` en `loop.py`.

---

## Coding System Prompt

El prompt del agente sigue el workflow:

```
UNDERSTAND → PLAN → EXECUTE → TEST → FIX → DELIVER
```

Reglas clave:
- Testear después de cada edit (`run_command("pytest ...")`)
- Usar `apply_patch` para edits, `write_source_file` solo para archivos nuevos
- Conventional commits (`fix:`, `feat:`, `refactor:`)
- Max 3 intentos de fix por paso antes de skip
- Pedir aprobación antes de operaciones destructivas

---

## Progress Updates

Entre rounds, el agente envía por WhatsApp:

```
🔧 Round 3: 2/5 steps done
```

Best-effort: si falla el envío, el agent loop no se interrumpe.

---

## Diff Preview y PR Creation

### Diff Preview (`preview_patch`)
Permite visualizar los cambios (unified diff) propuestos en un archivo sin modificarlo en disco, brindando seguridad y revisiones paso a paso antes de aplicar un `apply_patch`.

### GitHub PR Creation (`git_create_pr`)
Automatiza la creación de Pull Requests una vez que una tarea esté terminada. Requiere de las variables de entorno `GITHUB_TOKEN` y `GITHUB_REPO` configuradas para realizar los llamados directamente a la API de GitHub.

---

## Persistencia y Bootstrap Files

### JSONL Persistence
Cada round de la sesión agéntica se añade/appendea a un archivo `.jsonl` en `data/agent_sessions/` a través de `persistence.py`. Esto permite utilizar `/agent-resume` para retomar el `task_plan` de una ejecución interrumpida previamente, dándole resiliencia contra caídas del bot.

### Bootstrap Files
Al iniciar una nueva sesión, el agente intentará leer 3 archivos opcionales desde el `_PROJECT_ROOT`:
- `SOUL.md`
- `USER.md`
- `TOOLS.md`
Si existen, su contenido se inyecta al final del _Agent System Prompt_ de la sesión, permitiendo inyectar comportamientos, personalidades, o requerimientos del usuario directos sin hardcodear.

---

## Intelligent Context Loading (Sprint 3 — F9)

Permite al agente navegar archivos grandes sin desbordar el contexto del LLM con contenido innecesario.

### `get_file_outline(path)`
- Usa `ast.parse()` para archivos `.py`: extrae clases, funciones/métodos con líneas de inicio y fin.
- Para otros tipos (JS, MD, YAML): fallback a regex detectando definiciones y headings.
- **No lee el contenido completo** — solo devuelve la estructura.
- Output cap: 4000 chars.

### `read_lines(path, start, end)`
- Lee un rango específico de líneas (1-indexed, inclusivo).
- **Máximo 200 líneas por llamada** — retorna error si se excede.
- Las líneas se devuelven numeradas: `L42: def foo():`

**Patrón recomendado para archivos >200 líneas:**
```
get_file_outline("app/agent/loop.py")   → ver estructura
read_lines("app/agent/loop.py", 288, 350)  → leer solo la función relevante
```

---

## User-Defined Cron Jobs (Sprint 3 — F8)

Permite crear tareas recurrentes que **sobreviven reinicios del container** gracias a persitencia en SQLite + APScheduler.

### Tools

| Tool | Firma | Descripción |
|------|-------|-------------|
| `create_cron` | `(schedule, message, timezone)` | Crea un cron usando expresión estándar de 5 campos |
| `list_crons` | `()` | Lista los crons activos del usuario |
| `delete_cron` | `(job_id)` | Elimina un cron por ID (soft-delete) |

**Sintaxis de `schedule` (5 campos):**
```
0 9 * * 1-5    → lunes a viernes a las 9am
0 */6 * * *    → cada 6 horas
30 8 * * 1     → cada lunes a las 8:30am
```

### Persistencia
- Tabla `user_cron_jobs` en SQLite (schema en `db.py`).
- Al iniciar, `main.py` restaura todos los crons activos desde la DB mediante `repository.get_active_cron_jobs()`.
- Límite: 20 crons activos por usuario.

---

## Multi-Project Workspace (Sprint 3 — F10)

Permite cambiar el proyecto activo sin reiniciar el container.

### Tools

| Tool | Descripción |
|------|-------------|
| `list_workspaces` | Lista los directorios disponibles bajo `PROJECTS_ROOT` |
| `switch_workspace(name)` | Cambia `_PROJECT_ROOT` activo (selfcode + shell tools) |
| `get_workspace_info` | Muestra path, branch git, cantidad de archivos y últimos commits |

**Seguridad:** `switch_workspace` valida que `name` sea un subdirectorio directo de `PROJECTS_ROOT` (sin `..` ni paths absolutos).

---

## Configuración (`.env`)

```bash
# Allowlist de comandos seguros (comma-separated)
AGENT_SHELL_ALLOWLIST=pytest,ruff,mypy,make,npm,pip,git,cat,head,tail,wc,ls,find,grep,echo,python,node

# Habilita shell + write tools (OFF por defecto)
AGENT_WRITE_ENABLED=false

# GitHub (Sprint 2 — F5)
GITHUB_TOKEN=ghp_...
GITHUB_REPO=owner/repo

# Multi-project workspace (Sprint 3 — F10, opcional)
PROJECTS_ROOT=/home/user/projects
```

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Razón |
|----------|----------------------|-------|
| `shell=False` con `shlex.split` | `shell=True` | Previene command injection — el LLM no puede inyectar operadores shell |
| Allowlist + HITL para unknowns | Blocklist only | Más seguro: solo lo conocido pasa sin aprobación |
| `stdin=DEVNULL` | Permitir stdin | Evita cuelgues con comandos interactivos (vi, python REPL) |
| Audit table en SQLite | Solo logging | Permite queries SQL para análisis post-mortem |
| Loop detection en el outer loop | En el inner loop | Detecta patrones entre rounds, no solo dentro de un round |

---

## Gotchas / Edge cases

- **Comandos con pipes** (`pytest | tee output.txt`) triggerean HITL aunque los componentes sean seguros, por el shell operator `|`
- **`shlex.split` falla** con quotes desbalanceados → el comando se rechaza como DENY
- **Background processes no persisten** al reiniciar el container — se limpian al restart
- **Exit code 137** = OOM kill del OS. El agente lo verá como "command failed"
- **Progress updates solo se envían si hay task plan** — si el agente no creó plan, no hay updates

---

## Testing

📋 [Guía de testing](../testing/autonomous_agent_testing.md)

---

## Referencias

- Exec plan: [`docs/exec-plans/autonomous_agent_plan.md`](../exec-plans/autonomous_agent_plan.md)
- Sprint 2 plan: [`autonomous_agent_sprint2_plan.md`](../exec-plans/autonomous_agent_sprint2_plan.md)
- Sprint 3 plan: [`autonomous_agent_sprint3_plan.md`](../exec-plans/autonomous_agent_sprint3_plan.md)
- Agent Mode base: [`docs/features/agentic_sessions.md`](agentic_sessions.md)
- Evaluación Claude Code: [`docs/exec-plans/claude_code_experience.md`](../exec-plans/claude_code_experience.md)
- Evaluación OpenClaw: [`docs/exec-plans/openclaw_experience.md`](../exec-plans/openclaw_experience.md)
