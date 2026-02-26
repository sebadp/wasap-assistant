# Execution Plan: Autonomous Agent — Sprint 3 (Extensions)

> **Status:** ✅ Completado
> **Módulo:** Agentic Sessions
> **Objetivo:** Extender el agente autónomo con capacidades avanzadas: cron jobs persistentes definidos por el usuario, carga inteligente de contexto para archivos grandes, y soporte multi-proyecto para trabajar en más de un codebase.


---

## Estado de Implementación

- [x] F8: Tabla `user_cron_jobs` agregada al SCHEMA en app/database/db.py
- [x] F8: Repository methods: save_cron_job, list_cron_jobs, delete_cron_job, get_all_active_crons
- [x] F8: scheduler_tools.py — create_cron, list_crons, delete_cron con APScheduler
- [x] F8: Cron jobs re-cargados desde SQLite en startup (main.py lifespan)
- [x] F9: get_file_outline en selfcode_tools.py — AST-based para .py, regex para otros
- [x] F9: read_lines en selfcode_tools.py — lectura de rangos de líneas con offsets
- [x] F10: app/skills/tools/workspace_tools.py — list_workspaces, switch_workspace, get_workspace_info
- [x] F10: _PROJECT_ROOT dinámico en selfcode_tools.py (module-level var actualizable)
- [x] F10: workspaces_dir configurable en app/config.py

---

## Descripción General

Sprint 1 estableció la autonomía core (shell, loops, prompts). Sprint 2 añadió la UX premium (diffs, PRs, persistencia, bootstrap). **Sprint 3** cierra el ciclo convirtiendo al agente en una herramienta de productividad completa con 3 features:

1. **F8: User-Defined Cron Jobs** — Persistencia de tareas recurrentes en SQLite + APScheduler, sobreviviendo reinicios.
2. **F9: Intelligent Context Loading** — `get_file_outline` (AST) + `read_lines` para archivos grandes sin desbordar el contexto del LLM.
3. **F10: Multi-Project Workspace** — Cambio dinámico de `_PROJECT_ROOT` entre proyectos en un directorio configurable.

---

## Modificaciones Propuestas

### F8: User-Defined Cron Jobs

Actualmente `scheduler_tools.py` soporta reminders one-shot (`schedule_task`). F8 extiende esto con **cron jobs persistentes** que sobreviven reinicios del container.

#### [MODIFY] [db.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/database/db.py)

Agregar tabla `user_cron_jobs` al `SCHEMA`:

```sql
CREATE TABLE IF NOT EXISTS user_cron_jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number TEXT NOT NULL,
    cron_expr    TEXT NOT NULL,          -- "0 9 * * 1-5" (lunes a viernes 9am)
    message      TEXT NOT NULL,          -- "Buenos días, tu resumen de tareas:"
    timezone     TEXT NOT NULL DEFAULT 'UTC',
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cron_phone ON user_cron_jobs(phone_number, active);
```

#### [MODIFY] [repository.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/database/repository.py)

Agregar métodos CRUD para `user_cron_jobs`:
- `create_cron_job(phone_number, cron_expr, message, timezone) -> int`
- `list_cron_jobs(phone_number) -> list[dict]`
- `delete_cron_job(job_id, phone_number) -> bool`
- `get_active_cron_jobs() -> list[dict]` — para restaurar al boot

#### [MODIFY] [scheduler_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/scheduler_tools.py)

Agregar 3 nuevas tools:

**`create_cron(schedule, message, timezone)`**
- Parsea `schedule` como expresión cron (5 campos) usando `CronTrigger` de APScheduler
- Persiste en SQLite via `repository.create_cron_job(...)`
- Registra el job en el scheduler global con `_send_reminder` como callback
- Retorna confirmación con el ID del cron creado

**`list_crons()`**
- Lista cron jobs activos del usuario actual (via `_current_user_phone`)
- Formato: `ID | Schedule | Message | Timezone`

**`delete_cron(job_id)`**
- Marca como `active=0` en SQLite
- Remueve el job de APScheduler
- Retorna confirmación

#### [MODIFY] [main.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/main.py)

Al inicio del lifespan, después de inicializar el scheduler:
- Llamar a `repository.get_active_cron_jobs()` 
- Para cada cron, registrarlo en APScheduler con `CronTrigger.from_crontab(cron_expr)`
- Log: `"Restored N cron jobs from database"`

#### [MODIFY] [router.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/router.py)

