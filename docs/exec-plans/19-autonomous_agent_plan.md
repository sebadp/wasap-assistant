# Exec Plan: Autonomous Agent Experience

> **Fecha**: 2026-02-22
> **Estado**: ✅ Completado
> **Pre-requisitos**: Fases 1-8 completadas, Context Engineering completado
> **Fuentes**: [Claude Code eval](EX-claude_code_experience.md) · [OpenClaw eval](EX-openclaw_experience.md)

---

## Estado de Implementación

### Sprint 1 (Completado)
- [x] F1: shell_tools.py — run_command + manage_process con seguridad multi-capa
- [x] F1: CommandDecision (ALLOW/DENY/ASK) + denylist + allowlist configurable
- [x] F2: Loop detection en loop.py (_check_loop_detection con genericRepeat + pingPong)
- [x] F3: Coding system prompt + progress updates por round en loop.py

### Sprint 2 (Completado)
- [x] F4: preview_patch en selfcode_tools.py (unified diff, sin aplicar)
- [x] F5: git_create_pr en git_tools.py (GitHub REST API, requiere GITHUB_TOKEN)
- [x] F6: app/agent/persistence.py — append-only JSONL en data/agent_sessions/
- [x] F7: Bootstrap files (SOUL.md, USER.md, TOOLS.md) cargados en run_agent_session

### Sprint 3 (Completado)
- [x] F8: Cron jobs en scheduler_tools.py (create_cron, list_crons, delete_cron)
- [x] F9: get_file_outline + read_lines en selfcode_tools.py (AST-based)
- [x] F10: workspace_tools.py — list_workspaces, switch_workspace, get_workspace_info

---

## Objetivo

Convertir el agente WasAP en un **programador autónomo** controlable desde WhatsApp. El usuario describe una tarea ("arreglá el bug de login", "agregá dark mode") y el agente:
1. Entiende el codebase (lee, busca, lista)
2. Planifica (task plan con steps concretos)
3. Ejecuta (edita archivos, corre tests, fixea errores)
4. Entrega (commitea, pushea, opcionalmente crea PR)
5. Reporta (envía progress updates por WhatsApp)

---

## Sprint 1 — Core Autonomy (2-3 días)

### F1: Shell Execution (`run_command` + `manage_process`)

> La pieza #1 que falta. Sin esto el agente no puede correr tests, linters, ni validar sus cambios.

#### [NEW] [shell_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/shell_tools.py)

Dos tools:

**`run_command(command, timeout, background)`**
- Ejecuta un comando shell en `_PROJECT_ROOT`
- `timeout`: default 30s, max 300s
- `background`: si True, retorna `process_id` inmediato
- Sync: retorna `{"exit_code": N, "stdout": "...", "stderr": "..."}`
- Trunca output a 4000 chars (WhatsApp-friendly)
- Gated por `settings.agent_write_enabled`

**`manage_process(action, process_id, limit)`**
- `action`: `list` | `poll` | `log` | `kill`
- `poll`: retorna nuevo output desde última lectura + exit status si completó
- `log`: retorna últimas N líneas (default 50, max 200)
- `kill`: termina el proceso (SIGTERM, fallback SIGKILL)
- `list`: muestra todos los procesos activos del agente

Implementación interna:
```python
# Module-level process registry
_processes: dict[str, _ProcessInfo] = {}

@dataclass
class _ProcessInfo:
    proc: asyncio.subprocess.Process
    stdout_buffer: list[str]
    stderr_buffer: list[str]
    started_at: float
    command: str
    exit_code: int | None = None
```

Seguridad:
- **Allowlist** configurable: `AGENT_SHELL_ALLOWLIST=pytest,ruff,mypy,make,npm,pip,git,cat,head,tail,wc,ls,find,grep`
- Comandos no en la allowlist → HITL (`request_user_approval`)
- Bloquea: `rm -rf`, `sudo`, pipes a archivos sensibles
- Todos corren en `_PROJECT_ROOT` como cwd

#### [MODIFY] [__init__.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/__init__.py)

- Importar y llamar `register_shell(registry, settings)` en `register_builtin_tools()`

