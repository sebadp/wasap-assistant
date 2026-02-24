# Feature: Memoria Avanzada

> **Versión**: v1.0
> **Fecha de implementación**: 2026-01
> **Fase**: Fase 5
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

El sistema de memoria opera en 3 capas: semántica (MEMORY.md — facts permanentes), episódica reciente (daily logs — qué pasó hoy), y episódica histórica (session snapshots — conversaciones archivadas). Antes de borrar mensajes, un pre-compaction flush extrae información valiosa. Un consolidador LLM elimina duplicados y contradicciones.

---

## Arquitectura

```
[Memorias]
    ├─ Capa 1: MEMORY.md (semántica)
    │     ├─ SQLite ↔ MEMORY.md (sync bidireccional)
    │     ├─ Watchdog file watcher
    │     └─ Consolidador LLM (dedup/merge)
    │
    ├─ Capa 2: Daily Logs (episódica reciente)
    │     ├─ data/memory/YYYY-MM-DD.md
    │     └─ Append-only, un archivo por día
    │
    └─ Capa 3: Snapshots (episódica histórica)
          ├─ data/memory/snapshots/<slug>.md
          └─ Guardados en /clear con últimos 15 msgs

[Pre-compaction flush]
    mensajes a borrar → LLM extrae:
        ├─ facts → add_memory()
        └─ events → daily_log.append()
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/memory/markdown.py` | `MemoryFile` — sync bidireccional SQLite ↔ MEMORY.md |
| `app/memory/watcher.py` | `MemoryWatcher` — watchdog para edición manual de MEMORY.md |
| `app/memory/daily_log.py` | `DailyLog` — append-only logs diarios + snapshots |
| `app/memory/consolidator.py` | Dedup/merge de memorias via LLM |
| `app/conversation/manager.py` | Pre-compaction flush antes de borrar mensajes |

---

## Walkthrough técnico

### Sync bidireccional MEMORY.md

1. **DB → archivo**: tras `add_memory()`, se llama `memory_file.sync(all_memories)` que regenera MEMORY.md
2. **Archivo → DB**: si el usuario edita MEMORY.md manualmente, el `MemoryWatcher` (watchdog) detecta el cambio
3. **Guard anti-loop**: `threading.Event` previene sync circular (DB→file→watcher→DB→file→...)
4. **Categoría self_correction excluida**: las correcciones del agente no se escriben a MEMORY.md

### Daily logs

1. Cada evento se appendea a `data/memory/YYYY-MM-DD.md`
2. Los logs son append-only — nunca se borran durante el día
3. Se leen como contexto para el LLM (Phase B en `_handle_message`)

### Pre-compaction flush

1. Cuando el historial excede el límite, antes de summarizar y borrar:
2. LLM extrae facts nuevos → `add_memory()` con dedup via `SequenceMatcher(ratio > 0.8)`
3. LLM extrae eventos del día → `daily_log.append()`
4. Solo después se procede con la summarization

### Session snapshots

1. `/clear` guarda los últimos 15 mensajes en `data/memory/snapshots/<slug>.md`
2. El slug se genera con LLM (resumen corto de la sesión)
3. Los snapshots son read-only — sirven para contexto histórico

### Consolidación

1. Después del flush, el consolidador LLM revisa todas las memorias activas
2. Detecta duplicados y contradicciones
3. Merge memorias similares, marca contradictorias como inactivas

---

## Cómo extenderla

- **Agregar nueva capa de memoria**: crear módulo en `app/memory/` e integrarlo en Phase B
- **Cambiar umbral de dedup**: constante en `consolidator.py` (ratio 0.8)
- **Agregar categorías de memoria**: campo `category` en tabla `memories`, filtrar en queries

---

## Guía de testing

→ Ver [`docs/testing/07-memoria_avanzada_testing.md`](../testing/07-memoria_avanzada_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| 3 capas de memoria | Una sola tabla | Distintas duraciones y propósitos requieren distintas estrategias |
| MEMORY.md editable | Solo API | Flexibilidad — el usuario puede editar con cualquier editor |
| Watchdog para sync | Polling | Reacción instantánea, sin CPU innecesario |
| Dedup con SequenceMatcher | Embeddings para dedup | Más rápido, determinístico, suficiente para similitud textual |
| Pre-compaction flush | Borrar sin extraer | Preserva conocimiento que se perdería al truncar |

---

## Gotchas y edge cases

- **Editores con atomic rename** (VS Code): el watcher maneja `on_created` además de `on_modified` porque el editor crea un archivo temporal y lo renombra.
- **self_correction** categoría está excluida del sync a MEMORY.md para evitar loops con el watcher.
- **Los daily logs** se leen con `asyncio.to_thread()` para no bloquear el event loop.

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `MEMORY_DIR` | `data/memory` | Directorio para daily logs y snapshots |
| `MEMORY_FILE_WATCH_ENABLED` | `True` | Habilita watchdog en MEMORY.md |
| `CONVERSATION_MAX_MESSAGES` | `20` | Trigger para pre-compaction flush |