Agregar `create_cron`, `list_crons`, `delete_cron` a la categoría `"time"` en `TOOL_CATEGORIES`.

---

### F9: Intelligent Context Loading

Actualmente `read_source_file` lee el archivo completo. Para archivos de 500+ líneas, esto satura el contexto del LLM innecesariamente. F9 agrega dos tools que permiten exploración quirúrgica.

#### [MODIFY] [selfcode_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/selfcode_tools.py)

**`get_file_outline(path)`**
- Usa `ast.parse()` para archivos `.py`
- Extrae: clases (nombre, línea inicio-fin), funciones/métodos (nombre, firma, línea inicio-fin), decoradores
- Para archivos no-Python: fallback a regex simple (`def `, `class `, `function `, `export `) con número de línea
- Retorna un outline tipo:
  ```
  app/agent/loop.py (518 lines)
  ├── L50-70   _AGENT_SYSTEM_PROMPT (constant)
  ├── L72-120  _check_loop_detection(tool_history)
  ├── L122-200 _extract_tool_history(messages)
  ├── L252-285 _is_session_complete(session, last_reply)
  ├── L288-480 run_agent_session(session, ollama_client, ...)
  └── L492-518 create_session(phone_number, objective, ...)
  ```
- Límite de output: 4000 chars (truncar con `...and N more items`)

**`read_lines(path, start, end)`**
- Lee un rango específico de un archivo (1-indexed)
- `start`: línea inicial (required)
- `end`: línea final (required, max `start + 200`)
- Retorna las líneas numeradas: `L42: def foo():` ...
- Validaciones: archivo existe, rango válido, max 200 líneas por call
- Reutiliza `_is_safe_path()` existente

**Impacto en prompt del agente:**

#### [MODIFY] [loop.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/agent/loop.py)

Actualizar `_AGENT_SYSTEM_PROMPT` para incluir instrucción:
```
- For large files (>200 lines), use get_file_outline first, then read_lines for specific sections.
  Do NOT read_source_file on large files — use the outline+lines pattern instead.
```

---

### F10: Multi-Project Workspace

Permite al agente trabajar en múltiples codebases sin reconfigurar el container.

#### [MODIFY] [config.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/config.py)

Agregar:
```python
projects_root: str = ""  # e.g. "/home/user/projects"
```

Si está vacío, el comportamiento es el actual (single project = raíz del repo).

#### [NEW] [workspace_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/workspace_tools.py)

Tres tools para gestión de workspace:

**`list_workspaces()`**
- Si `projects_root` no está configurado → error descriptivo
- Lista subdirectorios de `projects_root` (1 nivel)
- Marca cuál es el workspace activo (`*`)
- Formato: `project-name/ (12 .py files, git: main)`

**`switch_workspace(name)`**
- Valida que `name` exista en `projects_root`
- Cambia `_PROJECT_ROOT` global en `selfcode_tools.py` y `shell_tools.py`
- Cambia `cwd` del shell executor
- Retorna confirmación con resumen del nuevo workspace (archivos, branch actual)
- Seguridad: no permite `..` ni paths absolutos en `name`

**`get_workspace_info()`**
- Retorna info del workspace activo: nombre, path, branch git, archivos totales, últimos commits

#### [MODIFY] [selfcode_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/selfcode_tools.py)

- Extraer `_PROJECT_ROOT` a una variable mutable (actualmente es constante de módulo)
- Exponer `set_project_root(path)` para que `workspace_tools` pueda cambiarla
- Validar que el nuevo root siempre esté dentro de `projects_root` o sea el root original

#### [MODIFY] [shell_tools.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/shell_tools.py)

- Exponer `set_cwd(path)` para cambiar el directorio de trabajo del shell executor
- Validar que el nuevo cwd siempre esté dentro de `projects_root`

#### [MODIFY] [__init__.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/tools/__init__.py)

- Importar y registrar `workspace_tools.register(registry, settings)` en `register_builtin_tools()`

#### [MODIFY] [router.py](file:///Users/sebastiandavila/wasap/wasap-assistant/app/skills/router.py)

Agregar categoría `"workspace"` a `TOOL_CATEGORIES`:
```python
"workspace": ["list_workspaces", "switch_workspace", "get_workspace_info"],
```

---

## Orden de Implementación

