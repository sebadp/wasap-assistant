# Feature: Persistencia y Memoria

> **Versión**: v1.0
> **Fecha de implementación**: 2025-12
> **Fase**: Fase 2
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Las conversaciones y memorias del usuario se persisten en SQLite. El usuario puede guardar información con `/remember`, olvidarla con `/forget`, y el sistema resume conversaciones largas para mantener el contexto sin exceder la ventana del LLM.

---

## Arquitectura

```
[Usuario]
    │
    ├─ /remember <texto> ──► [CommandRegistry] ──► [Repository.add_memory()]
    ├─ /forget <id>       ──► [CommandRegistry] ──► [Repository.delete_memory()]
    ├─ /memories          ──► [CommandRegistry] ──► [Repository.list_memories()]
    │
    └─ (mensaje normal)
            │
            ▼
    [ConversationManager]
        ├─ get_or_create_conversation(phone)
        ├─ save_message(conv_id, role, content)
        ├─ get_recent_messages(conv_id, limit)
        └─ summarize_and_compact(conv_id)
                │
                ▼
        [Summarizer — LLM genera resumen de N mensajes]
                │
                ▼
        [Repository.save_summary(conv_id, summary)]
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/database/db.py` | Schema SQLite, `init_db()`, PRAGMA tuning, sqlite-vec |
| `app/database/repository.py` | CRUD: memorias, mensajes, conversaciones, summaries |
| `app/conversation/manager.py` | `ConversationManager` — historial por conversación, summarizer |
| `app/commands/registry.py` | `CommandRegistry` — registro y dispatch de /commands |
| `app/commands/builtins.py` | Comandos built-in: `/remember`, `/forget`, `/memories`, `/clear` |
| `app/memory/markdown.py` | `MemoryFile` — sync bidireccional SQLite ↔ MEMORY.md |
| `app/formatting/compaction.py` | `compact_tool_output()` — compactación de payloads grandes |

---

## Walkthrough técnico

1. **Init DB**: `init_db()` crea tablas (conversations, messages, memories, etc.) con `CREATE TABLE IF NOT EXISTS`
2. **PRAGMA tuning**: `synchronous=NORMAL`, `cache_size=-32000` (32MB), `temp_store=MEMORY`
3. **Comandos**: Cuando el texto empieza con `/`, se despacha al `CommandRegistry` en lugar del LLM
4. **Memorias**: se almacenan en tabla `memories` con campos `content`, `category`, `active`, `created_at`
5. **MEMORY.md sync**: cada cambio en memorias actualiza `data/MEMORY.md` y viceversa
6. **Summarization**: cuando el historial excede `conversation_max_messages`, el `Summarizer` genera un resumen con LLM y borra mensajes antiguos
7. **Pre-compaction flush**: antes de borrar mensajes, se extraen facts→memorias y eventos→daily log

---

## Cómo extenderla

- **Agregar comando nuevo**: registrar en `app/commands/builtins.py` con `registry.register(name, handler, description)`
- **Cambiar la estrategia de summarization**: modificar `app/conversation/manager.py`
- **Agregar tabla nueva**: agregar DDL en `app/database/db.py:SCHEMA` (se auto-crea en startup)

---

## Guía de testing

→ Ver [`docs/testing/persistencia_memoria_testing.md`](../testing/persistencia_memoria_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| SQLite (aiosqlite) | PostgreSQL, Redis | Zero-dependency, funciona en single-container, suficiente para single-user |
| PRAGMA tuning agresivo | Defaults SQLite | 3-5x mejora en escritura con `synchronous=NORMAL` |
| Comandos con `/` prefix | Detección por NLP | Determinístico, cero latencia, zero ambigüedad |
| MEMORY.md bidireccional | Solo DB | El usuario puede editar memorias manualmente con cualquier editor |
| Resumen LLM antes de borrar | Truncado simple | Preserva context y decisions, no solo datos |

---

## Gotchas y edge cases

- **`/clear`** borra mensajes pero guarda un snapshot de los últimos 15 en `data/memory/snapshots/`
- **La tabla `conversations`** usa `phone_number` como `UNIQUE` — una conversación por número
- **MEMORY.md sync** tiene un guard (`threading.Event`) para evitar loops infinitos watcher→write→watcher
- **`dedup` de facts** usa `difflib.SequenceMatcher(ratio > 0.8)` — memorias similares no se duplican

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `DATABASE_PATH` | `data/wasap.db` | Ruta del archivo SQLite |
| `CONVERSATION_MAX_MESSAGES` | `20` | Trigger para summarization |
| `MEMORY_FILE_WATCH_ENABLED` | `True` | Habilita watchdog en MEMORY.md |