#### [MODIFY] [config.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/config.py)

- Agregar `agent_shell_allowlist: str = "pytest,ruff,mypy,make,npm,pip,git,cat,head,tail,wc,ls,find,grep"`

#### [MODIFY] [router.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/router.py)

- Agregar categoría `"shell"` a `TOOL_CATEGORIES` con keywords: `run, execute, command, test, lint, build, install`

---

### F2: Loop Detection Guardrails

> Previene que el agente gaste sus 15 rounds repitiendo la misma acción sin progreso.

#### [MODIFY] [loop.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/agent/loop.py)

Nueva función `_check_loop_detection(tool_history)`:
- Trackea últimos 20 tool calls como `(tool_name, params_hash)`
- **genericRepeat**: mismo (name, hash) 3+ veces → inyectar warning
- **genericRepeat**: mismo (name, hash) 5+ veces → circuit breaker (abortar round)
- **pingPong**: patrón A→B→A→B 3+ veces → warning + skip

Integración: se llama después de cada `execute_tool_loop` round, antes de `_clear_old_tool_results`.

Constantes:
```python
_LOOP_WARNING_THRESHOLD = 3
_LOOP_CIRCUIT_BREAKER = 5
_LOOP_HISTORY_SIZE = 20
```

---

### F3: Coding System Prompt + Progress Updates

> El agente necesita instrucciones especializadas para programar (vs. chatear) y el usuario necesita saber qué está pasando.

#### [MODIFY] [loop.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/agent/loop.py)

**Coding prompt**: reemplazar `_AGENT_SYSTEM_PROMPT` con versión coding-aware:
```
You are a senior software engineer working autonomously on this codebase.

OBJECTIVE: {objective}

WORKFLOW:
1. UNDERSTAND: list_source_files, read_source_file, search_source_code
2. PLAN: create_task_plan with concrete steps
3. EXECUTE: apply_patch for edits, write_source_file for new files
4. TEST: run_command("pytest ...") after EVERY code change
5. FIX: if tests fail, read errors, fix, re-test (max 3 attempts per step)
6. DELIVER: git_commit, git_push when all tests pass

RULES:
- Always test after edits. Never commit untested code.
- Use apply_patch for edits. Only use write_source_file for new files.
- Use conventional commit messages: "fix: ...", "feat: ...", "refactor: ..."
- If a step fails 3 times, skip it and move to the next. Note the failure.
- Ask for approval (request_user_approval) before destructive operations.
```

**Progress updates**: en el agent loop, después de cada round exitoso, enviar un mensaje breve al usuario via `wa_client`:
```python
# After each round in the agent loop:
if wa_client and session.task_plan:
    done = session.task_plan.count("[x]")
    total = done + session.task_plan.count("[ ]")
    status_emoji = "🔧" if iteration < session.max_iterations - 1 else "📋"
    await wa_client.send_message(
        session.phone_number,
        f"{status_emoji} Round {iteration+1}: {done}/{total} steps done"
    )
```

---

## Sprint 2 — UX Premium (3-4 días)

### F4: Diff Preview

#### [MODIFY] [selfcode_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/selfcode_tools.py)

Nuevo tool `preview_patch(path, search, replace)`:
- Genera un diff formateado (unified diff format)
- Lo retorna como texto — el agente lo envía al usuario
- El agente luego llama `request_user_approval` antes de `apply_patch`
- No aplica nada — solo muestra

### F5: PR Creation

#### [MODIFY] [git_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/git_tools.py)

Nuevo tool `git_create_pr(title, body)`:
- Usa GitHub API (`POST /repos/{owner}/{repo}/pulls`)
- Requiere `GITHUB_TOKEN` en config
- Retorna URL del PR creado

#### [MODIFY] [config.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/config.py)

- Agregar `github_token: str = ""` y `github_repo: str = ""`

### F6: Session Persistence (JSONL)

#### [NEW] [persistence.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/agent/persistence.py)

- `save_round(session_id, round_data)` → append a `data/agent_sessions/<session_id>.jsonl`
- `load_session(session_id)` → leer y reconstruir estado
- `list_sessions(phone_number)` → listar sesiones de un usuario
- Cada línea JSONL: `{"round": N, "tool_calls": [...], "reply": "...", "task_plan": "..."}`

