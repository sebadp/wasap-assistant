# Feature: Auto-Evolución de Prompts

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-20
> **Fase**: Eval — Iteración 5
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

El sistema aprende de sus errores en dos niveles:

1. **Nivel 1 — Memorias de auto-corrección**: Cuando un guardrail falla, se guarda automáticamente una memoria de categoría `self_correction` que el LLM lee en el próximo contexto, evitando el mismo error.
2. **Nivel 2 — Evolución de prompts**: El agente puede proponer cambios al system prompt basados en patrones de falla, guardarlos como drafts, y un humano los aprueba vía `/approve-prompt`.

---

## Arquitectura

```
[Guardrail falla — ej: language_match]
        │
        ▼
_save_self_correction_memory() ← background task
        │
        ▼
repository.add_memory(category="self_correction")
        │
        ▼
memory_file.sync() + embed (best-effort)
        │
        ▼ (próxima conversación)
_get_memories() → contexto LLM (el agente "recuerda" el error)

[Usuario: "los últimos 3 fallos fueron de idioma, proponé un cambio"]
        │
        ▼
propose_prompt_change(prompt_name, diagnosis, proposed_change) ← eval tool
        │
        ▼
ollama_client.chat([system_msg, user_msg]) → nuevo prompt
        │
        ▼
repository.save_prompt_version(version=N+1, created_by="agent")

[Usuario: /approve-prompt system_prompt 3]
        │
        ▼
repository.activate_prompt_version("system_prompt", 3)
        │
        ▼
invalidate_prompt_cache("system_prompt")
        │
        ▼ (próxima conversación)
get_active_prompt() → carga v3 desde DB
```

---

## Schema

```sql
CREATE TABLE IF NOT EXISTS prompt_versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_name TEXT NOT NULL,
    version     INTEGER NOT NULL,
    content     TEXT NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 0,
    scores      TEXT NOT NULL DEFAULT '{}',
    created_by  TEXT NOT NULL DEFAULT 'human',
    approved_at TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_version ON prompt_versions(prompt_name, version);
```

> `is_active` es enforced a nivel aplicación: `activate_prompt_version()` corre en una transacción que primero desactiva todas las versiones del prompt, luego activa la nueva. SQLite no soporta partial unique indexes para esto.

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/database/db.py` | `PROMPT_SCHEMA` — tabla `prompt_versions` |
| `app/database/repository.py` | `save_prompt_version()`, `get_active_prompt_version()`, `get_prompt_version()`, `activate_prompt_version()`, `list_prompt_versions()`, `get_latest_memory()` |
| `app/eval/prompt_manager.py` | Cache en memoria + `get_active_prompt()` + `invalidate_prompt_cache()` |
| `app/eval/evolution.py` | `propose_prompt_change()` — genera draft via LLM |
| `app/webhook/router.py` | `_save_self_correction_memory()` helper + integración de `get_active_prompt()` + background task post-guardrail-failure |
| `app/commands/builtins.py` | `cmd_approve_prompt()` + registro en `register_builtins()` |
| `app/skills/tools/eval_tools.py` | Tool `propose_prompt_change` para el eval skill |

---

## Walkthrough técnico

### Nivel 1: Memorias de auto-corrección

Al final del guardrail check en `_run_normal_flow()`:
```python
if not guardrail_report.passed:
    failed_checks = [r.check_name for r in guardrail_report.results if not r.passed]
    _track_task(asyncio.create_task(
        _save_self_correction_memory(user_text, failed_checks, ...)
    ))
```

La función `_save_self_correction_memory()`:
1. Genera un note del tipo: `"[auto-corrección] Al responder '...', los guardrails detectaron: language_match. Recordar evitar este tipo de error."`
2. Llama `repository.add_memory(note, category="self_correction")`
3. Sync a MEMORY.md vía `memory_file.sync()`
4. Embed best-effort si `vec_available`

Estas memorias se inyectan automáticamente en Phase B del pipeline (ya pasan por `get_active_memories()`).

### Nivel 2: Prompt versioning

**Propuesta (via eval tool `propose_prompt_change`):**
1. LLM genera un prompt modificado con instrucciones específicas al engineer
2. Se guarda con `save_prompt_version(created_by="agent", is_active=0)`
3. El agente informa al usuario: "usa /approve-prompt system_prompt N para activarlo"

**Aprobación (`/approve-prompt`):**
1. Verifica que la versión existe y no está activa
2. `activate_prompt_version()`: transacción que desactiva todas → activa la nueva
3. `invalidate_prompt_cache()`: limpia la cache en memoria
4. Próximas conversaciones cargan la nueva versión vía `get_active_prompt()`

### Cache de prompts

```python
# app/eval/prompt_manager.py
_active_prompts: dict[str, str] = {}  # module-level, survives requests

async def get_active_prompt(prompt_name, repository, default) -> str:
    if prompt_name not in _active_prompts:
        row = await repository.get_active_prompt_version(prompt_name)
        _active_prompts[prompt_name] = row["content"] if row else default
    return _active_prompts[prompt_name]
```

Primera llamada: query a DB. Siguientes: hit de cache. Se invalida solo con `invalidate_prompt_cache()`.

---

## Flujos de uso

**Flujo 1 — Auto-corrección de idioma:**
```
1. Bot responde en inglés a mensaje en español
2. Guardrail language_match falla → score 0.0 en traza
3. Background: memory "[auto-corrección] Al responder '...', los guardrails detectaron: language_match."
4. En la próxima conversación, esa memoria aparece en el contexto
5. Bot ahora "recuerda" responder en español
```

**Flujo 2 — Evolución de prompt:**
```
Usuario: "los últimos 5 fallos son de idioma, proponé un fix al system prompt"
→ list_recent_failures() → failures con language_match
→ propose_prompt_change(
    prompt_name="system_prompt",
    diagnosis="Responde en inglés cuando el usuario habla español",
    proposed_change="Agregar instrucción explícita: 'SIEMPRE responde en el idioma del usuario'"
  )
→ "Propuesta guardada: system_prompt v2. Usa /approve-prompt system_prompt 2"

Usuario: /approve-prompt system_prompt 2
→ "Prompt 'system_prompt' v2 activado."
→ (próximas conversaciones usan el prompt v2)
```

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Memorias de self_correction | Modificar el system prompt directo | Requiere aprobación humana; memorias son reversibles |
| Cache de prompts a nivel módulo | Reload desde DB por request | Evita latencia en el hot path; se invalida explícitamente |
| Transacción en `activate_prompt_version` | Constraint DB | SQLite no tiene partial unique index; la transacción garantiza exactamente 1 activo |
| `propose_prompt_change` como eval tool | Comando /propose-prompt | El agente puede proponer en respuesta a una conversación, sin que el usuario conozca el comando |

---

## Guía de testing

→ Ver [`docs/testing/15-eval_auto_evolution_testing.md`](../testing/15-eval_auto_evolution_testing.md)
