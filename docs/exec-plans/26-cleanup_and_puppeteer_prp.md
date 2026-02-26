# PRP: Limpieza general + Puppeteer-first con fallback a mcp-server-fetch

**Branch:** `feat/autonomy`
**Estado:** En progreso
**Creado:** 2026-02-25

## Contexto

Revisión de los planes 18-25 encontró 6 problemas prioritizados:

1. **Bug crítico** — La categoría `"fetch"` se fuerza en el fast-path de URLs pero nunca se mapea a herramientas reales → el LLM recibe 0 tools cuando detecta una URL pura. Fetching roto.
2. **Mismatch tools** — `system_prompt` en config.py referencia `fetch_markdown`/`fetch_txt` (mcp-server-fetch) pero solo Puppeteer está configurado en `mcp_servers.json`.
3. **Sin fallback** — Si Puppeteer no está disponible, no hay alternativa ni notificación al usuario.
4. **Deuda de proceso** — Planes 18, 19, 20, 21, 22, 24 implementados pero sin checkboxes marcados.
5. **Tests ausentes** — `shell_tools.py` (ejecución de comandos del sistema) sin cobertura de tests.
6. **Docs faltantes** — Features de Sprint 2, Sprint 3 y web fetch fix sin documentar.

---

## Fase 0: Crear PRP oficial del proyecto

- [x] Crear `docs/exec-plans/26-cleanup_and_puppeteer_prp.md` con todos los checkboxes de Fases 1-6 (formato stateful, template del proyecto)

---

## Fase 1: Fix fetch routing + Puppeteer-first con fallback (PRIORIDAD)

### 1.1 Agregar mcp-server-fetch a `data/mcp_servers.json`
- [x] Agregar mcp-server-fetch como servidor secundario con `enabled: true`

### 1.2 `app/mcp/manager.py` — Fetch mode tracking + registro de categoría "fetch"
- [x] Agregar `_fetch_mode: str = "unavailable"` como atributo de instancia en `__init__`
- [x] Agregar método público `get_fetch_mode() -> str`
- [x] Agregar `_register_fetch_category()` que detecta qué tools fetch están disponibles
- [x] Llamar `_register_fetch_category()` al final de `initialize()` para registrar la categoría "fetch" con las tools correctas

### 1.3 `app/config.py` — Neutralizar referencias a tools específicas en system_prompt
- [x] Reemplazar menciones hardcoded a `fetch_markdown`, `fetch_txt`, `fetch_html`, `max_length=40000` con instrucción genérica

### 1.4 `app/skills/executor.py` — Runtime fallback: Puppeteer → mcp-fetch
- [x] En `_run_tool_call()`: si tool es puppeteer Y resultado indica error → buscar tool equivalente en mcp-fetch → re-ejecutar con prefijo de aviso

### 1.5 `app/webhook/router.py` — Notificación al usuario cuando se usa fallback
- [x] Detectar si mensaje contiene URL y `mcp_manager.get_fetch_mode() == "mcp-fetch"`
- [x] Inyectar nota de sistema sobre Puppeteer no disponible

### Verificación Fase 1
- [x] Correr `make check` — pasar lint + typecheck + tests (436 passed, 23 skipped)

---

## Fase 2: Actualizar PRPs con checkboxes (deuda de proceso)

- [x] `docs/exec-plans/18-agentic_sessions_plan.md` — Agregar checkboxes + marcar [x]
- [x] `docs/exec-plans/19-autonomous_agent_plan.md` — Agregar checkboxes + marcar [x]
- [x] `docs/exec-plans/20-autonomous_agent_sprint2_plan.md` — Marcar [x] lo implementado
- [x] `docs/exec-plans/21-autonomous_agent_sprint3_plan.md` — Marcar [x] lo implementado
- [x] `docs/exec-plans/22-web_browsing_plan.md` — Agregar checkboxes + marcar estado real
- [x] `docs/exec-plans/24-observability_plan.md` — Marcar lo implementado

---

## Fase 3: Tests para shell_tools

- [x] Crear `tests/test_shell_tools.py` con:
  - Tests de `_validate_command()`: ALLOW, DENY, ASK cases
  - Tests de `run_command()` mockeado: éxito, timeout, truncation
  - Tests de `manage_process()`: list, kill
- [x] Correr `make test` — todos pasan (40 tests nuevos, todos verdes)

---

## Fase 4: CLAUDE.md + AGENTS.md

### CLAUDE.md
- [x] Agregar `app/security/` a sección Estructura
- [x] Agregar `app/agent/persistence.py` a sección Estructura
- [x] Agregar patrón `shell_tools`
- [x] Agregar patrón `workspace_tools`
- [x] Agregar patrón `git_tools`
- [x] Agregar patrón `persistence.py`
- [x] Actualizar patrón Puppeteer/mcp-fetch con fetch mode tracking

### AGENTS.md
- [x] Agregar `app/agent/` a tabla de ownership
- [x] Agregar `app/security/` a tabla de ownership

---

## Fase 5: Documentación de features faltantes

- [x] Crear `docs/features/20-autonomous_agent_sprint2.md`
- [x] Crear `docs/testing/20-autonomous_agent_sprint2_testing.md`
- [x] Crear `docs/features/21-autonomous_agent_sprint3.md`
- [x] Crear `docs/testing/21-autonomous_agent_sprint3_testing.md`
- [x] Crear `docs/features/25-web_fetch_fix.md`
- [x] Crear `docs/testing/25-web_fetch_fix_testing.md`
- [x] Actualizar `docs/features/README.md`
- [x] Actualizar `docs/testing/README.md`

---

## Fase 6: Limpieza de archivos sueltos

- [x] Eliminar `test_executor.py`
- [x] Eliminar `test_mcp.py`
- [x] Eliminar `test_router.py`
- [x] Eliminar `test_tools.py`

---

## Verificación end-to-end

1. [x] `make check` (lint + typecheck + tests) — 436 passed, 23 skipped ✅
2. [ ] Test manual: enviar URL pura por WhatsApp → LLM debe usar `puppeteer_navigate`
3. [ ] Test fallback: desactivar Puppeteer → enviar URL → logs muestran fallback + usuario recibe aviso
4. [ ] Test fallback runtime: Puppeteer activo pero falla → reintentar con mcp-fetch + prefixar mensaje