#### [MODIFY] [loop.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/agent/loop.py)

- Después de cada round, `save_round(session.session_id, round_data)`
- Nuevo comando `/agent-resume` para retomar la última sesión

### F7: Bootstrap Files

#### [MODIFY] [loop.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/agent/loop.py)

- Al inicio de `run_agent_session`, cargar archivos opcionales:
  - `data/workspace/SOUL.md` → prepend como system message (personalidad)
  - `data/workspace/USER.md` → prepend como system message (perfil del usuario)
  - `data/workspace/TOOLS.md` → prepend como system message (notas sobre herramientas)
- Si no existen, se ignoran silenciosamente

---

## Sprint 3 — Extensions (5+ días)

### F8: User-Defined Cron Jobs

#### [MODIFY] [scheduler_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/scheduler_tools.py)

- `create_cron(schedule, message, phone_number)` → registra en APScheduler + tabla `user_cron_jobs`
- `list_crons()` → lista crons del usuario
- `delete_cron(id)` → elimina un cron

#### [MODIFY] [db.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/database/db.py)

- Tabla `user_cron_jobs`: `id, phone_number, schedule, message, created_at, active`

### F9: Intelligent Context Loading

#### [MODIFY] [selfcode_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/selfcode_tools.py)

- `get_file_outline(path)` → extrae funciones/clases con líneas (AST-based)
- `read_lines(path, start, end)` → lee un rango específico de un archivo

### F10: Multi-Project Workspace

#### [MODIFY] [config.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/config.py)

- `projects_root: str = ""` — directorio base para proyectos

#### [NEW] [workspace_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/workspace_tools.py)

- `switch_project(name)` → cambia `_PROJECT_ROOT` dinámicamente
- `list_projects()` → lista directorios en `projects_root`

---

## Modelo de Seguridad

> El agente puede ejecutar código arbitrario. La seguridad es **defense-in-depth**: múltiples capas independientes, cada una suficiente para prevenir daño si las demás fallan.

### Capa 1: Gate de habilitación

| Control | Cómo funciona |
|---|---|
| `AGENT_WRITE_ENABLED=false` (default) | Bloquea `run_command`, `write_source_file`, `apply_patch` y `manage_process(kill)`. Sin esta flag = read-only completo. |
| `allowed_phone_numbers` en config | Solo usuarios en la lista pueden usar el agente. Verificado en `_handle_message` antes de despachar. |

### Capa 2: Command validation (antes de ejecutar)

```
[LLM genera tool call: run_command("rm -rf /")]
        │
        ▼
[_validate_command(command)]
    │
    ├── Denylist check ──────► BLOQUEO inmediato + log
    │   rm -rf, sudo, chmod 777, mkfs, dd, shutdown,
    │   reboot, kill -9, :(){ :|:& };:, > /dev/sda
    │
    ├── Allowlist check ──────► ✅ ejecutar directo
    │   pytest, ruff, mypy, make, npm, pip, git,
    │   cat, head, tail, wc, ls, find, grep, echo, python -m pytest
    │
    ├── Shell operator check ─► HITL si contiene: |, >, >>, &&, ||, ;, $(), `backtick`
    │   (previene: pytest | rm -rf /, echo x > /etc/passwd)
    │
    └── Comando desconocido ──► HITL (request_user_approval)
            │
            └── Si aprobado → ejecutar
            └── Si rechazado → abortar + log
```

Implementación en `_validate_command(command) -> CommandDecision`:
```python
class CommandDecision(Enum):
    ALLOW = "allow"        # en allowlist, sin operadores peligrosos
    DENY = "deny"          # en denylist → bloqueo hard
    ASK = "ask"            # no reconocido o tiene operadores shell → HITL

def _validate_command(command: str) -> CommandDecision:
    tokens = shlex.split(command)       # parse sin ejecutar
    base_cmd = tokens[0] if tokens else ""

    # 1. Denylist check (base command + full command patterns)
    if base_cmd in _DENYLIST or any(p in command for p in _DANGEROUS_PATTERNS):
        return CommandDecision.DENY

    # 2. Shell operator check
    if any(op in command for op in _SHELL_OPERATORS):
        return CommandDecision.ASK

    # 3. Allowlist check
    if base_cmd in _allowlist:
        return CommandDecision.ALLOW

    # 4. Unknown → ask
    return CommandDecision.ASK
```

