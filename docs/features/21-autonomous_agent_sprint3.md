# Feature: Autonomous Agent Sprint 3 — Cron Jobs, File Outline, Multi-Project Workspace

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-25
> **Fase**: Agent Mode
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Agrega tres extensiones al sistema agéntico: cron jobs definidos por el usuario (tareas programadas recurrentes), herramientas inteligentes de lectura de código (`get_file_outline`, `read_lines`), y un sistema de workspace multi-proyecto que permite al agente cambiar el directorio raíz de trabajo.

---

## Arquitectura

### F8: Cron Jobs
```
[/agent: "Recordarme cada día a las 9am los tasks pendientes"]
        │
        ▼
[scheduler_tools: create_cron(schedule, message, phone)]
        │
        ▼
[APScheduler: registrar job cron]
        │
        ▼
[SQLite: tabla user_cron_jobs]
        │
        ▼ (al disparar)
[WhatsAppClient: enviar mensaje]
```

### F9: Intelligent File Loading
```
[LLM: "Necesito entender api/server.py"]
        │
        ▼
[selfcode_tools: get_file_outline("api/server.py")]
        │── Lista funciones/clases con números de línea (AST-based)
        ▼
[LLM selecciona rango relevante]
        │
        ▼
[selfcode_tools: read_lines("api/server.py", start=45, end=80)]
        │── Solo el fragmento necesario (ahorra contexto)
        ▼
[LLM procesa el código específico]
```

### F10: Multi-Project Workspace
```
[LLM: "Cambiar al proyecto backend-api"]
        │
        ▼
[workspace_tools: switch_workspace("backend-api")]
        │── Modifica _PROJECT_ROOT en selfcode_tools + shell_tools
        ▼
[Todas las tools subsiguientes operan en el nuevo directorio]
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/skills/tools/scheduler_tools.py` | `create_cron`, `list_crons`, `delete_cron` |
| `app/database/db.py` | Tabla `user_cron_jobs` |
| `app/skills/tools/selfcode_tools.py` | `get_file_outline()`, `read_lines()` |
| `app/skills/tools/workspace_tools.py` | `list_workspaces()`, `switch_workspace()`, `get_workspace_info()` |
| `app/config.py` | `projects_root` — directorio base para workspaces |

---

## Walkthrough técnico: cómo funciona

### F8: Cron Jobs

1. Usuario pide crear un cron: `create_cron(schedule="0 9 * * *", message="Check tasks", phone_number=...)`
2. Se valida el cron expression con `croniter`
3. Se registra en APScheduler: `scheduler.add_job(func, 'cron', **parsed_schedule, id=job_id)`
4. Se persiste en `user_cron_jobs` (SQLite): `id, phone_number, schedule, message, active`
5. Al dispararse, `wa_client.send_message(phone_number, message)` via closure en el job
6. `list_crons()` lee de SQLite los crons activos del usuario
7. `delete_cron(id)` → `scheduler.remove_job(id)` + `UPDATE active=0`

### F9: `get_file_outline` + `read_lines`

**`get_file_outline(path)`**:
1. Lee el archivo con `ast.parse()`
2. Extrae funciones (`ast.FunctionDef`, `ast.AsyncFunctionDef`) y clases (`ast.ClassDef`)
3. Retorna lista con nombre, tipo y número de línea
4. Fallback a regex para archivos no-Python

**`read_lines(path, start, end)`**:
1. Lee el archivo completo
2. Retorna solo el rango `[start-1:end]` (1-indexed → 0-indexed)
3. Prefixea cada línea con su número (para que el LLM pueda hacer referencias precisas)
4. Respeta `_is_safe_path()` — no puede leer fuera del proyecto

### F10: Multi-Project Workspace

1. `list_workspaces()` → lista subdirectorios de `settings.projects_root`
2. `switch_workspace(name)` → llama `set_project_root(new_path)` en el módulo de workspace
3. `set_project_root()` actualiza `_PROJECT_ROOT` en `selfcode_tools` y `shell_tools` via módulo compartido
4. Todas las tools subsiguientes (`read_source_file`, `run_command`, etc.) operan en el nuevo root
5. `get_workspace_info()` → retorna nombre, path, contenido del README si existe

---

## Cómo extenderla

- **Para agregar más fields al cron**: extender la tabla `user_cron_jobs` y el schema del tool
- **Para agregar outline a más lenguajes**: agregar parsers en `get_file_outline()` (regex-based)
- **Para persistir el workspace activo**: agregar `current_workspace` a `conversation_state`

---

## Guía de testing

→ Ver [`docs/testing/21-autonomous_agent_sprint3_testing.md`](../testing/21-autonomous_agent_sprint3_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| `get_file_outline` AST-based | Grep por `def `/`class ` | AST da números de línea exactos y maneja docstrings |
| `_PROJECT_ROOT` mutable shared via función | Reiniciar con nuevo root por sesión | Permite cambios en caliente sin perder la sesión |
| Cron expression (estilo Unix) | Lenguaje natural ("cada día a las 9") | Standard, sin ambigüedad, LLM lo convierte bien |
| SQLite para persistir crons | Solo APScheduler en memoria | Los crons sobreviven reinicios del servidor |

---

## Gotchas y edge cases

- **`projects_root` vacío**: `list_workspaces` retorna error descriptivo
- **Cron expression inválida**: `create_cron` rechaza con error de validación
- **`read_lines` con rango out-of-bounds**: retorna las líneas disponibles (no crash)
- **`switch_workspace` a proyecto no existente**: verifica que el path exista antes de cambiar
- **AST parse error**: `get_file_outline` hace fallback a regex simple

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `projects_root` | `""` | Directorio base para workspaces (vacío = single-project mode) |
| `agent_write_enabled` | `False` | Necesario para operaciones write en el workspace activo |
