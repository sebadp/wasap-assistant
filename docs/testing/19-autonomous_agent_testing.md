# Manual Testing: Autonomous Agent (Shell Execution, Loop Detection, Coding Mode)

> **Feature documentada**: [`docs/features/19-autonomous_agent.md`](../features/19-autonomous_agent.md)
> **Prerequisites**: Container corriendo, Ollama con modelos descargados, `AGENT_WRITE_ENABLED=true` en `.env`

---

## Pre-requisitos

```bash
# Asegurar que AGENT_WRITE_ENABLED=true en .env
grep AGENT_WRITE_ENABLED .env

# Rebuild si cambiaste .env
docker compose up -d --build wasap
```

---

## Test Cases: Shell Execution

### TC-1: Comando en allowlist (happy path)

**Enviar**:
```
/agent Corré los tests del proyecto
```

**Esperado**:
1. Agente crea task plan con pasos
2. Agente llama `run_command("pytest tests/ -v")` o similar
3. Output incluye exit code, duración, y stdout
4. Agente reporta resultado

**Verificar en logs**:
```bash
docker compose logs wasap 2>&1 | grep "agent.shell"
# Debe mostrar: decision=allow, exit_code, duration_ms
```

### TC-2: Comando bloqueado (denylist)

**Enviar**:
```
/agent Ejecutá rm -rf /tmp/test
```

**Esperado**:
- El agente recibe `"🚫 Command blocked: rm is not allowed"`
- No se ejecuta ningún proceso

**Verificar en logs**:
```bash
docker compose logs wasap 2>&1 | grep "decision.*deny"
```

### TC-3: Comando desconocido (HITL)

**Enviar**:
```
/agent Ejecutá curl https://example.com
```

**Esperado**:
- El agente recibe mensaje de que requiere aprobación
- Agente debería llamar `request_user_approval` con el comando
- Al aprobar, ejecuta el comando

### TC-4: Shell operators (HITL)

**Enviar**:
```
/agent Corré pytest tests/ -v | head -20
```

**Esperado**:
- El pipe `|` triggerea HITL
- El agente pide aprobación antes de ejecutar

### TC-5: Timeout

**Enviar**:
```
/agent Corré sleep 999 con timeout 5
```

**Esperado**:
- El comando se mata después de ~5-30s
- Retorna `"⏰ Command timed out after Ns"`

**Verificar en logs**:
```bash
docker compose logs wasap 2>&1 | grep "agent.shell.timeout"
```

### TC-6: Background process

**Enviar**:
```
/agent Corré pytest en background y monitoreá el progreso
```

**Esperado**:
1. `run_command("pytest", background=true)` retorna un `process_id`
2. Agente llama `manage_process(action="poll", process_id="...")` para ver output
3. Cuando completa, muestra exit code

---

## Test Cases: Loop Detection

### TC-7: genericRepeat warning

**Enviar una tarea ambigua/imposible**:
```
/agent Arreglá algo que está mal en el código
```

**Esperado**:
- Si el agente repite la misma herramienta 3+ veces → aparece warning `⚠️`
- Si repite 5+ veces → circuit breaker aborta la sesión

**Verificar en logs**:
```bash
docker compose logs wasap 2>&1 | grep "agent.loop.detected"
# Debe mostrar: detector=genericRepeat, count, action=warning|circuit_breaker
```

### TC-8: Circuit breaker

Forzar un loop: dar al agente una instrucción que causa lectura repetida del mismo archivo.

**Esperado**:
- Después de 5 repeticiones, sesión se aborta con mensaje de error
- Log muestra `action=circuit_breaker`

---

## Test Cases: Coding Prompt + Progress

### TC-9: Progress updates

**Enviar**:
```
/agent Listá los archivos del proyecto y contá cuántos .py hay
```

**Esperado**:
- Durante la ejecución, recibís por WhatsApp: `🔧 Round 1: 0/N steps done`, `🔧 Round 2: 1/N steps done`...
- Al final: `✅ Sesión agéntica completada`

### TC-10: Coding workflow completo

**Enviar**:
```
/agent Agregá un docstring a la función gc_stale_processes en shell_tools.py
```

**Esperado**:
1. Agente crea task plan
2. Lee `app/skills/tools/shell_tools.py`
3. Aplica patch con docstring
4. Corre tests (`run_command("pytest")`)
5. Si pasan → commit + push
6. Progress updates entre rounds