Constantes:
```python
_DENYLIST = {"rm", "sudo", "chmod", "chown", "mkfs", "dd", "shutdown", "reboot", "systemctl", "mount", "umount"}
_DANGEROUS_PATTERNS = {"rm -rf", "> /dev/", ":()", "fork bomb", "/etc/passwd", "/etc/shadow"}
_SHELL_OPERATORS = {"|", ">>", "&&", "||", ";", "$(", "`"}
# Pipe simple ">" se permite solo si el target es dentro de _PROJECT_ROOT (check especial)
```

### Capa 3: Execution sandboxing (durante ejecución)

| Control | Cómo funciona |
|---|---|
| `cwd = _PROJECT_ROOT` | Todos los comandos corren desde el root del proyecto — no se puede escapar via paths relativos en el cwd |
| `shell=False` | Usamos `asyncio.create_subprocess_exec(*tokens)` — no hay interpretación de shell. Previene injection |
| `timeout` hard | `asyncio.wait_for(proc.communicate(), timeout)` — kill si excede |
| `stdin=DEVNULL` | Bloquea stdin — comandos interactivos (vi, nano, python REPL, ssh) mueren inmediato |
| `PATH` limpio | Heredamos solo el PATH del container — no hay binarios inesperados |
| No `env` override | El subproceso hereda el env del container pero no puede leer secrets (solo en Python memory) |
| Procesos max = 5 | Como mucho 5 procesos background simultáneos per agente — `_MAX_CONCURRENT_PROCESSES = 5` |

### Capa 4: Resource limits

```python
_MAX_CONCURRENT_PROCESSES = 5   # por agente
_MAX_OUTPUT_BYTES = 50_000      # truncar stdout/stderr (50KB)
_MAX_OUTPUT_DISPLAY = 4_000     # retornar al LLM (4K chars)
_PROCESS_GC_INTERVAL = 300      # cleanup procesos muertos cada 5 min
_PROCESS_MAX_AGE = 1800         # kill automático después de 30 min
```

Cleanup automático:
- `_gc_stale_processes()` corre cada 5 minutos (registrado en APScheduler via `main.py`)
- Kill procesos que exceden `_PROCESS_MAX_AGE` (30 min)
- Remove procesos terminados del registry después de 10 min

### Tabla de auditoría: `agent_command_log`

Cada comando ejecutado se loguea en SQLite **antes y después** de la ejecución:

```sql
CREATE TABLE IF NOT EXISTS agent_command_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    command TEXT NOT NULL,
    decision TEXT NOT NULL,           -- 'allow', 'deny', 'ask_approved', 'ask_rejected'
    exit_code INTEGER,                -- NULL si aún corriendo o denegado
    stdout_preview TEXT,              -- primeros 500 chars
    stderr_preview TEXT,              -- primeros 500 chars
    duration_ms INTEGER,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    error TEXT                        -- si hubo excepción en la ejecución
);
```

Cada fila se inserta en 2 pasos:
1. **Pre-exec**: `INSERT` con `decision` y sin `exit_code`/`completed_at` (log de intento)
2. **Post-exec**: `UPDATE` con `exit_code`, `duration_ms`, `stdout_preview`, `completed_at`

Si el comando es `DENY`, solo se hace paso 1 (queda registrado el intento bloqueado).

### Failure modes

| Escenario | Comportamiento |
|---|---|
| Comando denegado (denylist) | Log + retorna `"🚫 Command blocked: {base_cmd} is not allowed"` |
| HITL rechazado por usuario | Log + retorna `"❌ Command rejected by user"` |
| Timeout | Kill proceso + retorna `"⏰ Command timed out after {timeout}s"` |
| Output > 50KB | Trunca internamente, retorna últimos 4K chars al LLM |
| 5+ procesos background | Retorna `"Too many background processes. Kill one first."` |
| Proceso zombie (>30 min) | GC lo mata automáticamente + log |
| `shell=False` falla con shlex | Retorna error + hint para reformular el comando |
| OOM del subprocess | El OS mata el proceso → exit_code=137 → log |

---

## Observabilidad

### Tracing: integración con trazas existentes

Cada sesión agéntica ya tiene un `TraceContext` (creado en `router.py`). Las operaciones del agente se instrumentan como spans hijos:

```python
# En shell_tools.py — cada run_command genera un span
trace = get_current_trace()
if trace:
    with trace.span(f"shell:{base_cmd}", kind="tool") as span:
        span.set_input({"command": command, "timeout": timeout})
        result = await _execute(...)
        span.set_output({"exit_code": result.exit_code, "duration_ms": duration})
