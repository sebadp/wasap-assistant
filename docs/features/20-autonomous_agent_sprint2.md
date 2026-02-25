# Feature: Autonomous Agent Sprint 2 — Diff Preview, PR Creation, Session Persistence, Bootstrap Files

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-25
> **Fase**: Agent Mode
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Extiende el modo agéntico con cuatro capacidades de UX premium: el agente puede mostrar un diff de sus cambios antes de aplicarlos, crear Pull Requests en GitHub directamente, persistir cada ronda de trabajo en JSONL para auditoría y recuperación, y cargar archivos de contexto personalizados (`SOUL.md`, `USER.md`, `TOOLS.md`) al inicio de cada sesión.

---

## Arquitectura

```
[Usuario: "Crear PR para el fix"]
        │
        ▼
[agent/loop.py] ─── carga bootstrap files (SOUL/USER/TOOLS.md)
        │
        ▼
[selfcode_tools: preview_patch] ─► muestra diff al usuario
        │                          (sin aplicar cambios)
        ▼
[request_user_approval] ─► usuario confirma
        │
        ▼
[selfcode_tools: apply_patch] ─► aplica el cambio
        │
        ▼
[git_tools: git_create_pr] ─► POST /repos/{owner}/{repo}/pulls
        │
        ▼
[agent/persistence: save_round] ─► data/agent_sessions/<phone>_<session_id>.jsonl
        │
        ▼
[WhatsApp: "✅ PR creado: https://github.com/..."]
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/skills/tools/selfcode_tools.py` | `preview_patch()` — genera unified diff sin aplicar |
| `app/skills/tools/git_tools.py` | `git_create_pr()` — crea PR via GitHub REST API |
| `app/agent/persistence.py` | Append-only JSONL por sesión |
| `app/agent/loop.py` | Carga de bootstrap files al inicio de sesión |
| `data/workspace/SOUL.md` | Personalidad del agente (opcional) |
| `data/workspace/USER.md` | Perfil del usuario (opcional) |
| `data/workspace/TOOLS.md` | Notas sobre herramientas disponibles (opcional) |

---

## Walkthrough técnico: cómo funciona

### F4: Diff Preview (`preview_patch`)

1. El LLM llama `preview_patch(path, search, replace)` → `selfcode_tools.py`
2. La función lee el archivo, encuentra `search`, genera un unified diff con `difflib.unified_diff`
3. Retorna el diff formateado como string — el LLM lo envía al usuario
4. Luego el LLM llama `request_user_approval` antes de `apply_patch`
5. **No aplica nada** — solo muestra el preview

### F5: PR Creation (`git_create_pr`)

1. El LLM llama `git_create_pr(title, body)` → `git_tools.py`
2. Detecta owner/repo de `settings.github_repo` (formato: `owner/repo`)
3. `POST https://api.github.com/repos/{owner}/{repo}/pulls` con `Authorization: token {github_token}`
4. Retorna la URL del PR creado o mensaje de error descriptivo
5. Requiere `GITHUB_TOKEN` y `GITHUB_REPO` en `.env`

### F6: Session Persistence

1. `run_agent_session()` en `loop.py` llama `save_round(session_id, round_data)` después de cada round
2. `persistence.py` hace append a `data/agent_sessions/<phone>_<session_id>.jsonl`
3. Cada línea: `{"round": N, "tool_calls": [...], "reply_preview": "...", "task_plan_snapshot": "..."}`
4. Best-effort: errores de I/O logueados, nunca propagados (no abortan la sesión)

### F7: Bootstrap Files

1. Al inicio de `run_agent_session()`, se intenta cargar:
   - `data/workspace/SOUL.md` → prepend como system message (personalidad/valores)
   - `data/workspace/USER.md` → prepend como system message (perfil del usuario)
   - `data/workspace/TOOLS.md` → prepend como system message (notas sobre herramientas)
2. Archivos inexistentes se ignoran silenciosamente (`try/except FileNotFoundError`)
3. Los que existen se agregan al inicio del `messages` list como `ChatMessage(role="system", ...)`

---

## Cómo extenderla

- **Para agregar más bootstrap files**: agregar entry en el loop de carga en `loop.py`
- **Para cambiar el repo GitHub**: modificar `GITHUB_REPO=owner/repo` en `.env`
- **Para cambiar el directorio de sesiones**: modificar `data/agent_sessions/` en `persistence.py`

---

## Guía de testing

→ Ver [`docs/testing/20-autonomous_agent_sprint2_testing.md`](../testing/20-autonomous_agent_sprint2_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| `preview_patch` antes de `apply_patch` | Aplicar directamente + mostrar diff post-hoc | El usuario debe ver qué cambia antes, no después |
| JSONL append-only para persistencia | SQLite con tabla `agent_rounds` | JSONL es más simple, auditable con `cat`/`grep`, no requiere schema |
| Bootstrap files como archivos en `data/workspace/` | Config YAML en `.env` | Fácil de editar sin reiniciar el servidor |
| GitHub REST API directamente | MCP GitHub server | Las operaciones de PR requieren contexto de sesión que ya está en `loop.py` |

---

## Gotchas y edge cases

- **`github_token` no configurado**: `git_create_pr` retorna mensaje descriptivo, no crash
- **Bootstrap files grandes**: se truncan implícitamente por el límite de contexto del LLM
- **Sesión interrumpida**: los rounds ya persistidos en JSONL están disponibles para auditoría aunque la sesión falle
- **Diff con búsqueda no encontrada**: `preview_patch` retorna error descriptivo (no genera diff vacío)

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `github_token` | `None` | Token para GitHub API (crear PRs) |
| `github_repo` | `None` | Repo en formato `owner/repo` |
| `agent_write_enabled` | `False` | Habilita apply_patch (write tools) |