---

## Test Cases: Sprint 2 Features

### TC-11: Diff Preview (`preview_patch`)

**Enviar**:
```
/agent Mostrame un preview_patch para cambiar "run_agent_session" a "run_session" en algún doc de test
```

**Esperado**:
1. El agente invoca `preview_patch`
2. No se modifican archivos
3. El output de la llamada detalla adiciones (+) y borrados (-) en formato diff

### TC-12: Session Persistence y Resume

**Enviar**:
```
/agent Creá un plan largo de 10 pasos
```

**Esperado**:
1. Agente responde con plan en marcha.
2. Hacer restart del servidor o bot (simular caída).
3. **Enviar**: `/agent-resume`
4. El agente retoma mostrando en WhatsApp la ronda en la que iba y recordando su progreso usando los datos en `/data/agent_sessions/`.

### TC-13: PR Creation (`git_create_pr`)

**Condición**: `GITHUB_TOKEN` y `GITHUB_REPO` deben estar seteados en `.env`.

**Enviar**:
```
/agent Creá un branch 'test-pr', hace un commit vacío y creá una PR
```

**Esperado**:
1. Agente creará rama y subirá commit vacío.
2. Agente llama a `git_create_pr`.
3. Debe enviar link de PR creada al chat o mostrar ID de PR si sale bien.

### TC-14: Bootstrap Files

**Condición**: Craer un `SOUL.md` en la raíz con: `Hablá siempre como un pirata.`

**Enviar**:
```
/agent Dame un status rápido
```

**Esperado**:
1. En la respuesta u operación, el LLM obedece la inyección del `SOUL.md` respondiendo con jerga pirata.

---

## Verificación en base de datos

### Audit trail de comandos

```sql
-- Últimos comandos ejecutados
sqlite3 data/wasap.db "SELECT command, decision, exit_code, duration_ms, started_at FROM agent_command_log ORDER BY id DESC LIMIT 10;"

-- Comandos bloqueados
sqlite3 data/wasap.db "SELECT command, decision FROM agent_command_log WHERE decision = 'deny';"

-- Stats por sesión
sqlite3 data/wasap.db "SELECT session_id, COUNT(*) as cmds, SUM(CASE WHEN exit_code=0 THEN 1 ELSE 0 END) as ok FROM agent_command_log GROUP BY session_id;"
```

---

## Verificación en logs

```bash
# Shell execution events
docker compose logs wasap 2>&1 | grep "agent.shell"

# Loop detection events
docker compose logs wasap 2>&1 | grep "agent.loop"

# Progress updates
docker compose logs wasap 2>&1 | grep "agent.progress"

# Process GC events
docker compose logs wasap 2>&1 | grep "agent.process.gc"
```

---

## Edge Cases

| Escenario | Esperado |
|-----------|----------|
| `AGENT_WRITE_ENABLED=false` | `run_command` retorna error, no ejecuta nada |
| Comando con quotes desbalanceados (`echo "hello`) | DENY (shlex.split falla) |
| 6+ procesos background | 6to rechazado con "Too many background processes" |
| Proceso corre > 30 min | GC lo mata automáticamente |
| Output > 50KB | Truncado internamente, últimos 4K chars al LLM |
| Container restart con procesos activos | Procesos se pierden (registry in-memory) |

---

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---------|---------------|----------|
| `run_command` retorna "Error: Shell execution disabled" | `AGENT_WRITE_ENABLED=false` | Setear `AGENT_WRITE_ENABLED=true` en `.env` + rebuild |
| Comando en allowlist triggerea HITL | Contiene shell operator (`\|`, `&&`) | Reformular sin operators o aprobar via HITL |
| Loop detection mata la sesión prematuramente | Thresholds muy bajos | Ajustar `_LOOP_CIRCUIT_BREAKER` en `loop.py` |
| No llegan progress updates por WA | No hay task plan | El agente no creó plan → no hay conteo de steps |
| `command not found` | El binario no está en el container | Agregar al Dockerfile o usar un comando disponible |

---

## Test Cases: Sprint 3 — Intelligent Context Loading (F9)

### TC-15: Outline de archivo Python

**Enviar**:
```
/agent Dame la estructura de loop.py
```