```

Spans generados:

| Span name | Kind | Input | Output |
|---|---|---|---|
| `shell:<base_cmd>` | `tool` | command, timeout | exit_code, duration_ms |
| `agent_round:<N>` | `agent` | iteration, task_plan_snapshot | reply_preview, tools_used |
| `loop_detection` | `system` | tool_history | decision (ok/warning/abort) |
| `hitl:approval` | `user` | question | response, wait_time_ms |

### Structured logging

Todos los eventos del agente autónomo se loguean con campos estructurados:

```python
# Shell execution
logger.info(
    "agent.shell.execute",
    extra={
        "session_id": session.session_id,
        "phone": session.phone_number,
        "command": command,
        "decision": decision.value,      # allow | deny | ask_approved | ask_rejected
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "output_bytes": len(stdout),
        "background": background,
    },
)

# Loop detection
logger.warning(
    "agent.loop.detected",
    extra={
        "session_id": session.session_id,
        "detector": "genericRepeat",     # o "pingPong"
        "repeated_tool": tool_name,
        "count": repeat_count,
        "action": "warning",             # o "circuit_breaker"
    },
)

# Progress update
logger.info(
    "agent.progress",
    extra={
        "session_id": session.session_id,
        "iteration": iteration,
        "steps_done": done,
        "steps_total": total,
        "tools_used_this_round": tools_used,
    },
)
```

### Audit queries (para debugging y revisión)

```sql
-- Últimos 20 comandos ejecutados
SELECT command, decision, exit_code, duration_ms, started_at
FROM agent_command_log ORDER BY id DESC LIMIT 20;

-- Comandos bloqueados (intentos de abuso o errors del LLM)
SELECT phone_number, command, decision, started_at
FROM agent_command_log WHERE decision IN ('deny', 'ask_rejected')
ORDER BY id DESC;

-- Comandos más lentos
SELECT command, duration_ms, exit_code
FROM agent_command_log WHERE duration_ms > 10000
ORDER BY duration_ms DESC LIMIT 10;

-- Sesiones agénticas por usuario
SELECT session_id, COUNT(*) as commands, 
       SUM(CASE WHEN exit_code = 0 THEN 1 ELSE 0 END) as success,
       SUM(CASE WHEN exit_code != 0 THEN 1 ELSE 0 END) as failures
FROM agent_command_log
WHERE phone_number = ?
GROUP BY session_id;
```

### Métricas clave (via eval tools)

Extender `get_eval_summary` en `eval_tools.py` para incluir métricas del agente:

| Métrica | Cómo calcular |
|---|---|
| Commands executed (24h) | `COUNT(*) FROM agent_command_log WHERE started_at > datetime('now', '-1 day')` |
| Command success rate | `AVG(CASE WHEN exit_code=0 THEN 1.0 ELSE 0.0 END)` |
| Commands denied | `COUNT(*) WHERE decision='deny'` |
| Avg command duration | `AVG(duration_ms)` |
| Loop detections (24h) | `COUNT(*) FROM trace_spans WHERE name LIKE 'loop_detection%'` |
| Agent sessions completed | Contar sesiones con status `COMPLETED` en las trazas |

### Alerting (logs-based)

No necesitamos un sistema de alertas externo — aprovechamos el logging JSON + grep:

```bash
# Alertar si hay comandos denegados (posible prompt injection)
docker compose logs -f wasap 2>&1 | grep '"decision": "deny"'