```
Día 1-2: F9 (Intelligent Context Loading)
  1. selfcode_tools.py  — get_file_outline + read_lines
  2. loop.py            — actualizar prompt del agente
  3. Tests unitarios

Día 3-4: F8 (Cron Jobs)
  1. db.py              — tabla user_cron_jobs
  2. repository.py      — CRUD methods
  3. scheduler_tools.py — create_cron, list_crons, delete_cron
  4. main.py            — restaurar crons al boot
  5. router.py          — categoría actualizada
  6. Tests unitarios

Día 5+: F10 (Multi-Project Workspace)
  1. config.py          — projects_root setting
  2. workspace_tools.py — nuevo módulo
  3. selfcode_tools.py  — _PROJECT_ROOT mutable + set_project_root
  4. shell_tools.py     — set_cwd
  5. __init__.py        — registrar workspace tools
  6. router.py          — categoría "workspace"
  7. Tests unitarios + integración
```

---

## Plan de Verificación

### Tests Automatizados

```bash
# F9: Context loading
pytest tests/test_selfcode_tools.py -v -k "outline or read_lines"

# F8: Cron jobs
pytest tests/test_scheduler_tools.py -v -k "cron"

# F10: Workspace
pytest tests/test_workspace_tools.py -v

# Suite completa
pytest tests/ -v
```

### Tests Manuales (WhatsApp)

#### F8: Cron Jobs
1. **Crear cron**: `/agent Recordame cada lunes a las 9am que revise los PRs pendientes`
   - Esperado: agente llama `create_cron("0 9 * * 1", "Revisar PRs pendientes", "America/Argentina/Buenos_Aires")`
2. **Listar crons**: "Listame mis recordatorios recurrentes"
   - Esperado: tabla con ID, schedule, mensaje
3. **Persistencia**: Reiniciar container → verificar que los crons se restauran
4. **Eliminar**: "Eliminá el recordatorio #3"

#### F9: Context Loading
1. **Outline**: `/agent Mostrame la estructura de loop.py`
   - Esperado: agente llama `get_file_outline("app/agent/loop.py")` y muestra clases/funciones con líneas
2. **Read lines**: `/agent Mostrá las líneas 50-70 de loop.py` 
   - Esperado: agente llama `read_lines("app/agent/loop.py", 50, 70)` con líneas numeradas
3. **LLM pattern**: `/agent Analizá la función run_agent_session`
   - Esperado: agente primero llama `get_file_outline`, luego `read_lines` para el rango correcto

#### F10: Multi-Project
1. **Listar**: "Qué proyectos tengo disponibles?"
   - Esperado: lista de directorios en `projects_root`
2. **Cambiar**: "Cambiá al proyecto wasap-frontend"
   - Esperado: confirmación, nuevo branch, conteo de archivos
3. **Verificar**: "Listá los archivos del proyecto actual"
   - Esperado: archivos del nuevo proyecto, no del anterior

---

## Decisiones de Diseño

| Decisión | Alternativa descartada | Razón |
|----------|----------------------|-------|
| Cron expr estándar (5 campos) | Natural language parsing | Más predecible, APScheduler lo soporta nativamente via `CronTrigger` |
| Persistencia en SQLite (no JSONL) | JSONL como en F6 | Los cron jobs son datos estructurados con CRUD — relacional es más apropiado |
| AST para .py, regex para otros | Solo regex | AST da información precisa (decorators, class hierarchy) para Python |
| `_PROJECT_ROOT` mutable | Config file per-session | Simplifica la implementación, un solo workspace activo por instancia |
| Max 200 líneas por `read_lines` | Sin límite | Protege el contexto del LLM de desbordes accidentales |

---

## Riesgos y Mitigaciones

| Riesgo | Mitigación |
|--------|-----------|
| Cron expr inválida del LLM | Validar con `CronTrigger.from_crontab()` antes de persistir — retornar error descriptivo |
| AST falla en archivos .py con syntax errors | Catch `SyntaxError` → fallback a regex |
| `switch_workspace` a path malicioso | Validar que `name` no contenga `..`, `/`, ni sea path absoluto. Resolver y verificar que esté bajo `projects_root` |
| Demasiados cron jobs por usuario | Limitar a 20 crons activos por `phone_number` |
| `read_lines` con rango gigante | Hard cap en 200 líneas por llamada — retornar error si `end - start > 200` |

---

## Dependencias

- Sprint 1 + Sprint 2 completados ✅
- APScheduler ya integrado en `main.py` ✅
- `projects_root` debe configurarse en `.env` para F10 (opcional en F8/F9)