**Esperado**:
1. El agente llama `get_file_outline("app/agent/loop.py")`
2. Recibís un outline tipo:
   ```
   app/agent/loop.py (518 lines)
     def _check_loop_detection(...)  [L72-120]
     def run_agent_session(...)      [L288-480]
   ```
3. El agente NO llama `read_source_file` sobre el archivo completo

### TC-16: Outline de archivo no-Python

**Enviar**:
```
/agent Mostrame la estructura del README.md
```

**Esperado**:
- El agente llama `get_file_outline("README.md")`
- Se detectan headers (`#`, `##`, `###`) con sus líneas
- Fallback regex funciona correctamente

### TC-17: Lectura de rango de líneas

**Enviar**:
```
/agent Leé las líneas 50 a 80 de loop.py
```

**Esperado**:
- El agente llama `read_lines("app/agent/loop.py", 50, 80)`
- Output incluye líneas numeradas: `L50: ...`, `L51: ...`

### TC-18: Cap de 200 líneas

**Enviar**:
```
/agent Leé desde la línea 1 hasta la 500 de loop.py
```

**Esperado**:
- El agente recibe un error: `Error: Range too large (500 lines). Max 200 lines per call.`
- El agente debe dividir la lectura en chunks de ≤200 líneas

---

## Test Cases: Sprint 3 — Cron Jobs (F8)

### TC-19: Crear cron persistente

**Enviar**:
```
Recordame todos los lunes a las 9am que revise los PRs pendientes
```

**Esperado**:
1. El LLM llama `create_cron("0 9 * * 1", "Revisar PRs pendientes", "America/Argentina/Buenos_Aires")`
2. Respuesta confirma el ID del cron creado
3. El lunes siguiente a las 9am llega el recordatorio por WhatsApp

**Verificar en DB**:
```sql
sqlite3 data/wasap.db "SELECT * FROM user_cron_jobs WHERE active=1;"
```

### TC-20: Persistencia tras restart

1. Crear un cron
2. Reiniciar el container: `docker compose restart wasap`
3. Verificar en los logs al arrancar:
   ```bash
   docker compose logs wasap 2>&1 | grep "Restored"
   # Debe mostrar: Restored N cron job(s) from database
   ```
4. El cron debe seguir apareciendo en `list_crons`

### TC-21: Eliminar cron

**Enviar**:
```
Listame mis recordatorios recurrentes y eliminá el primero
```

**Esperado**:
1. LLM llama `list_crons` → muestra lista con IDs
2. LLM llama `delete_cron(job_id)` → confirmación de eliminación
3. El cron desaparece de `list_crons` y de la DB

---

## Test Cases: Sprint 3 — Multi-Project Workspace (F10)

> **Prerequisito**: `PROJECTS_ROOT=/ruta/a/mis/proyectos` configurado en `.env` + rebuild.

### TC-22: Listar workspaces

**Enviar**:
```
/agent Listame los proyectos disponibles
```

**Esperado**:
- El agente llama `list_workspaces()`
- Muestra directorios bajo `PROJECTS_ROOT` con branch git y count de archivos
- Marca el proyecto activo con "← active"

### TC-23: Cambiar workspace

**Enviar**:
```
/agent Cambiate al proyecto "mi-frontend"
```

**Esperado**:
1. El agente llama `switch_workspace("mi-frontend")`
2. Confirmación con path, branch y conteo de archivos del nuevo proyecto
3. Llamadas posteriores a `list_source_files` muestran archivos del nuevo proyecto

### TC-24: Seguridad path traversal

**Enviar**:
```
/agent Cambiate al proyecto "../../etc"
```

**Esperado**:
- El agente recibe: `Error: Invalid project name '../../etc'. Use a simple directory name without path separators.`
- No se modifica el workspace activo

---

## Edge Cases (Sprint 3)

| Escenario | Esperado |
|-----------|----------|
| `get_file_outline` con archivo no-.py con syntax errors | Fallback a regex, sin error |
| `read_lines` con `start > total_lines` | Error descriptivo: `start=N exceeds file length` |
| `create_cron` con expresión inválida | Error: `Invalid cron expression '...'` con detalles |
| 21+ crons activos | Error: `Maximum of 20 active cron jobs per user reached` |
| `switch_workspace` con nombre con `/` | Error: path traversal bloqueado |
| `list_workspaces` sin `PROJECTS_ROOT` | Error descriptivo invitando a configurar la variable |