# Alertar si hay circuit breakers (agente atascado)
docker compose logs -f wasap 2>&1 | grep '"action": "circuit_breaker"'

# Alertar si hay procesos zombie (>30 min)
docker compose logs -f wasap 2>&1 | grep 'agent.process.gc'
```

---

## Schema de datos

### `_ProcessInfo` (module-level en shell_tools.py)
```python
_processes: dict[str, _ProcessInfo] = {}

@dataclass
class _ProcessInfo:
    proc: asyncio.subprocess.Process
    stdout_buffer: list[str]
    stderr_buffer: list[str]
    started_at: float
    command: str
    session_id: str              # para audit trail
    phone_number: str            # para audit trail
    exit_code: int | None = None
    last_poll_offset: int = 0    # para poll incremental
```

### `agent_command_log` (SQLite — Sprint 1)
```sql
CREATE TABLE IF NOT EXISTS agent_command_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    command TEXT NOT NULL,
    decision TEXT NOT NULL,
    exit_code INTEGER,
    stdout_preview TEXT,
    stderr_preview TEXT,
    duration_ms INTEGER,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_cmd_log_session ON agent_command_log(session_id);
CREATE INDEX IF NOT EXISTS idx_cmd_log_phone ON agent_command_log(phone_number);
```

### `user_cron_jobs` (SQLite — Sprint 3)
```sql
CREATE TABLE IF NOT EXISTS user_cron_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number TEXT NOT NULL,
    schedule TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    active INTEGER DEFAULT 1
);
```

### Agent session JSONL (Sprint 2)
```json
{"round": 1, "iteration": 0, "tool_calls": ["list_source_files", "read_source_file"], "reply_preview": "Leí la estructura...", "task_plan_snapshot": "- [x] Leer código\n- [ ] Editar", "timestamp": "2026-02-22T16:30:00Z"}
```

---

## Orden de implementación

```
1. config.py              — nuevos settings (shell_allowlist, github_token)
2. db.py                  — tabla agent_command_log (DDL en SCHEMA)
3. shell_tools.py         — nuevo archivo (run_command + manage_process + validation + audit)
4. __init__.py            — registrar shell tools
5. router.py              — categoría "shell"
6. loop.py                — coding prompt + loop detection + progress updates + tracing spans
7. Documentación + testing
```

---

## Verification Plan

### Automated
```bash
# Shell tools
pytest tests/test_shell_tools.py -v

# Loop detection
pytest tests/test_loop_detection.py -v

# Lint + types
make check
```

### Security tests manuales
1. **Denylist**: `/agent Ejecutá rm -rf /tmp` → debe ser bloqueado sin HITL
2. **Shell operators**: `/agent Corré pytest | tee output.txt` → HITL (tiene pipe)
3. **Allowlist**: `/agent Corré pytest tests/ -v` → debe ejecutar directo
4. **HITL**: `/agent Corré curl https://example.com` → HITL (no está en allowlist)
5. **Timeout**: `/agent Corré sleep 999` → timeout después de 30s
6. **Process limit**: Lanzar 6 procesos background → 6to rechazado

### Observability checks
1. Verificar en logs: `grep "agent.shell.execute" data/wasap.log`
2. Verificar audit trail: `sqlite3 data/wasap.db "SELECT * FROM agent_command_log ORDER BY id DESC LIMIT 5;"`
3. Verificar tracing spans: `sqlite3 data/wasap.db "SELECT name, kind FROM trace_spans WHERE name LIKE 'shell:%' ORDER BY id DESC LIMIT 5;"`
4. Verificar loop detection: enviar tarea ambigua y verificar `grep "agent.loop.detected" data/wasap.log`

### Manual (WhatsApp)
1. `/agent Corré los tests y arreglá los que fallen`
   - Verificar: task plan → `run_command("pytest")` → arregla → re-testea
2. `/agent Agregá un endpoint GET /health en main.py`
   - Verificar: entiende código → edita → testea → commitea
3. Verificar progress updates (emojis + conteo de steps)

